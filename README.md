# llm-guard-cpu-offline

[LLM Guard](https://github.com/protectai/llm-guard) v0.3.16, packaged to scan with **no network
access** and **no GPU**, with its prompt-injection and topic classifiers baked in, at under two fifths
of the upstream image's size.

```
ghcr.io/peopleforrester/watch-it-burn:llm-guard-0.3.16-cpu.5@sha256:4c66fd0f0846c2c829952e562fd076f37ca8f7e41fb6ecfbb5a1f28cb8579791
```

It is publicly pullable and signed with cosign. Pin it by digest. `llm-guard-0.3.16-cpu.4`
(`sha256:3322db6af60c2fc935f2208d0c4a84198b29e93307ab2e88debdd045a919ae9f`, 1,274 MB) is the last
build with PromptInjection alone.

## What this is, and what it is not

It is a **packaging**, not a fork. The API server under `src/` is LLM Guard's own `llm_guard_api` at
tag v0.3.16, copied verbatim with its MIT license as `src/LICENSE.upstream`. The scanners are
upstream's, unmodified. Nobody here is maintaining the library.

That distinction matters because upstream is gone. Palo Alto Networks completed its acquisition of
Protect AI on 2025-07-22, and the LLM Guard repository was archived on 2026-07-08. Its notice covers
the Hugging Face models as well as the code. This repository exists so that an image depending on
that project keeps building and keeps working.

## What it fixes

**It scans with no network.** Upstream lazy-loads its classifiers from huggingface.co on the first
scan. Behind a default-deny egress policy that download fails, and a fail-closed caller then refuses
every request. Here the PromptInjection and BanTopics classifiers are baked in and loaded from local
directories with `local_files_only`, and the Hugging Face libraries are switched to offline mode.
Verified on `docker run --network none` with the shipped config: ready in 16 to 19 seconds with both
classifiers, injection and a banned topic both blocked.

**It is CPU-only.** The upstream image installs the default PyPI torch, which declares fifteen NVIDIA
CUDA packages as hard dependencies. On a CPU node `transformers_helpers.py` never selects the CUDA
execution provider, so that payload is never loaded. The `[cpu]` extra does **not** fix this, because
it selects the optimum variant only. The fix is installing torch from PyTorch's CPU index first.

**It does not depend on Hugging Face to build.** The weights come from `model/` and
`model-zero-shot/`, each published as its own image and pinned by digest in the main Dockerfile.

| | Upstream-based build | This image (cpu.5) |
|---|---|---|
| Compressed size | 4,211 MB | **1,650 MB** |
| Critical CVEs (trivy) | 29 | **0** |
| Unique CVEs, critical and high | 916 | **27** |
| Network needed to scan | yes, on the first scan | **no** |
| Compiler in the runtime image | yes | **no** (multi-stage build) |

The cpu.5 figures were measured on 2026-10-29: size from the registry manifest, CVEs with trivy
(critical and high only) on a build with no layer cache, and start time over three starts on a
16-core host at load average 26 to 28. A cached build once carried an older certifi and pip whose CA
bundle trivy rates critical, which is why the build below passes `--no-cache`.

## Layout

```
Dockerfile      the guard image: multi-stage, CPU torch, vendored API server
src/            llm_guard_api v0.3.16, verbatim, MIT (LICENSE.upstream)
overrides.txt   packaging-owned overrides of upstream's pins (OpenTelemetry, #13); src/ stays verbatim
model/          the prompt-injection weights as a scratch image, with provenance
model-zero-shot/ the BanTopics zero-shot weights as a scratch image, with provenance
config/         the image's default scanners.yml: PromptInjection and BanTopics, from the baked-in models
tests/          unit tests (Dockerfiles, config, entrypoint) and the no-network E2E
```

## The models

`protectai/deberta-v3-base-prompt-injection-v2` at revision
`90c9989b1a342275dd0d1a95aad283c04e075671`, Apache-2.0. The sha256 of `model.onnx` and `spm.model`
were read from the Hugging Face API for that revision and independently computed from the files
shipped here, and they agree. `model/LICENSE.model` records the provenance and carries the full
license, and it travels inside both images.

`MoritzLaurer/deberta-v3-base-zeroshot-v2.0` at revision
`8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8`, the revision llm-guard 0.3.16 uses for BanTopics. Its model
card declares MIT. All seven files are pinned by sha256 in `model-zero-shot/Dockerfile`, and
`model-zero-shot/LICENSE.model` records them with the license and travels with the weights. The card
also says that models without "-c" in the name, this one included, were trained partly on data with
non-commercial licenses, and recommends the "-c" models for users with strict legal requirements.

## Building

```bash
docker build -t <registry>/llm-guard-model:<rev> model
docker build -t <registry>/llm-guard-model-zeroshot:<rev> model-zero-shot
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
MIT, copyright Protect AI; see `src/LICENSE.upstream`. The prompt-injection weights are Apache-2.0;
see `model/LICENSE.model`. The zero-shot weights are MIT as their model card declares; see
`model-zero-shot/LICENSE.model`.
