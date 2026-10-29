# ABOUTME: LLM Guard API image: multi-stage, CPU-only torch, vendored upstream source, and the
# ABOUTME: PromptInjection classifier baked in with Hugging Face offline so a default-deny cluster scans.
#
# THREE PROBLEMS THIS IMAGE SOLVES
#
# 1. Offline scanning (#241). The upstream image lazy-loads
#    protectai/deberta-v3-base-prompt-injection-v2 from huggingface.co on the FIRST scan. In the
#    workshop that first scan is Challenge 6, which every attendee reaches AFTER applying Challenge 1's
#    default-deny NetworkPolicy, so the download fails and guard-proxy (fail-closed) refuses every
#    prompt for the rest of the lab. A cached Hub snapshot is not enough: the API forces use_onnx=True
#    and optimum's ONNX loader lists the repo tree over the network even with HF_HUB_OFFLINE set. The
#    scanner's `model_path` parameter loads from a plain directory with local_files_only and never
#    touches the Hub, so the model lives at /home/user/models/prompt-injection with the tokenizer files
#    and model.onnx at the TOP level (model_path also clears the onnx subfolder), and the scanners.yml
#    in gitops/ai-layer/resources.yaml points PromptInjection at it.
#
# 2. Weight (#413). The build before this one derived FROM laiyer/llm-guard-api and measured 4,211 MB
#    compressed, of which 2,748 MB was fifteen NVIDIA CUDA packages and 555 MB was the CUDA-linked
#    torch build. This fleet runs t3.2xlarge nodes with no GPU, and llm_guard/transformers_helpers.py
#    selects CUDAExecutionProvider only when a GPU is present, so that payload was never loaded.
#    Deleting it in a later layer could not have helped, because a layer cannot remove bytes an earlier
#    layer added, which is why this builds from python:3.12-slim rather than wrapping another image.
#    The fix is a resolver change, not a source change: the `[cpu]` extra only selects the optimum
#    variant and does NOT control which torch build is resolved, while the default PyPI torch wheel
#    declares the NVIDIA wheels as hard dependencies. Installing torch from PyTorch's CPU index first
#    satisfies llm-guard's `torch>=2.4.0` and keeps the rest of the resolve away from CUDA.
#
# 3. The compiler in a security scanner (#415). build-essential is needed to BUILD and not to RUN, and
#    it drags in linux-libc-dev, whose CVE-2026-43185 (CRITICAL, no fix available) was the last
#    critical finding in the image. For the same layer reason as above, an apt-get purge later in the
#    file removes nothing: pip's install sits in a layer between them. So the compiler lives in a
#    builder stage and never reaches the runtime image, which carries only libgomp1.
#
# 4. The Hugging Face dependency (#414). The build used to download the classifier from
#    huggingface.co. Runtime was already safe, since the weights are baked in and the Hub is
#    switched off, but a REBUILD was not, and the archive notice covers the models as well as the
#    code. The weights now come from model/ in our own registry, pinned by digest.
#
# WHY THE SOURCE IS VENDORED
#
# src/ holds llm_guard_api at tag v0.3.16, copied verbatim from protectai/llm-guard, MIT, with its
# LICENSE alongside as LICENSE.upstream. Protect AI archived that repository on 2026-07-08 after Palo
# Alto Networks acquired them, so building from a clone of it is a dependency on somebody else's
# archived repository staying reachable. 40 KB of Python removes that. See #414 for the same argument
# applied to the model weights, which are now mirrored too.
#
# Build and push (from this repo's root):
#   docker build --pull --no-cache -t ghcr.io/peopleforrester/watch-it-burn:llm-guard-0.3.16-cpu.5 .
#   docker push ghcr.io/peopleforrester/watch-it-burn:llm-guard-0.3.16-cpu.5

# ---------------------------------------------------------------------------------------------------
# The classifier weights, from our own mirror. A scratch image holding files and nothing executable.
# Re-pin with `docker buildx imagetools inspect <ref>` when the model revision changes.
# ---------------------------------------------------------------------------------------------------
ARG MODEL_IMAGE=ghcr.io/peopleforrester/watch-it-burn:llm-guard-model-90c9989b@sha256:a8a678af4326562aaa265b718dc9aaa172e9940f40545eca174b0737a63ec8e4
# The BanTopics zero-shot weights (#2, #15): deberta-v3-base-zeroshot-v2.0 at revision 8e7e5af5, MIT,
# published from model-zero-shot/ and pinned by digest the same way. Declared here because an ARG a
# FROM names must come before the first FROM.
ARG ZERO_SHOT_IMAGE=ghcr.io/peopleforrester/watch-it-burn:llm-guard-model-zeroshot-8e7e5af5@sha256:c01ca9644bb1c93601a1b333339a3a2aacd63a287e057a4a124f5f08b33c7ca8
FROM ${MODEL_IMAGE} AS model
FROM ${ZERO_SHOT_IMAGE} AS zero-shot

# ---------------------------------------------------------------------------------------------------
# Builder: compilers and the full install. None of this stage ships.
# ---------------------------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# uv applies overrides.txt below, which pip cannot. Installed as root into the system Python, outside
# the venv, so it stays in this stage.
RUN pip install --no-cache-dir --root-user-action=ignore uv==0.13.6

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# A virtualenv at a fixed path is what makes the runtime stage a plain directory copy. It is built as
# the same uid that will run it, so no ownership rewrite is needed on the way across.
ENV VIRTUAL_ENV=/home/user/.venv \
    PATH=/home/user/.venv/bin:$PATH
RUN python -m venv "$VIRTUAL_ENV"

WORKDIR $HOME/app
COPY --chown=user:user src/pyproject.toml ./
COPY --chown=user:user src/app ./app
COPY --chown=user:user overrides.txt ./

# torch FIRST, from PyTorch's CPU index. This is the size fix: it satisfies llm-guard's `torch>=2.4.0`
# with a 159 MB wheel instead of a 555 MB one and keeps the fifteen NVIDIA packages and triton out of
# the resolve below. Pinned, because an unpinned reinstall from PyPI would silently put CUDA back.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu

# Upstream's pins, except where overrides.txt replaces them (#13): the OpenTelemetry set moves past the
# tracestate parsing fix in opentelemetry-api 1.45.1 while src/pyproject.toml stays as upstream wrote it.
# The torch above already satisfies `torch>=2.4.0`, so this resolve leaves it in place.
RUN uv pip install --no-cache --override overrides.txt ".[cpu]"

RUN python -m spacy download en_core_web_sm

# The classifier comes from OUR mirror, not from Hugging Face (#414). The weights are
# deberta-v3-base-prompt-injection-v2 at revision 90c9989b, Apache-2.0, published as
# model/ and pinned by digest above so the builder enforces it. Nothing in this
# build reaches huggingface.co any more: the upstream project was archived on 2026-07-08 and the
# archive notice covers the models, so a build that depends on that org staying alive is a build
# that stops working on somebody else's schedule.
ENV WIB_PI_MODEL_DIR=/home/user/models/prompt-injection
COPY --from=model --chown=user:user /model ${WIB_PI_MODEL_DIR}
COPY --from=model /LICENSE ${WIB_PI_MODEL_DIR}/LICENSE.model
# BanTopics loads from here through model_path, with model.onnx and the tokenizer at the top level.
ENV WIB_ZS_MODEL_DIR=/home/user/models/zero-shot
COPY --from=zero-shot --chown=user:user /model ${WIB_ZS_MODEL_DIR}
COPY --from=zero-shot /LICENSE ${WIB_ZS_MODEL_DIR}/LICENSE.model

# ---------------------------------------------------------------------------------------------------
# Runtime: no compiler, no headers, no pip cache. Only what serves a request.
# ---------------------------------------------------------------------------------------------------
FROM python:3.12-slim

LABEL org.opencontainers.image.source=https://github.com/peopleforrester/llm-guard-cpu-offline
LABEL org.opencontainers.image.description="LLM Guard API v0.3.16, CPU-only torch, prompt-injection and zero-shot topic classifiers baked in for offline scanning"
LABEL org.opencontainers.image.licenses=MIT

# libgomp1 is the one runtime library the compiler used to bring along. onnxruntime and torch want
# OpenMP; torch bundles its own copy in torch/lib, and this covers anything that looks for the system
# one. About 150 KB against build-essential's ~200 MB and its kernel headers.
#
# The upgrade is not optional, and the reason is worth keeping. The single-stage build installed
# build-essential, which depends on dpkg-dev, which depends on perl, and that incidentally upgraded
# perl-base to the version carrying three CRITICAL fixes. Dropping the compiler dropped that accident
# too, and the multi-stage image came back with three criticals the single-stage one did not have.
# Security updates in the base now happen on purpose rather than as a side effect of installing gcc.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libgomp1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    VIRTUAL_ENV=/home/user/.venv \
    PATH=/home/user/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR $HOME/app

COPY --from=builder --chown=user:user /home/user/.venv /home/user/.venv
COPY --from=builder --chown=user:user /home/user/models /home/user/models

COPY --chown=user:user src/app ./app
COPY --chown=user:user src/pyproject.toml ./pyproject.toml
COPY --chown=user:user src/LICENSE.upstream ./LICENSE.upstream
# A default config so the image runs standalone. In the cluster this path is a ConfigMap mount
# (gitops/ai-layer/resources.yaml) and the file below is shadowed. It is ours, not upstream's
# src/config/scanners.yml: that one enables scanners whose models come from huggingface.co on the
# first scan, while this one runs PromptInjection and BanTopics, from WIB_PI_MODEL_DIR and WIB_ZS_MODEL_DIR.
COPY --chown=user:user config/scanners.yml ./config/scanners.yml
COPY --chown=user:user --chmod=755 src/entrypoint.sh ./entrypoint.sh
# entrypoint.sh starts uvicorn without exec (#9), so bash stays PID 1. The kernel delivers a signal to
# a PID 1 only if it handles it, bash installs no handler and forwards nothing, so a terminating pod
# would sit out its grace period until SIGKILL. With exec, uvicorn becomes PID 1 and its own SIGTERM
# handler shuts it down gracefully. The edit is made here so src/ stays verbatim; the grep fails the
# build if upstream's line ever stops matching.
RUN sed -i 's/^uvicorn /exec uvicorn /' ./entrypoint.sh && grep -q '^exec uvicorn ' ./entrypoint.sh

# Nothing reaches the Hub at runtime. Both scanners load from their directories with local_files_only.
ENV WIB_PI_MODEL_DIR=/home/user/models/prompt-injection \
    WIB_ZS_MODEL_DIR=/home/user/models/zero-shot \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    PYTHONPATH=$HOME/app

# entrypoint.sh starts `uvicorn app.app:create_app` without --factory (#7). uvicorn 0.34.2 then
# calls create_app() itself, and if that raises TypeError, as a scanner built with a missing
# parameter does, it swallows the error and serves create_app as an ASGI2 app: the process stays up
# and every request is a 500 naming the wrong TypeError. uvicorn reads its flags from UVICORN_*
# variables, so this sets --factory without editing the vendored script, and a bad config exits.
ENV UVICORN_FACTORY=true

EXPOSE 8000

# One uvicorn worker per container (#8). Above one, uvicorn 0.34.2 runs a supervisor whose
# keep_subprocess_alive() respawns every worker that dies, so a create_app() error repeats forever
# and the pod never crash-loops. Each worker would also load its own copy of the classifier. Scale
# with replicas instead. The check sits here so the vendored entrypoint.sh stays verbatim.
ENTRYPOINT ["/bin/sh", "-c", "[ \"${APP_WORKERS:-1}\" = 1 ] || { echo \"APP_WORKERS=$APP_WORKERS: this image runs one uvicorn worker per container; scale with replicas\" >&2; exit 1; }; exec ./entrypoint.sh \"$@\"", "entrypoint.sh"]
