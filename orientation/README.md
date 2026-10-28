# Turning a label photo upright before Etiquette reads it

[Etiquette](https://huggingface.co/FoodClockLabs/Etiquette-1-8B) reads sideways text less reliably than upright
text, and it does not know when it has misread: on one side panel photographed with the text running vertically it
returned carbohydrate 1.9 g for a printed 20 g, with high confidence and a transcript that agreed with itself. Two
of ten phone scans by one contributor showed a wrong digit of this kind. This folder is the fix FoodClock runs in
front of its own reader, as one file with no dependencies beyond Pillow and the `tesseract` command.

## What rotation costs the reader

Measured on the private printed-truth hundred (99 cards, Etiquette 1, same prompt), with every photo turned, or
every second photo turned for "mixed":

| photos | all fields | wrong values | kcal / 100 g | salt | sodium | basis | brand | product name |
|---|---|---|---|---|---|---|---|---|
| upright | 81.0% | 47 | 99.0 | 98.0 | 99.0 | 96.0 | 80.8 | 72.7 |
| turned 90° | 78.0% | 71 | 92.9 | 98.0 | 97.0 | 93.9 | 77.8 | 65.7 |
| mixed | 79.3% | 54 | 96.0 | 99.0 | 97.0 | 93.9 | 83.8 | 69.7 |
| turned 180° | 75.3% | 89 | 94.9 | 97.0 | 98.0 | 89.9 | 68.7 | 64.6 |

The reader is more robust to rotation than the single scan suggested, and the loss it does take has the dangerous
shape: energy per 100 g goes from 99 to 93 agreement at 90 degrees, and the cards it loses return a wrong number,
not a blank. If your photos can arrive sideways, turning them first is cheap insurance. If they cannot, skip this.

## How it decides

1. Tesseract's orientation detection on a 2x upscale (`tesseract photo.png - --psm 0 --dpi 300`): `Rotate: N` and
   an orientation confidence. At typical phone-capture size the upscale is what makes it answer at all.
2. A four-rotation vote: OCR at 0, 90, 180 and 270 degrees (`-l nld+eng --psm 6 tsv`), mean confidence of words of
   three or more characters. The upright rotation wins clearly on a label (33 / 76 / 40 / 37 for a sideways panel).

Rotate only on a clear verdict: the winner at least 45 mean confidence, 10 ahead of the runner-up, eight or more
words, and not contradicted by a Tesseract orientation of confidence 5 or more. Otherwise leave the photo as it is.
On 16 upright exam photos turned three ways (48 trials): 48 put back upright, 0 turned the wrong way; ten further
exam photos with little text were left alone.

Mixed panels, an upright table beside a sideways ingredients strip, follow the dominant block. Photograph one panel
per shot, or hand the reader both rotations.

## Use

```
pip install pillow
apt install tesseract-ocr tesseract-ocr-osd tesseract-ocr-nld tesseract-ocr-eng   # or your languages

python orient_first.py photo.jpg                     # verdict only
python orient_first.py --apply --out upright/ *.jpg  # upright copies, originals untouched
python orient_first.py --langs fra+eng photo.jpg     # vote languages
```

Rotation training, whole photos and mixed composites, is lined up for Etiquette 1.1, and sideways and mixed cards
are being added to the exam so 1.1 can be scored on them.
