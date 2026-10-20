# Evaluation: an end-to-end VLM label reader vs nutrition-extractor on two annotated sets (weights Apache 2.0)

Hello, we are FoodClock, a small food-diary app built on Open Food Facts data. We have been training an open model that reads a
whole pack photo in one pass, and we wanted to measure it against Nutrisight's `nutrition-extractor` properly before saying
anything about it. This is that measurement, with everything needed to rerun it. We are posting it here because the charter we
wrote for the model says its point is a reader Robotoff could use, and because we owe this project a lot.

## What was compared

- **nutrition-extractor** (LayoutLMv3-large over Google Cloud Vision OCR, `openfoodfacts/nutrition-extractor`), run with the public
  weights and a line-for-line port of Robotoff's `nutrition_extraction.py` post-processing (B-/I- ignored, same regex, same
  energy-unit and duplicate rules). Inference local instead of Triton, same tensors in and out.
- **Etiquette-1-8B** ([FoodClockLabs/Etiquette-1-8B](https://huggingface.co/FoodClockLabs/Etiquette-1-8B), Qwen3-VL-8B-Instruct
  fine-tune, Apache 2.0), given only the photo. No OCR.

Both readers were scored the same way on the 9 nutrients both produce (energy kcal, energy kJ, fat, saturated fat, carbohydrates,
sugars, fiber, proteins, salt): a value agrees within 2 percent or 0.05. Each printed row is agree, differ or missing, and each
non-printed row is agree or invented.

## Set 1: your test split (199 panels, `openfoodfacts/nutrient-detection-layout`)

nutrition-extractor read the dataset's own OCR tokens and boxes, which is its production input. Etiquette read the image.

The labels in this dataset were annotated over OCR tokens, so where the OCR misread a pack, the annotation carries the misreading
("979 kJ/235 kcal" tokenised as "kJ/235" with no value, "1,4 g" tokenised as "1,49", "1 767 kJ" as "1 707"). That is not a
criticism of the annotators, it is what annotating tokens means, but it changes what "correct" is depending on how the labels
are read. So we scored three ways:

| reference | nutrition-extractor | Etiquette-1-8B |
|---|---|---|
| **A**: the labels parsed by Robotoff's own rules (your definition of correct) | **94.5%** | 91.0% |
| **B**: the same labelled tokens read as a person reads them (kcal glued to kJ recovered, thousands marks, trailing 9 as g) | 88.9% | 94.8% |
| **C**: B, then every field either reader still disputed checked against the photo (112 panels, 252 fields) | 88.8% | **97.7%** |

Under A your model wins: it reproduces the tokens it was trained on, misreadings included, and that is exactly what A rewards.
Under C, which is what the pack prints, Etiquette reads 1,621 of 1,659 rows and nutrition-extractor 1,473. Every C override is in
[`panels199/adjudications.jsonl`](https://github.com/FoodClockLabs/etiquette-benchmark/blob/main/panels199/adjudications.jsonl) with the image URL, so the adjudication itself can be checked.

Where each one fails under C:
- nutrition-extractor, 140 missing: mostly kcal values the OCR glued to the kJ (no value survives the regex) and rows voided by the
  duplicate-entity rule when two values share a label on dense tables. 43 differ: rows shifted by one on dense tables, OCR digit
  errors taken as read (36 g for 3,6 g, 1.767 for 1767 kJ). 3 invented.
- Etiquette, 23 missing: 22 are rows printed as "< 0,5 g", which this version does not emit (a design choice we will change).
  12 differ: three rotated labels read one row off, 0,91 read as 0,97, 0 g read as 0,9, 3,3 read as 5,3, 1 g read as 0,1, and
  one kcal read as 12 for 104 on a tiny ham-pack table. 3 invented (a dash and two "not a significant source" footnotes read as 0).

## Set 2: our printed-truth hundred

100 products, human-verified truth of what is printed (not OFF values), scored on the four nutrition rows both readers give there
(basis, energy kcal, salt, sodium). nutrition-extractor read the Vision OCR files you publish next to each image. Coverage was
253 of 253 ticked photos.

| | nutrition rows (400 judgements) | basis | energy kcal | salt | sodium |
|---|---|---|---|---|---|
| nutrition-extractor | 78.8% | 86 | 68 | 82 | 79 |
| Etiquette-1-8B | 96.2% | 94 | 97 | 98 | 96 |

The gap is widest exactly where OCR is weakest: 13 of the 100 products had no Latin-script "kcal" in the OCR at all (Arabic
tables, OCR that missed the table), and the reader never saw them. On the whole card (names, brands, quantity, basis, three
nutrients) Etiquette scores 83.0. nutrition-extractor does not read those fields, so there is no comparison there.

## What this does and does not say

- It says an end-to-end reader on the photo is now more accurate than OCR plus token classification on what packs print, on
  your test set and on ours.
- It does not say nutrition-extractor is a bad model: on its own tokens it is excellent, and it runs on a CPU after one OCR call.
- The costs are different. Etiquette needs a GPU: about a second a photo on a consumer card, roughly 0.06 cent of electricity,
  no OCR bill. A Q4 GGUF runs on a laptop at some loss (79.9 on our full card against 83.0 for BF16, the nutrition rows hold up better).
- It reads what is printed. It does not compute, convert or infer values, so "salt from sodium" and per-serving-to-100g are
  deliberately not done.

## What we offer

- The weights, Apache 2.0: [huggingface.co/FoodClockLabs/Etiquette-1-8B](https://huggingface.co/FoodClockLabs/Etiquette-1-8B).
  GGUF quants for laptops and CPUs: [mradermacher/Etiquette-1-8B-GGUF](https://huggingface.co/mradermacher/Etiquette-1-8B-GGUF)
  (Q4_K_M to f16, with the mmproj), and a stdlib runner (`run_gguf.py` in the model repo), so it runs without our stack.
  Everything we publish lives under [huggingface.co/FoodClockLabs](https://huggingface.co/FoodClockLabs).
- Both evaluation sets with scorers and reply files: [FoodClockLabs/etiquette-benchmark](https://github.com/FoodClockLabs/etiquette-benchmark),
  where `./run.sh score` reproduces every table in seconds and `./serve.sh cpu|gpu` runs Etiquette on your own machine, and the
  printed-truth dataset
  [FoodClockLabs/etiquette-printed-truth](https://huggingface.co/datasets/FoodClockLabs/etiquette-printed-truth) (CC BY-SA).
- An integration guide in the benchmark repo ([INTEGRATION.md](https://github.com/FoodClockLabs/etiquette-benchmark/blob/main/INTEGRATION.md)): how to serve the model (BF16 on one GPU, or the GGUF with
  llama-server), the exact request and reply shapes, a worked mapping from Etiquette's reading to Robotoff's
  `NutrientPrediction` fields, throughput and memory figures, and the failure modes to expect (rotated labels, "< 0,5 g" rows).
  Everything a Robotoff contributor needs to wire a predictor without us in the loop.
- The printed-truth hundred as an extra test set for Nutrisight, if you want it.
- Questions answered here in the thread.

Happy to be corrected on anything in the method, here in the thread.

*Posted as a GitHub Discussion (Show and tell) on openfoodfacts/openfoodfacts-ai. This file is the same text.*
