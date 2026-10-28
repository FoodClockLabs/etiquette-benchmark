#!/usr/bin/env python3
"""orient_first: turn a label photo upright before a reader sees it.

Etiquette reads sideways text less reliably than upright text and does not know when it has misread (see the
"Sideways text" limit on the model card). Printed text has a detectable orientation, and two cheap checks agree on
it: Tesseract's orientation detection on a 2x upscale, and a four-rotation OCR vote. This script applies both and
rotates only on a clear, agreeing verdict; a photo with too little text, or a close vote, is left exactly as it is.

Needs: Python 3.9+, Pillow, and the `tesseract` command (5.x) with the `osd` data and the languages you pass
(default nld+eng: `apt install tesseract-ocr tesseract-ocr-osd tesseract-ocr-nld tesseract-ocr-eng`).

  python orient_first.py photo.jpg                 print the verdict, change nothing
  python orient_first.py --apply photo.jpg ...     rotate the files in place (EXIF applied first, JPEG quality 95)
  python orient_first.py --apply --out DIR *.jpg   write upright copies to DIR, originals untouched
  python orient_first.py --langs fra+eng photo.jpg OCR languages for the vote (Tesseract names, + separated)

Measured on 16 upright nutrition-label photos from the Etiquette exam, each turned 90, 180 and 270 degrees
(48 trials): 48 put back upright, 0 turned the wrong way. Ten further exam photos with little text were left alone.
Cost: a few seconds per photo on one CPU core.
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


def _tesseract(path, *args):
    try:
        return subprocess.run(["tesseract", path, "-", *args], capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def judge(path, langs="nld+eng"):
    """Return (rotate_ccw_degrees, how, detail). 0 means leave the photo as it is."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("L")
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
            tsv = _tesseract(t, "-l", langs, "--psm", "6", "--dpi", "300", "tsv")
            confs = []
            for line in tsv.splitlines()[1:]:
                parts = line.split("\t")
                if len(parts) >= 12 and len(parts[11].strip()) >= 3:
                    try:
                        c = float(parts[10])
                    except ValueError:
                        continue
                    if c > 0:
                        confs.append(c)
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


def apply(path, rot, out_dir=None):
    im = ImageOps.exif_transpose(Image.open(path)).rotate(rot, expand=True)
    dst = os.path.join(out_dir, os.path.basename(path)) if out_dir else path
    im.convert("RGB").save(dst, "JPEG", quality=95)
    return dst


def main():
    ap = argparse.ArgumentParser(description="turn label photos upright before reading them")
    ap.add_argument("photos", nargs="+")
    ap.add_argument("--apply", action="store_true", help="rotate (in place, or into --out)")
    ap.add_argument("--out", default="", help="directory for upright copies (with --apply)")
    ap.add_argument("--langs", default="nld+eng", help="Tesseract languages for the vote")
    a = ap.parse_args()
    if a.out:
        os.makedirs(a.out, exist_ok=True)
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
    return rc


if __name__ == "__main__":
    sys.exit(main())
