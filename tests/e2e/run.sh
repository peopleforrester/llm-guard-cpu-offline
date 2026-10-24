#!/usr/bin/env bash
# ABOUTME: End-to-end run: installs the API the way the Dockerfile does and scans it with no network, then
# ABOUTME: builds the image itself and scans through it under --network none, as a default-deny pod does.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$REPO_ROOT/.e2e"
VENV="$WORK/venv"
WEIGHTS="$WORK/models/prompt-injection"
ZS_WEIGHTS="$WORK/models/zero-shot"
IMAGE="llm-guard-cpu-offline:e2e"

for tool in uv unshare docker; do
  command -v "$tool" >/dev/null || { echo "E2E needs $tool on PATH" >&2; exit 1; }
done
unshare -rn true || {
  echo "E2E needs unprivileged user and network namespaces (unshare -rn) to run with no network" >&2
  exit 1
}
docker info >/dev/null || {
  echo "E2E needs a container runtime that can build and run images: 'docker info' failed" >&2
  exit 1
}

TORCH_PIN="$(grep -o 'torch==[0-9][0-9.]*' "$REPO_ROOT/Dockerfile")"
[ "$(wc -l <<<"$TORCH_PIN")" -eq 1 ] || { echo "Expected one torch pin in Dockerfile" >&2; exit 1; }

echo "[1/6] Python 3.12 environment in $VENV"
[ -x "$VENV/bin/python" ] || uv venv --quiet --python 3.12 "$VENV"

echo "[2/6] $TORCH_PIN from the PyTorch CPU index, then src[cpu] with overrides.txt, as the Dockerfile installs them"
uv pip install --python "$VENV/bin/python" "$TORCH_PIN" --index-url https://download.pytorch.org/whl/cpu
uv pip install --python "$VENV/bin/python" --override "$REPO_ROOT/overrides.txt" "$REPO_ROOT/src[cpu]" -r "$REPO_ROOT/tests/e2e/requirements.txt"
"$VENV/bin/python" - <<'EOF'
import importlib.metadata as md
cuda = sorted(d.metadata["Name"] for d in md.distributions() if d.metadata["Name"].startswith("nvidia-"))
if cuda:
    raise SystemExit(f"CUDA packages resolved into a CPU-only install: {cuda}")
EOF

echo "[3/6] Weights from the model image pinned in Dockerfile, and the zero-shot files model-zero-shot/ pins"
"$VENV/bin/python" -I "$REPO_ROOT/tests/e2e/fetch_weights.py" "$WEIGHTS"
"$VENV/bin/python" -I "$REPO_ROOT/tests/e2e/fetch_zero_shot.py" "$ZS_WEIGHTS"

echo "[4/6] Scanning with no network"
cd "$REPO_ROOT"
unshare -rn env \
  WIB_PI_MODEL_DIR="$WEIGHTS" \
  WIB_ZS_MODEL_DIR="$ZS_WEIGHTS" \
  HF_HUB_OFFLINE=1 \
  TRANSFORMERS_OFFLINE=1 \
  HF_DATASETS_OFFLINE=1 \
  "$VENV/bin/python" -m pytest tests/e2e "$@"

echo "[5/6] Building the image as $IMAGE"
docker build --tag "$IMAGE" "$REPO_ROOT"

echo "[6/6] Scanning through the image under --network none"
E2E_IMAGE="$IMAGE" "$VENV/bin/python" -m pytest tests/image "$@"
