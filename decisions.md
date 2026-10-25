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

## 2026-10-25: question 721, one uvicorn worker per container (#8)

**Question 721:** When the llm-guard image is started with APP_WORKERS above 1, should it refuse to
start, check the app once before forking workers, or stay as it is with the limitation written down?

**Answer:** Refuse to start above 1.

**Decided by:** hecaton's research under Michael's standing rules, not by Michael.

**What it changes:** The Dockerfile's ENTRYPOINT checks `APP_WORKERS` before it hands over to the
vendored `entrypoint.sh`. Unset, empty, or `1` runs `./entrypoint.sh` as before. Any other value
exits 1 with a message saying the image runs one worker per container and scaling is done with
replicas. Above one worker, uvicorn 0.34.2 runs a supervisor whose `keep_subprocess_alive()`
respawns every worker that dies. A `create_app()` error therefore repeated about four times a second
and never exited, and the pod never crash-looped. Each worker would also load its own copy of the
classifier, which the deployed limits of 1 CPU and 3 GiB do not allow. No deployment set more than
one worker when this was decided. The check sits in the Dockerfile so `src/` stays verbatim.

| Package | Pin | Why |
|---|---|---|
| uvicorn | 0.34.2 | Unit suite only: the worker test runs the vendored script through the image's ENTRYPOINT, and this is `src/pyproject.toml`'s pin. |
