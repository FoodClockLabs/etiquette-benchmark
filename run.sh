#!/usr/bin/env bash
# One entry point. Everything scores from the files in this repository without any model; the model runs are optional.
#   ./run.sh score              the headline tables, both exams, from the stored replies (standard library, seconds)
#   ./run.sh setup              python venv + the light requirements; fetches the 199-panel parquet
#   ./run.sh theirs             re-run nutrition-extractor on both exams (CPU ok, ~15 min each; CC BY-NC-SA, research use)
#   ./run.sh etiquette-gguf     re-run Etiquette on the 199 panels through a llama-server you started (see panels199/run_etiquette_gguf.py)
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-$( [ -x venv/bin/python ] && echo venv/bin/python || echo python3 )}
case "${1:-score}" in
  score)
    echo "== Printed-truth hundred (holdout100): the whole card, as on the model card"
    for f in holdout100/replies/*.jsonl; do echo "-- $f"; $PY holdout100/score.py holdout100/cards.jsonl "$f" | head -1; done
    echo; echo "== Printed-truth hundred: the four nutrition rows both readers give"
    $PY holdout100/compare.py holdout100/replies/nutrition-extractor.jsonl holdout100/replies/run13.jsonl
    echo; echo "== Open Food Facts' 199 test panels: nine nutrients, three truths"
    $PY panels199/score.py panels199/predictions/nutrition-extractor.json panels199/predictions/etiquette-run13.jsonl ;;
  setup)
    python3 -m venv venv && venv/bin/pip install -q -r requirements.txt && bash panels199/download.sh ;;
  theirs)
    $PY -m pip install -q -r requirements-nutrition-extractor.txt
    $PY panels199/run_nutrition_extractor.py && $PY holdout100/run_nutrition_extractor.py ;;
  etiquette-gguf)
    $PY panels199/run_etiquette_gguf.py "${@:2}" ;;
  *) echo "usage: ./run.sh score|setup|theirs|etiquette-gguf"; exit 1 ;;
esac
