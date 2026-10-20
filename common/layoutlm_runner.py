"""Run openfoodfacts/nutrition-extractor (LayoutLMv3-large) locally on OCR words + boxes + an image.
Research use only: the model is CC BY-NC-SA 4.0. Needs: pip install -r requirements-nutrition-extractor.txt"""
import os, torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForTokenClassification
from huggingface_hub import snapshot_download

_P = _M = None


def load(model_dir=None):
    global _P, _M
    if _M is None:
        d = model_dir or snapshot_download("openfoodfacts/nutrition-extractor",
                                           allow_patterns=["*.json", "*.safetensors", "*.txt", "merges*", "vocab*"])
        _P = AutoProcessor.from_pretrained(d, apply_ocr=False)
        _M = AutoModelForTokenClassification.from_pretrained(d).eval()
        torch.set_num_threads(max(1, os.cpu_count() or 1))
    return _P, _M


def norm_box(b, W, H):
    return [max(0, min(1000, int(1000 * b[0] / W))), max(0, min(1000, int(1000 * b[1] / H))),
            max(0, min(1000, int(1000 * b[2] / W))), max(0, min(1000, int(1000 * b[3] / H)))]


@torch.no_grad()
def label_words(words, boxes, img):
    """boxes already normalised to 0-1000. -> list of label names per word (argmax, first sub-token)."""
    proc, model = load()
    enc = proc(img, words, boxes=boxes, truncation=True, max_length=512, stride=64,
               return_overflowing_tokens=True, return_tensors="pt", padding="max_length")
    enc.pop("overflow_to_sample_mapping", None)
    n_win = enc["input_ids"].shape[0]
    pix = enc["pixel_values"]
    if isinstance(pix, list):
        pix = torch.stack([x if torch.is_tensor(x) else torch.as_tensor(x) for x in pix])
    if pix.dim() == 3:
        pix = pix.unsqueeze(0)
    if pix.shape[0] != n_win:
        pix = pix[:1].repeat(n_win, 1, 1, 1)
    lab = {}
    for wi in range(n_win):
        out = model(input_ids=enc["input_ids"][wi:wi + 1], attention_mask=enc["attention_mask"][wi:wi + 1],
                    bbox=enc["bbox"][wi:wi + 1], pixel_values=pix[wi:wi + 1])
        pred = out.logits.argmax(-1)[0]
        prev = None
        for ti, w_id in enumerate(enc.word_ids(wi)):
            if w_id is None or w_id == prev:
                prev = w_id
                continue
            prev = w_id
            if w_id not in lab:
                lab[w_id] = model.config.id2label[int(pred[ti])]
    return [lab.get(i, "O") for i in range(len(words))]


def ocr_words_from_vision_json(d):
    """Google Cloud Vision response (as Open Food Facts publishes next to each image) -> (words, boxes_px, W, H)."""
    r = d["responses"][0]
    fa = r.get("fullTextAnnotation")
    if not fa:
        return [], [], None, None
    page = fa["pages"][0]
    W, H = page.get("width"), page.get("height")
    words, boxes = [], []
    for b in page.get("blocks", []):
        for p in b.get("paragraphs", []):
            for w in p.get("words", []):
                txt = "".join(s.get("text", "") for s in w.get("symbols", []))
                if not txt.strip():
                    continue
                vs = w["boundingBox"]["vertices"]
                xs = [v.get("x", 0) for v in vs]; ys = [v.get("y", 0) for v in vs]
                words.append(txt); boxes.append([min(xs), min(ys), max(xs), max(ys)])
    return words, boxes, W, H
