# Decisions

## 2026-10-24: test dependencies

The repository had no tests. These are test-only dependencies; none reaches either image.

| Package | Pin | Why |
|---|---|---|
| pytest | 9.1.1 | Runner for both suites; current release. |
| ruff | 0.17.2 | Lint for the tests. The vendored `src/` stays as upstream wrote it and is not linted. |
| pydantic | 2.11.4 | Same pin as `src/pyproject.toml`, so the config loader is tested against what the image runs. |
| pyyaml | 6.0.2 | Same reason as pydantic. |
| structlog | 26.1.0 | `src/pyproject.toml` allows `>=24`; this is what a fresh build resolves today. |
| httpx | 0.28.1 | E2E only: FastAPI's `TestClient` needs it. |

The light suite runs on Python 3.12, the interpreter in `python:3.12-slim`, and needs neither torch
nor llm-guard: it checks the Dockerfiles statically and exercises the config loader.

The E2E suite installs torch from the CPU index and then `src[cpu]`, in the Dockerfile's order and
with the Dockerfile's torch pin, fetches the weights from the model image the Dockerfile pins by
digest, and scans inside `unshare -rn`. It does not build the image: building needs a container
runtime with subordinate uids, which the agent sandbox does not have, and the property under test,
scanning with no network, is a property of the install and the weights rather than of the layers.

## 2026-10-24: the zero-shot weights image reads the Hub, checksum-pinned

`model-zero-shot/` mirrors MoritzLaurer/deberta-v3-base-zeroshot-v2.0 at the revision llm-guard 0.3.16
pins for BanTopics. `model/` copies its bytes from an earlier guard image of ours, but no image of ours
has ever carried these weights, so the mirror has to read them from Hugging Face once. It does so with
`ADD --checksum=sha256:...` per file in a scratch stage: the builder refuses any byte that differs, the
image still executes nothing, and no download tool enters the build. The guard Dockerfile itself keeps
its rule of never touching the Hub; it will take these weights by digest from the pushed mirror.

The E2E suite reads the same seven URLs and checksums out of `model-zero-shot/Dockerfile`, so it scans
the bytes the mirror will hold. No new dependency.
