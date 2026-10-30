#!/usr/bin/env python3
"""orient_first: turn a label photo upright before a reader sees it.

Etiquette reads sideways text less reliably than upright text and does not know when it has misread (see the
"Sideways text" limit on the model card). This is a property of the base vision model: training Etiquette on rotated
photos (the 1.1 candidate, October 2026) did not close the gap, so the remedy stays in front of the reader, where it
is cheap and measurable. Printed text has a detectable orientation, and two cheap checks agree on it: Tesseract's
orientation detection on a 2x upscale, and a four-rotation OCR vote. This script applies both and rotates only on a
clear, agreeing verdict; a photo with too little text, or a close vote, is left exactly as it is.

Needs: Python 3.9+, Pillow, and the `tesseract` command (5.x) with the `osd` data and the languages you pass
(default nld+eng: `apt install tesseract-ocr tesseract-ocr-osd tesseract-ocr-nld tesseract-ocr-eng`).

  python orient_first.py photo.jpg                 print the verdict, change nothing
  python orient_first.py --apply photo.jpg ...     rotate the files in place (EXIF applied first, JPEG quality 95)
  python orient_first.py --apply --out DIR *.jpg   write upright copies to DIR, originals untouched
  python orient_first.py --langs fra+eng photo.jpg OCR languages for the vote (Tesseract names, + separated)
  python orient_first.py --blocks DIR photo.jpg    worst case, text in several orientations on one photo (an upright
                                                   table beside a sideways ingredients strip): find each text region,
                                                   give it its own verdict, cut it out, turn it upright, one crop per
                                                   region in DIR. Send the crops as the reader's images (it takes
                                                   several per reading).

Whole-photo verdict, measured on 16 upright nutrition-label photos from the Etiquette exam, each turned 90, 180 and
270 degrees (48 trials): 48 put back upright, 0 turned the wrong way. Ten further exam photos with little text were
left alone. Cost: a few seconds per photo on one CPU core; --blocks roughly three times that.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image, ImageOps

MIN_WORDS = 8          # fewer readable words than this: no verdict
MIN_CONF = 45.0        # the winning rotation's mean word confidence must reach this
MARGIN = 10.0          # ... and lead the runner-up by this much
OSD_TRUST = 5.0        # a Tesseract orientation at least this confident may veto a contradicting vote
REGION_GAP = 0.015     # --blocks: words closer than this share of the photo's short side belong to one region
REGION_PAD = 0.03      # --blocks: margin around a crop, as a share of the photo's width/height


def _tesseract(path, *args):
    try:
        return subprocess.run(["tesseract", path, "-", *args], capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _words(tsv):
    """Tesseract tsv -> [(left, top, width, height, conf)] for readable words of three or more characters."""
    out = []
    for line in tsv.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12 or parts[0] != "5" or len(parts[11].strip()) < 3:
            continue
        try:
            conf = float(parts[10])
            left, top, width, height = (int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9]))
        except ValueError:
            continue
        if conf > 0:
            out.append((left, top, width, height, conf))
    return out


def judge_image(im, langs="nld+eng"):
    """The verdict for a PIL image (EXIF already applied). Return (rotate_ccw_degrees, how, detail); 0 = leave it."""
    im = im.convert("L")
    big = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    tmp = tempfile.mktemp(suffix=".png")
    big.save(tmp)
    try:
        osd = _tesseract(tmp, "--psm", "0", "--dpi", "300")
        m_rot = re.search(r"Rotate:\s*(\d+)", osd)
        m_conf = re.search(r"Orientation confidence:\s*([\d.]+)", osd)
        osd_cw = int(m_rot.group(1)) if m_rot else None          # degrees clockwise Tesseract wants applied
        osd_conf = float(m_conf.group(1)) if m_conf else 0.0
        votes = {}
        for rot in (0, 90, 180, 270):
            t = tempfile.mktemp(suffix=".png")
            big.rotate(rot, expand=True).save(t)
            confs = [w[4] for w in _words(_tesseract(t, "-l", langs, "--psm", "6", "--dpi", "300", "tsv"))]
            votes[rot] = (sum(confs) / len(confs) if confs else 0.0, len(confs))
            os.unlink(t)
    finally:
        os.unlink(tmp)
    best = max(votes, key=lambda r: votes[r][0])
    best_conf, n_words = votes[best]
    runner = max((votes[r][0] for r in votes if r != best), default=0.0)
    osd_ccw = (360 - osd_cw) % 360 if osd_cw is not None else None
    detail = "osd=%s(conf %.1f) vote=%s" % (
        osd_ccw, osd_conf, " ".join("%d:%.0f/%d" % (r, votes[r][0], votes[r][1]) for r in (0, 90, 180, 270)))
    if n_words < MIN_WORDS or best_conf < MIN_CONF:
        return 0, "unsure", detail
    if best_conf < runner + MARGIN:
        return 0, "close", detail
    if osd_ccw is not None and osd_conf >= OSD_TRUST and osd_ccw != best:
        return 0, "disagree", detail
    return best, "vote" + ("+osd" if osd_ccw == best else ""), detail


def judge(path, langs="nld+eng"):
    """Return (rotate_ccw_degrees, how, detail) for a photo file. 0 means leave the photo as it is."""
    return judge_image(ImageOps.exif_transpose(Image.open(path)), langs)


def apply(path, rot, out_dir=None):
    im = ImageOps.exif_transpose(Image.open(path)).rotate(rot, expand=True)
    dst = os.path.join(out_dir, os.path.basename(path)) if out_dir else path
    im.convert("RGB").save(dst, "JPEG", quality=95)
    return dst


# ---------------------------------------------------------------------------------------------------------------
# --blocks: one photo, several orientations. Finding text and judging its orientation are kept apart. Text is found
# by OCR at all four rotations (a sideways word is still a word box at some rotation); the boxes are mapped back onto
# the photo and words that lie close together form a region. Each region is then cut out and given the same
# whole-photo verdict as above, on its own pixels, with the same thresholds: that per-crop vote is the part that was
# measured (48 of 48), so a region never gets an orientation from a weaker rule. A region whose vote is unclear
# follows the whole photo's verdict. Nothing is interpreted: the crops are the same pixels, the right way up.

def _unrotate(box, rot, W, H):
    """Box (l,t,r,b) in an image rotated `rot` degrees counter-clockwise (size W x H after rotation) -> the same box in
    the unrotated image."""
    l, t, r, b = box
    if rot == 0:
        pts = [(l, t), (r, b)]
    elif rot == 90:          # counter-clockwise quarter turn: x' = y, y' = w - x  (w = original width = H here)
        pts = [(H - t, l), (H - b, r)]       # so x = H - y', y = x'
    elif rot == 180:
        pts = [(W - l, H - t), (W - r, H - b)]
    else:                    # 270 (a clockwise quarter turn): x' = h - y, y' = x  (h = original height = W here)
        pts = [(t, W - l), (b, W - r)]       # so x = y', y = W - x'
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _touch(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _regions(im, langs):
    """Text regions of a photo: [(box, n_words)] in photo pixels, from word boxes found at every rotation."""
    g = im.convert("L")
    big = g.resize((g.width * 2, g.height * 2), Image.LANCZOS)
    boxes = []
    for rot in (0, 90, 180, 270):
        rotated = big.rotate(rot, expand=True)
        W, H = rotated.size
        t = tempfile.mktemp(suffix=".png")
        rotated.save(t)
        try:
            # sparse text (11) finds words anywhere on a photo; one block (6) finds the rows of a table; automatic
            # page segmentation (3) finds next to nothing on a phone photo with a border, so it is not used
            words = (_words(_tesseract(t, "-l", langs, "--psm", "11", "--dpi", "300", "tsv"))
                     + _words(_tesseract(t, "-l", langs, "--psm", "6", "--dpi", "300", "tsv")))
        finally:
            os.unlink(t)
        for left, top, width, height, _conf in words:
            box = _unrotate((left, top, left + width, top + height), rot, W, H)
            boxes.append(tuple(v / 2.0 for v in box))
    if not boxes:
        return []
    gap = REGION_GAP * min(im.width, im.height)
    grown = [(l - gap, t - gap, r + gap, b + gap) for (l, t, r, b) in boxes]
    parent = list(range(len(boxes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(grown)):
        for j in range(i + 1, len(grown)):
            if _touch(grown[i], grown[j]):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    groups = {}
    for i, box in enumerate(boxes):
        g_ = groups.setdefault(find(i), [box[0], box[1], box[2], box[3], 0])
        g_[0] = min(g_[0], box[0]); g_[1] = min(g_[1], box[1]); g_[2] = max(g_[2], box[2]); g_[3] = max(g_[3], box[3]); g_[4] += 1
    # a word is seen up to four times (once per rotation), so the count threshold is per rotation on average
    return [((g_[0], g_[1], g_[2], g_[3]), g_[4]) for g_ in groups.values() if g_[4] >= MIN_WORDS * 2]


def blocks(path, langs="nld+eng", whole_rot=0):
    """Return [{rot, how, n, box, detail}] per text region, box in the photo's own pixels (EXIF applied), rot the
    counter-clockwise turn that makes the region upright (the whole photo's verdict when the region's own is unclear)."""
    src = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    pad_x, pad_y = src.width * REGION_PAD, src.height * REGION_PAD
    found = []
    for box, n in sorted(_regions(src, langs), key=lambda r: (r[0][1], r[0][0])):
        crop = src.crop((max(0, int(box[0] - pad_x)), max(0, int(box[1] - pad_y)),
                         min(src.width, int(box[2] + pad_x)), min(src.height, int(box[3] + pad_y))))
        rot, how, detail = judge_image(crop, langs)
        if how in ("unsure", "close", "disagree"):
            rot, how = whole_rot, how + ", follows the whole photo"
        found.append({"rot": rot, "how": how, "n": n, "box": box, "detail": detail})
    return found


def cut_blocks(path, found, out_dir):
    """Write one upright crop per region: <stem>_block<i>_rot<rot>.jpg. Returns the written paths."""
    src = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    pad_x, pad_y = src.width * REGION_PAD, src.height * REGION_PAD
    stem = os.path.splitext(os.path.basename(path))[0]
    out = []
    for i, b in enumerate(found, 1):
        l, t, r, bt = b["box"]
        crop = src.crop((max(0, int(l - pad_x)), max(0, int(t - pad_y)), min(src.width, int(r + pad_x)), min(src.height, int(bt + pad_y))))
        dst = os.path.join(out_dir, "%s_block%d_rot%d.jpg" % (stem, i, b["rot"]))
        crop.rotate(b["rot"], expand=True).save(dst, "JPEG", quality=95)
        out.append(dst)
    return out


def main():
    ap = argparse.ArgumentParser(description="turn label photos upright before reading them")
    ap.add_argument("photos", nargs="+")
    ap.add_argument("--apply", action="store_true", help="rotate (in place, or into --out)")
    ap.add_argument("--out", default="", help="directory for upright copies (with --apply)")
    ap.add_argument("--langs", default="nld+eng", help="Tesseract languages for the vote")
    ap.add_argument("--blocks", default="", metavar="DIR", help="cut each text region out upright into DIR (mixed orientations)")
    a = ap.parse_args()
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    if a.blocks:
        os.makedirs(a.blocks, exist_ok=True)
    rc = 0
    for p in a.photos:
        try:
            rot, how, detail = judge(p, a.langs)
        except Exception as e:  # a broken file is reported, never fatal for the batch
            print("%s: error %s" % (p, e)); rc = 1; continue
        where = ""
        if rot and a.apply:
            where = " -> " + apply(p, rot, a.out or None)
        print("%s: rotate %d (%s) %s%s" % (p, rot, how, detail, where))
        if a.blocks:
            try:
                found = blocks(p, a.langs, whole_rot=rot)
                written = cut_blocks(p, found, a.blocks)
            except Exception as e:
                print("  blocks: error %s" % e); rc = 1; continue
            rots = sorted({b["rot"] for b in found})
            print("  blocks: %d region(s), orientation(s) %s%s" % (len(found), rots or "-",
                  "" if len(rots) <= 1 else "  <- MIXED: read the crops, not the whole photo"))
            for b, dst in zip(found, written):
                print("    rot %3d (%s)  box %s  %s -> %s" % (b["rot"], b["how"], tuple(int(v) for v in b["box"]), b["detail"], dst))
    return rc


if __name__ == "__main__":
    sys.exit(main())
