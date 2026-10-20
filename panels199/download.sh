#!/usr/bin/env bash
# Fetch the test split of openfoodfacts/nutrient-detection-layout (CC BY-SA) into data/.
set -euo pipefail
cd "$(dirname "$0")"; mkdir -p data
python3 - <<'PY'
from huggingface_hub import hf_hub_download
p = hf_hub_download("openfoodfacts/nutrient-detection-layout", "data/test-00000-of-00001.parquet", repo_type="dataset", local_dir=".")
print("got", p)
PY
echo "data/test-00000-of-00001.parquet ready"
