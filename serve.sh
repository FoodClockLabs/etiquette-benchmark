#!/usr/bin/env bash
# Start Etiquette as a local server for the exams. Needs llama.cpp's llama-server on your PATH (https://github.com/ggml-org/llama.cpp,
# a recent build with vision support) and the hf CLI (pip install huggingface_hub).
#   ./serve.sh cpu     Q4_K_M quant, no GPU needed: a laptop or any server. Slow (minutes per photo) but it runs anywhere.
#   ./serve.sh gpu     f16 quant on the GPU: ~17 GB of VRAM, a few seconds per product. This is what the README numbers used
#                      (BF16 weights; the f16 GGUF is the same precision in llama.cpp's format).
# Leave it running, then in another terminal:  ./run.sh etiquette-gguf
set -euo pipefail
cd "$(dirname "$0")"; mkdir -p gguf
MM=Etiquette-1-8B.mmproj-f16.gguf
case "${1:-cpu}" in
  cpu) Q=Etiquette-1-8B.Q4_K_M.gguf; NGL=0 ;;
  gpu) Q=Etiquette-1-8B.f16.gguf; NGL=999 ;;
  *) echo "usage: ./serve.sh cpu|gpu"; exit 1 ;;
esac
command -v llama-server >/dev/null || { echo "llama-server not found: install llama.cpp first (brew install llama.cpp, or build it)"; exit 1; }
HF=$(command -v hf || command -v huggingface-cli || true)
[ -n "$HF" ] || { echo "hf CLI not found: pip install huggingface_hub"; exit 1; }
for f in "$Q" "$MM"; do [ -s "gguf/$f" ] || "$HF" download mradermacher/Etiquette-1-8B-GGUF "$f" --local-dir gguf; done
echo "serving $Q on http://127.0.0.1:8080 (ngl=$NGL). Ctrl-C stops it."
exec llama-server -m "gguf/$Q" --mmproj "gguf/$MM" -c 40960 -ngl "$NGL" --jinja --port 8080
