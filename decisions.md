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
digest, and scans inside `unshare -rn`.

## 2026-10-24: the E2E builds the image

The venv scan cannot see layer-level regressions, such as a missing COPY into the runtime stage, so
`tests/e2e/run.sh` then runs `docker build`, starts the image with `--network none` and the
PromptInjection-only config copied in, and scans through `docker exec` (`tests/image/`). It needs a
`docker` CLI that can build and run, and fails before installing anything when `docker info` does
not answer. The agent sandbox has no such runtime (docker.sock is permission-denied, and rootless
podman lacks a subordinate uid range), so the full E2E runs only on a host that has one.
