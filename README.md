# llm-guard-cpu-offline

[LLM Guard](https://github.com/protectai/llm-guard) v0.3.16, packaged to scan with **no network
access** and **no GPU**, at under a third of the upstream image's size.

```
ghcr.io/peopleforrester/watch-it-burn:llm-guard-0.3.16-cpu.4@sha256:3322db6af60c2fc935f2208d0c4a84198b29e93307ab2e88debdd045a919ae9f
```

It is publicly pullable and signed with cosign. Pin it by digest.

## What this is, and what it is not

It is a **packaging**, not a fork. The API server under `src/` is LLM Guard's own `llm_guard_api` at
tag v0.3.16, copied verbatim with its MIT license as `src/LICENSE.upstream`. The scanners are
upstream's, unmodified. Nobody here is maintaining the library.

That distinction matters because upstream is gone. Palo Alto Networks completed its acquisition of
Protect AI on 2025-07-22, and the LLM Guard repository was archived on 2026-07-08. Its notice covers
the Hugging Face models as well as the code. This repository exists so that an image depending on
that project keeps building and keeps working.

## What it fixes

**It scans with no network.** Upstream lazy-loads its prompt-injection classifier from huggingface.co
on the first scan. Behind a default-deny egress policy that download fails, and a fail-closed caller
then refuses every request. Here the classifier is baked in and loaded from a local directory with
`local_files_only`, and the Hugging Face libraries are switched to offline mode. Verified on
`docker run --network none`: healthy in about fourteen seconds, injection detected at score 1.0.

**It is CPU-only.** The upstream image installs the default PyPI torch, which declares fifteen NVIDIA
CUDA packages as hard dependencies. On a CPU node `transformers_helpers.py` never selects the CUDA
execution provider, so that payload is never loaded. The `[cpu]` extra does **not** fix this, because
it selects the optimum variant only. The fix is installing torch from PyTorch's CPU index first.

**It does not depend on Hugging Face to build.** The weights come from `model/`, published as their
own image and pinned by digest in the main Dockerfile.

| | Upstream-based build | This image (cpu.4) |
|---|---|---|
| Compressed size | 4,211 MB | **1,274 MB** |
| Critical CVEs (trivy) | 29 | **0** |
| Unique CVEs, critical and high | 916 | **27** |
| Network needed to scan | yes, on the first scan | **no** |
| Compiler in the runtime image | yes | **no** (multi-stage build) |

The cpu.4 figures were measured on 2026-10-29 with trivy, critical and high only, on a build with no
layer cache. A cached build carried an older certifi and pip whose CA bundle trivy rates critical.

## Layout

```
Dockerfile      the guard image: multi-stage, CPU torch, vendored API server
src/            llm_guard_api v0.3.16, verbatim, MIT (LICENSE.upstream)
overrides.txt   packaging-owned overrides of upstream's pins (OpenTelemetry, #13); src/ stays verbatim
model/          the classifier weights as a scratch image, with provenance
config/         the image's default scanners.yml: PromptInjection only, from the baked-in model
tests/          unit tests (Dockerfiles, config, entrypoint) and the no-network E2E
```

## The model

`protectai/deberta-v3-base-prompt-injection-v2` at revision
`90c9989b1a342275dd0d1a95aad283c04e075671`, Apache-2.0. The sha256 of `model.onnx` and `spm.model`
were read from the Hugging Face API for that revision and independently computed from the files
shipped here, and they agree. `model/LICENSE.model` records the provenance and carries the full
license, and it travels inside both images.

## Building

```bash
docker build -t <registry>/llm-guard-model:<rev> model
docker build --pull --no-cache -t <registry>/llm-guard:<tag> .
```

## Signing

Images are signed with **cosign 2.x**. cosign 3.x writes a signature format that Kyverno 1.19 reports
as "no signatures found" even though `cosign verify` passes. The signing procedure and the public key
live in the repository that deploys this image,
[Unleash_an_Agent_Watch_It_Burn](https://github.com/peopleforrester/Unleash_an_Agent_Watch_It_Burn),
under `policies/cosign/`.

## Who calls it

[guard-proxy-agenticburn](https://github.com/peopleforrester/guard-proxy-agenticburn) is the
consumer of this image. It reaches the API at `LLM_GUARD_URL` and fails closed by default
(`PROXY_FAIL_CLOSED`), so when this image cannot scan, every prompt is refused.

## History

This repository's history before its first standalone commit was carried over from
Unleash_an_Agent_Watch_It_Burn, where the packaging lived under `images/llm-guard` and
`images/llm-guard-model`. That repository now consumes this one as a git submodule.

## License

The packaging (the Dockerfiles and this README) is MIT; see `LICENSE`. The vendored API server is
MIT, copyright Protect AI; see `src/LICENSE.upstream`. The model weights are Apache-2.0; see
`model/LICENSE.model`.
