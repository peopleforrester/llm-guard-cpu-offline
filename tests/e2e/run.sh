#!/usr/bin/env bash
# ABOUTME: End-to-end run: installs the API the way the Dockerfile does (CPU torch first), fetches the
# ABOUTME: pinned weights, then scans in a network namespace with no network, as a default-deny pod does.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$REPO_ROOT/.e2e"
VENV="$WORK/venv"
WEIGHTS="$WORK/models/prompt-injection"

for tool in uv unshare; do
  command -v "$tool" >/dev/null || { echo "E2E needs $tool on PATH" >&2; exit 1; }
done
unshare -rn true || {
  echo "E2E needs unprivileged user and network namespaces (unshare -rn) to run with no network" >&2
  exit 1
}

TORCH_PIN="$(grep -o 'torch==[0-9][0-9.]*' "$REPO_ROOT/Dockerfile")"
[ "$(wc -l <<<"$TORCH_PIN")" -eq 1 ] || { echo "Expected one torch pin in Dockerfile" >&2; exit 1; }

echo "[1/4] Python 3.12 environment in $VENV"
[ -x "$VENV/bin/python" ] || uv venv --quiet --python 3.12 "$VENV"

echo "[2/4] $TORCH_PIN from the PyTorch CPU index, then src[cpu], as the Dockerfile installs them"
uv pip install --python "$VENV/bin/python" "$TORCH_PIN" --index-url https://download.pytorch.org/whl/cpu
uv pip install --python "$VENV/bin/python" "$REPO_ROOT/src[cpu]" -r "$REPO_ROOT/tests/e2e/requirements.txt"
"$VENV/bin/python" - <<'EOF'
import importlib.metadata as md
cuda = sorted(d.metadata["Name"] for d in md.distributions() if d.metadata["Name"].startswith("nvidia-"))
if cuda:
    raise SystemExit(f"CUDA packages resolved into a CPU-only install: {cuda}")
EOF

echo "[3/4] Weights from the model image pinned in Dockerfile"
"$VENV/bin/python" -I "$REPO_ROOT/tests/e2e/fetch_weights.py" "$WEIGHTS"

echo "[4/4] Scanning with no network"
cd "$REPO_ROOT"
exec unshare -rn env \
  WIB_PI_MODEL_DIR="$WEIGHTS" \
  HF_HUB_OFFLINE=1 \
  TRANSFORMERS_OFFLINE=1 \
  HF_DATASETS_OFFLINE=1 \
  "$VENV/bin/python" -m pytest tests/e2e "$@"
