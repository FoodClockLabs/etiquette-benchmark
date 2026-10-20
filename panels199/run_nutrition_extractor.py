#!/usr/bin/env python3
"""Run openfoodfacts/nutrition-extractor on the 199 test panels, using the dataset's own OCR tokens and boxes (its
production input) and the image from the parquet. Writes predictions/nutrition-extractor.json.
CPU is fine (about 15 minutes). pip install -r ../requirements-nutrition-extractor.txt first."""
import io, json, os, sys, time
import pyarrow.parquet as pq
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "common"))
from robotoff_port import aggregate, postprocess
from layoutlm_runner import label_words, norm_box

H = os.path.dirname(os.path.abspath(__file__))
t = pq.read_table(os.path.join(H, "data", "test-00000-of-00001.parquet"))
out, t0 = [], time.time()
for i, row in enumerate(t.to_pylist(), 1):
    img = Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB"); W, H_ = img.size
    bb = row["bboxes"]; mx = max(max(b) for b in bb) if bb else 0
    boxes = [[max(0, min(1000, int(v))) for v in b] for b in bb] if mx <= 1000 else [norm_box(b, W, H_) for b in bb]
    labels = label_words(row["tokens"], boxes, img)
    post, valid = postprocess(aggregate(row["tokens"], labels))
    out.append({"barcode": row["meta"]["barcode"], "image_id": row["meta"]["image_id"], "pred": valid, "entities": post})
    if i % 20 == 0:
        print(i, "panels", int(time.time() - t0), "s", flush=True)
os.makedirs(os.path.join(H, "predictions"), exist_ok=True)
json.dump(out, open(os.path.join(H, "predictions", "nutrition-extractor.json"), "w"), ensure_ascii=False)
print("done:", len(out), "panels in", int(time.time() - t0), "s -> predictions/nutrition-extractor.json")
