#!/usr/bin/env python3
"""Build truth A and truth B for the 199 test panels of openfoodfacts/nutrient-detection-layout.
  A = the human token labels aggregated and parsed by Robotoff's own rules (the project's definition of correct).
  B = the same labelled tokens read as a person reads them (kcal glued to the kJ recovered, thousands marks on kJ,
      "< 0,5" kept with its qualifier, a trailing 8/9 on a bare integer read as a misread g).
Writes truth_a.json and truth_b.json next to this file. Needs the dataset's test parquet (download.sh fetches it)."""
import json, os, re, sys
import pyarrow.parquet as pq
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from robotoff_port import aggregate, postprocess

H = os.path.dirname(os.path.abspath(__file__))
PQ = os.path.join(H, "data", "test-00000-of-00001.parquet")
t = pq.read_table(PQ, columns=["tokens", "ner_tags", "meta"])
names = json.loads(t.schema.metadata[b"huggingface"])["info"]["features"]["ner_tags"]["feature"]["names"]
NUMU = r"(<\s?)?(\d+(?:[.,]\d+)?)"
MACRO = ("proteins", "sugars", "fat", "saturated_fat", "carbohydrates", "fiber", "salt", "added_sugars", "trans_fat")


def nums(text):
    out = []
    for m in re.finditer(NUMU + r"\s*(kcal|kj|kJ|KJ|Kcal|KCAL|mg|µg|mcg|g)?", text.replace("O", "0")):
        out.append(("<" if m.group(1) else "", m.group(2).replace(",", "."), (m.group(3) or "").lower()))
    return out


def kj_fix(v, text):
    f = float(v)
    if f < 10 and re.fullmatch(r"\d[.,]\d{3}", v):
        return f * 1000
    m = re.search(r"\b(\d)\s(\d{3})\b", text)
    if m and f < 10:
        return float(m.group(1) + m.group(2))
    return f


A, B = [], []
for row in t.to_pylist():
    m = row["meta"]
    labels = [names[i] for i in row["ner_tags"]]
    ents = aggregate(row["tokens"], labels)
    post, valid = postprocess(ents)
    A.append({"barcode": m["barcode"], "image_id": m["image_id"], "image_url": m["image_url"], "ocr_url": m["ocr_url"],
              "usda": m["usda_table"], "truth": valid, "entities": post})
    b = {}
    for e in post:
        name, text = e["entity"], e["text"]
        if name == "serving_size":
            continue
        base, suf = name.rsplit("_", 1)
        suf = "_" + suf
        low = text.lower()
        if "trace" in low:
            b.setdefault(name, {"value": 0.0, "q": "traces", "text": text}); continue
        nu = nums(text)
        if not nu:
            continue
        if base in ("energy_kcal", "energy_kj"):
            kcal = [x for x in nu if x[2] == "kcal"]; kj = [x for x in nu if x[2] == "kj"]
            bare = [x for x in nu if x[2] == ""]
            if base == "energy_kj":
                src = kj or bare
                if src: b.setdefault("energy_kj" + suf, {"value": kj_fix(src[0][1], text), "q": "", "text": text})
                if kcal: b.setdefault("energy_kcal" + suf, {"value": float(kcal[0][1]), "q": "", "text": text})
            else:
                src = kcal or bare
                if src: b.setdefault("energy_kcal" + suf, {"value": float(src[0][1]), "q": "", "text": text})
                if kj: b.setdefault("energy_kj" + suf, {"value": kj_fix(kj[0][1], text), "q": "", "text": text})
            continue
        q, v, u = nu[0]
        val = float(v)
        if u == "" and base in MACRO and re.fullmatch(r"\d+[89]", v) and len(v) > 1 and not re.search(r"\d\s*g\b", low):
            val = float(v[:-1])
        if u == "mg" and base == "salt":
            val /= 1000
        b.setdefault(base + suf, {"value": val, "q": q, "text": text})
    B.append({"barcode": m["barcode"], "image_id": m["image_id"], "image_url": m["image_url"], "truth": b})
json.dump(A, open(os.path.join(H, "truth_a.json"), "w"), ensure_ascii=False)
json.dump(B, open(os.path.join(H, "truth_b.json"), "w"), ensure_ascii=False)
print("panels:", len(A), "-> truth_a.json, truth_b.json")
