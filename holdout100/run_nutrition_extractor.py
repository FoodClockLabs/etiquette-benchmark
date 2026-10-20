#!/usr/bin/env python3
"""Run openfoodfacts/nutrition-extractor on the printed-truth hundred the way its production sees it: the Google Cloud
Vision OCR file Open Food Facts publishes next to every image (<image>.json) plus the image. Per card the ticked photo that
yields the most valid nutrient entities is used. Writes replies/nutrition-extractor.jsonl in score.py's format.
Ours, stated: the model's *_100G labels say nothing about g vs ml, so basis "100ml" is chosen when the OCR text says
"100 ml" and not "100 g"; when only *_SERVING labels are found, the serving value is used with basis "serving: <size>".
No kJ->kcal derivation. CPU is fine (about 15 minutes). pip install -r ../requirements-nutrition-extractor.txt first."""
import json, os, re, sys, time, urllib.request
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from robotoff_port import aggregate, postprocess
from layoutlm_runner import label_words, norm_box, ocr_words_from_vision_json

H = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "etiquette-benchmark/1.0 (hello@foodclock.com)"}


def fetch(url, path):
    if not os.path.exists(path):
        open(path, "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
        time.sleep(0.3)
    return path


def read_photo(code, url):
    base = os.path.join(H, "cache", code + "_" + url.rsplit("/", 1)[-1].replace(".jpg", ""))
    jpath = fetch(url.replace(".jpg", ".json"), base + ".json"); ipath = fetch(url, base + ".jpg")
    words, boxes, W, Hh = ocr_words_from_vision_json(json.load(open(jpath)))
    if not words or not W:
        return None
    img = Image.open(ipath).convert("RGB")
    labels = label_words(words, [norm_box(b, W, Hh) for b in boxes], img)
    post, valid = postprocess(aggregate(words, labels))
    txt = " ".join(words).lower()
    return {"url": url, "entities": post, "valid": valid, "n_valid": len(valid),
            "ml": bool(re.search(r"100\s?ml", txt)) and not re.search(r"100\s?g\b", txt)}


def to_reading(ph):
    v = ph["valid"]; r = {"nutriments": {}, "basis": {}}
    def num(x):
        try: return float(x)
        except Exception: return None
    has100 = any(k.endswith("_100g") for k in v); hasserv = any(k.endswith("_serving") for k in v)
    suf = "_100g" if has100 else ("_serving" if hasserv else None)
    if suf == "_100g": r["basis"]["per"] = "100ml" if ph["ml"] else "100g"
    elif suf == "_serving":
        ss = v.get("serving_size"); r["basis"]["per"] = "serving: " + ss["text"] if ss else "serving"
    if suf:
        e = v.get("energy_kcal" + suf)
        if e and num(e["value"]) is not None: r["nutriments"]["energy_kcal_100g"] = num(e["value"])
        s = v.get("salt" + suf)
        if s and num(s["value"]) is not None: r["nutriments"]["salt_100g"] = num(s["value"]) / 1000 if s["unit"] == "mg" else num(s["value"])
        so = v.get("sodium" + suf)
        if so and num(so["value"]) is not None:
            x = num(so["value"]); r["sodium_mg"] = x if so["unit"] == "mg" else (x * 1000 if so["unit"] in ("g", None) else x)
    return r


if __name__ == "__main__":
    os.makedirs(os.path.join(H, "cache"), exist_ok=True); os.makedirs(os.path.join(H, "replies"), exist_ok=True)
    cards = [json.loads(l) for l in open(os.path.join(H, "cards.jsonl"))]
    outp = os.path.join(H, "replies", "nutrition-extractor.jsonl"); t0 = time.time()
    with open(outp, "w") as f:
        for i, c in enumerate(cards, 1):
            best = None; tried = []
            for p in c["photos"]:
                try: ph = read_photo(c["code"], p["url"])
                except Exception as e: print("  skip", c["code"], p["url"], e); continue
                if ph is None: continue
                tried.append({"url": p["url"], "n_valid": ph["n_valid"]})
                if best is None or ph["n_valid"] > best["n_valid"]: best = ph
            f.write(json.dumps({"code": c["code"], "reading": to_reading(best) if best else {"nutriments": {}, "basis": {}},
                                "reply": {"photo_used": best["url"] if best else None, "photos": tried, "entities": best["entities"] if best else []}}, ensure_ascii=False) + "\n")
            if i % 10 == 0: print(i, "cards", int(time.time() - t0), "s", flush=True)
    print("done ->", outp, "| score: python3 score.py cards.jsonl", outp)
