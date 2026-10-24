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

## 2026-10-24: the image's default config is ours, not upstream's

Issue #3: the image copied upstream's `src/config/scanners.yml`, which enables about thirty scanners.
Every one but PromptInjection fetches its model from huggingface.co on first use, so under
`--network none` the first scan failed even though the image reported healthy.

The image now copies `config/scanners.yml`, a packaging-owned file: upstream's `app`, `rate_limit`,
`auth`, `tracing` and `metrics` sections unchanged except `lazy_load`, PromptInjection alone with
`model_path: ${WIB_PI_MODEL_DIR}`, and no output scanners. `src/config/scanners.yml` stays verbatim,
because `src/` is a verbatim copy of upstream. `lazy_load` defaults to false, as in the cluster's
ConfigMap, so a missing model fails the start instead of the first scan. The E2E suite scans with
this file rather than a config written for the test.
