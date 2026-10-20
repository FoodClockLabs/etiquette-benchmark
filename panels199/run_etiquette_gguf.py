#!/usr/bin/env python3
"""Run Etiquette on the 199 panels through llama-server (GGUF), one photo per panel, with the model repo's own
run_gguf.py. Writes predictions/etiquette-gguf.jsonl in the scorer's format. Prerequisites, from the model card:
  huggingface-cli download mradermacher/Etiquette-1-8B-GGUF Etiquette-1-8B.Q4_K_M.gguf Etiquette-1-8B.mmproj-f16.gguf --local-dir gguf
  llama-server -m gguf/Etiquette-1-8B.Q4_K_M.gguf --mmproj gguf/Etiquette-1-8B.mmproj-f16.gguf -c 40960 -ngl 999 --jinja --port 8080
Then: python3 run_etiquette_gguf.py [--url http://127.0.0.1:8080] [--name etiquette-gguf]
The BF16 number in the README came from the FoodClock worker on a GPU; a Q4 quant is a little below it."""
import argparse, json, os, subprocess, sys, time, urllib.request
H = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument("--url", default="http://127.0.0.1:8080"); ap.add_argument("--name", default="etiquette-gguf")
ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args()
rg = os.path.join(H, "run_gguf.py")
if not os.path.exists(rg):
    urllib.request.urlretrieve("https://huggingface.co/FoodClockLabs/Etiquette-1-8B/resolve/main/run_gguf.py", rg)
panels = json.load(open(os.path.join(H, "truth_b.json")))
os.makedirs(os.path.join(H, "images"), exist_ok=True); os.makedirs(os.path.join(H, "predictions"), exist_ok=True)
outp = os.path.join(H, "predictions", a.name + ".jsonl"); t0 = time.time(); n = 0
with open(outp, "w") as f:
    for p in panels[: a.limit or None]:
        img = os.path.join(H, "images", "%s_%s.jpg" % (p["barcode"], p["image_id"]))
        if not os.path.exists(img):
            req = urllib.request.Request(p["image_url"], headers={"User-Agent": "etiquette-benchmark/1.0 (hello@foodclock.com)"})
            open(img, "wb").write(urllib.request.urlopen(req, timeout=60).read())
        r = subprocess.run([sys.executable, rg, img, "--url", a.url], capture_output=True, text=True, timeout=900)
        try:
            reading = json.loads(r.stdout)
        except Exception:
            reading = {"_error": r.stdout[-500:] + r.stderr[-500:]}
        f.write(json.dumps({"code": p["barcode"], "reading": reading}, ensure_ascii=False) + "\n"); f.flush()
        n += 1
        if n % 10 == 0:
            print(n, "panels", int(time.time() - t0), "s", flush=True)
print("done:", n, "panels ->", outp)
