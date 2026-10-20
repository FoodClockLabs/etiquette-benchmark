#!/usr/bin/env python3
"""The nutrition-row comparison on the printed-truth hundred: basis, energy kcal, salt, sodium (the rows both readers give).
  python3 compare.py replies/nutrition-extractor.jsonl replies/run13.jsonl [more...]   (standard library only)"""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import importlib.util
spec = importlib.util.spec_from_file_location("sc", os.path.join(H, "score.py")); sc = importlib.util.module_from_spec(spec); spec.loader.exec_module(sc)
cards = {json.loads(l)["code"]: json.loads(l) for l in open(os.path.join(H, "cards.jsonl"))}
NUT = ("basis", "energy_kcal_100g", "salt_100g", "sodium_mg")
for path in sys.argv[1:] or [os.path.join(H, "replies", "nutrition-extractor.jsonl"), os.path.join(H, "replies", "run13.jsonl")]:
    reps = {json.loads(l)["code"]: json.loads(l) for l in open(path, encoding="utf-8")}
    per = {f: [0, 0] for f in NUT}
    for c, card in cards.items():
        r = reps.get(c)
        if r is None: continue
        for f in NUT:
            row = card["truth"].get(f)
            if row is None: continue
            rv = sc.reading_value(r["reading"], f)
            empty = rv is None or (isinstance(rv, str) and not rv.strip())
            ok = (sc.judge(f, row["value"], rv) if not empty else False) if row["printed"] else empty
            per[f][1] += 1; per[f][0] += int(ok)
    a = sum(v[0] for v in per.values()); n = sum(v[1] for v in per.values())
    print("%-36s nutrition rows %3d/%3d = %5.1f%%  |  " % (os.path.basename(path), a, n, 100.0 * a / max(1, n)) + "  ".join("%s %d/%d" % (f.replace("_100g", "").replace("_mg", ""), v[0], v[1]) for f, v in per.items()))
