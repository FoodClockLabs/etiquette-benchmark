# Etiquette benchmark

Two exams, two readers of nutrition labels, every number reproducible from the files in this repository.

- **Etiquette-1-8B** ([FoodClockLabs/Etiquette-1-8B](https://huggingface.co/FoodClockLabs/Etiquette-1-8B), Apache 2.0): a Qwen3-VL-8B
  fine-tune that reads the pack photo directly. No OCR. GGUF quants for laptops: [mradermacher/Etiquette-1-8B-GGUF](https://huggingface.co/mradermacher/Etiquette-1-8B-GGUF).
- **nutrition-extractor** ([openfoodfacts/nutrition-extractor](https://huggingface.co/openfoodfacts/nutrition-extractor), CC BY-NC-SA, research use here):
  Open Food Facts' production reader, LayoutLMv3 over Google Cloud Vision OCR, with Robotoff's post-processing ported line for line.

## Results

**Exam 1: Open Food Facts' own 199 test panels** (`openfoodfacts/nutrient-detection-layout`, test split). Nine nutrients at value
level, printed basis, a value agrees within 2% or 0.05. The labels were annotated over OCR tokens, so where the OCR misread a pack
the label carries the misreading. Three ways of reading the same labels:

| reference | nutrition-extractor | Etiquette-1-8B |
|---|---|---|
| A: the labels parsed by Robotoff's own rules | **94.5%** | 91.0% |
| B: the same labelled tokens read as a person reads them | 88.9% | 94.8% |
| C: B, then every disputed field checked against the photo | 88.8% | **97.7%** |

**Exam 2: the printed-truth hundred** (`holdout100/cards.jsonl`, human-verified truth of what is printed). The four nutrition rows
both readers give (basis, energy kcal, salt, sodium):

| | nutrition rows | basis | energy kcal | salt | sodium |
|---|---|---|---|---|---|
| nutrition-extractor | 78.8% | 86 | 68 | 82 | 79 |
| Etiquette-1-8B | 96.2% | 94 | 97 | 98 | 96 |

On the whole card (product name, brand, net quantity, basis, three nutrients) Etiquette scores 83.0; nutrition-extractor does not read
the text fields, so there is no whole-card comparison.

## Run it yourself: CPU or GPU

**Just the scoring, no model** (seconds, standard library only):

    git clone https://github.com/FoodClockLabs/etiquette-benchmark && cd etiquette-benchmark
    ./run.sh score

**Etiquette on a CPU** (a laptop will do, the Q4_K_M quant, minutes per photo). Two terminals:

    ./serve.sh cpu              # downloads the GGUF files (~5 GB) and starts llama-server
    ./run.sh etiquette-gguf     # reads the 199 panels, writes panels199/predictions/etiquette-gguf.jsonl, then score it:
    python3 panels199/score.py panels199/predictions/etiquette-gguf.jsonl

**Etiquette on a GPU** (~17 GB VRAM, seconds per product, the f16 quant = the precision the tables used):

    ./serve.sh gpu
    ./run.sh etiquette-gguf

**nutrition-extractor** (their model, CPU is fine, ~15 minutes per exam, CC BY-NC-SA so research use only):

    ./run.sh setup
    ./run.sh theirs

`serve.sh` needs llama.cpp's `llama-server` on your PATH (`brew install llama.cpp`, or build it) and the `hf` CLI
(`pip install huggingface_hub`). Try `--limit 10` on `run_etiquette_gguf.py` first to see it work before the full run.

## Reproduce the tables (seconds, no model, standard library)

    git clone https://github.com/FoodClockLabs/etiquette-benchmark && cd etiquette-benchmark
    ./run.sh score

## Re-run the readers (optional)

    ./run.sh setup            # venv, light requirements, the 199-panel parquet
    ./run.sh theirs           # nutrition-extractor on both exams, CPU is fine, ~15 min each
    ./run.sh etiquette-gguf   # Etiquette on the 199 panels through a llama-server you start (see panels199/run_etiquette_gguf.py)

Any reader can sit either exam: write one line per card `{"code": ..., "reading": {"nutriments": {"fat_100g": ..}, "basis": {"per": "100g"}}}`
and pass the file to `panels199/score.py` or `holdout100/score.py`.

## Layout

    common/robotoff_port.py        Robotoff's post-processing, ported (AGPL-3.0, see NOTICE)
    common/layoutlm_runner.py      nutrition-extractor run locally (no Triton)
    common/judge.py                the number test both exams share
    holdout100/cards.jsonl         the hundred cards: photos (Open Food Facts URLs) and the printed truth per field
    holdout100/score.py            the scorer from the model card (whole card)
    holdout100/compare.py          the nutrition-row comparison
    holdout100/replies/            run13.jsonl (Etiquette), nutrition-extractor.jsonl
    panels199/build_truth.py       truth A and B from the dataset's labels
    panels199/adjudications.jsonl  truth C: every override from looking at the photo, with the image URL
    panels199/score.py             A, B and C for any predictions file
    panels199/predictions/         nutrition-extractor.json, etiquette-run13.jsonl
    panels199/disagreements_C.json every remaining disagreement of either reader, with the image URL
    serve.sh                       start Etiquette locally, cpu or gpu, for the runs above
    INTEGRATION.md                 how to serve Etiquette and map its reading to Robotoff's fields
    REPORT.md                      the write-up as posted to Open Food Facts

## Where each reader fails (truth C)

nutrition-extractor, 140 missing: kcal values the OCR glued to the kJ ("979 kJ/235 kcal" tokenised as "kJ/235", no value survives
the regex) and rows voided by the duplicate-entity rule on dense tables. 43 differ: rows shifted by one on dense tables, OCR digit
errors taken as read. 3 invented.

Etiquette, 23 missing: 22 are rows printed as "< 0,5 g", which this version does not emit. 12 differ: three rotated labels read one
row off, 0,91 read as 0,97, 0 g as 0,9, 3,3 as 5,3, 1 g as 0,1, one kcal read as 12 for 104 on a tiny table. 3 invented: a dash and
two "not a significant source" footnotes read as 0. All listed by barcode in `panels199/disagreements_C.json`.

## Licences

Apache 2.0 for this repository, except `common/robotoff_port.py` (AGPL-3.0, a port of Robotoff). Data: see NOTICE.
