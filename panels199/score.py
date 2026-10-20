#!/usr/bin/env python3
"""Score predictions on the 199 panels against truth A, B and C.
  python3 score.py predictions/nutrition-extractor.json predictions/etiquette-run13.jsonl [more files...]
A .json file is nutrition-extractor output ({barcode, pred:{entity:{value,unit}}}); a .jsonl file is a reader's output
({code, reading:{nutriments:{fat_100g:..}, basis:{per:..}}}), the format Etiquette and run_gguf.py produce.
Nine nutrients, the printed basis (100 g where the labels have it, else serving), a value agrees within 2% or 0.05,
each printed row is agree / differ / missing, each non-printed row is agree / invented. Standard library only."""
import json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from judge import num, agree
H = os.path.dirname(os.path.abspath(__file__))
NUT = ("energy_kcal", "energy_kj", "fat", "saturated_fat", "carbohydrates", "sugars", "fiber", "proteins", "salt")
A = {p["barcode"]: p for p in json.load(open(os.path.join(H, "truth_a.json")))}
Bt = {p["barcode"]: p for p in json.load(open(os.path.join(H, "truth_b.json")))}
ADJ = {}
for l in open(os.path.join(H, "adjudications.jsonl")):
    if l.strip():
        d = json.loads(l); ADJ[d["code"]] = d


def suffix(c):
    return "_100g" if any(k.endswith("_100g") for k in (set(A[c]["truth"]) | set(Bt[c]["truth"]))) else "_serving"


def truth_a(c, suf):
    out = {}
    for k in NUT:
        e = A[c]["truth"].get(k + suf)
        if not e: continue
        v = num(e["value"])
        if v is None: continue
        if k == "salt" and e.get("unit") == "mg": v /= 1000
        out[k] = v
    return out


def truth_b(c, suf):
    return {k: Bt[c]["truth"][k + suf]["value"] for k in NUT if (k + suf) in Bt[c]["truth"]}


def truth_c(c, suf):
    t = dict(truth_b(c, suf)); a = ADJ.get(c, {})
    for k in NUT:
        f = a.get(k + suf)
        if isinstance(f, dict) and "C" in f:
            if f["C"] is None: t.pop(k, None)
            else: t[k] = float(f["C"])
    return t


def load_pred(path):
    if path.endswith(".json"):
        d = {p["barcode"]: p for p in json.load(open(path))}
        def get(c, suf):
            p = d.get(c)
            if not p: return None
            out = {}
            for k in NUT:
                e = p["pred"].get(k + suf)
                if not e: continue
                v = num(e["value"])
                if v is None: continue
                if k == "salt" and e.get("unit") == "mg": v /= 1000
                out[k] = v
            return out
        return get
    d = {}
    for l in open(path, encoding="utf-8"):
        if l.strip():
            j = json.loads(l); d[j["code"]] = j["reading"]
    def get(c, suf):
        rd = d.get(c)
        if rd is None: return None
        per = str((rd.get("basis") or {}).get("per") or "").lower().replace(" ", "")
        b = "100" if per.startswith("100") else ("serving" if ("serving" in per or "portion" in per) else "")
        n = rd.get("nutriments") or {}
        vals = {k: num(n.get(k + "_100g")) for k in NUT if num(n.get(k + "_100g")) is not None}
        if ADJ.get(c, {}).get("ours_basis_ok"): return vals          # serving printed as 100 g (one panel)
        if suf == "_100g": return vals if b in ("100", "") else {}
        return vals if b == "serving" else {}
    return get


def run(label, truth_fn, pred_fn, codes):
    per = defaultdict(Counter); tot = Counter()
    for c in codes:
        suf = suffix(c); tv = truth_fn(c, suf); pv = pred_fn(c, suf) or {}
        for k in NUT:
            t, r = tv.get(k), pv.get(k)
            if t is None and r is None: continue
            kk = ("missing" if r is None else ("agree" if agree(t, r) else "differ")) if t is not None else "invented"
            per[k][kk] += 1; tot[kk] += 1
    n = sum(tot.values())
    print("  %-34s %4d judgements | agree %4d differ %3d missing %3d invented %3d | %5.1f%%" % (
        label, n, tot["agree"], tot["differ"], tot["missing"], tot["invented"], 100.0 * tot["agree"] / max(1, n)))
    print("      " + "  ".join("%s %d/%d" % (k.replace("saturated_fat", "sat").replace("carbohydrates", "carbs").replace("energy_", ""), per[k]["agree"], sum(per[k].values())) for k in NUT))


if __name__ == "__main__":
    files = sys.argv[1:] or [os.path.join(H, "predictions", "nutrition-extractor.json"), os.path.join(H, "predictions", "etiquette-run13.jsonl")]
    codes = sorted(A)
    preds = [(os.path.basename(f), load_pred(f)) for f in files]
    for lab, tf in (("Truth A: the human labels parsed by Robotoff's rules", truth_a),
                    ("Truth B: the printed values those labels show", truth_b),
                    ("Truth C: B corrected from the photos for every disputed field", truth_c)):
        print(lab)
        for name, fn in preds: run(name, tf, fn, codes)
