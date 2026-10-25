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

## 2026-10-25: `exec` added to the image's copy of `entrypoint.sh`, not to `src/` (#9)

`src/entrypoint.sh` starts uvicorn without `exec`, so bash stays PID 1 and uvicorn is its child. The
kernel delivers a signal to a PID namespace's init only if init handles it, and bash installs no
SIGTERM handler, so a container runtime's SIGTERM did nothing and the pod waited out its grace period
for SIGKILL. `tests/e2e/test_entrypoint_sigterm.py` reproduced this: uvicorn ran as PID 2 and was
still running 30 seconds after PID 1 got SIGTERM.

The runtime stage now runs `sed 's/^uvicorn /exec uvicorn /'` on its copy of the script, and a
`grep` fails the build if upstream's line no longer matches. uvicorn becomes PID 1 and shuts down
gracefully on SIGTERM. `src/` stays verbatim, which the README states, and the image still runs
upstream's script, so `APP_WORKERS` and the flags keep coming from it.

Rejected: an ENTRYPOINT that runs uvicorn itself would duplicate upstream's command line and leave a
dead copy of the script in the image. An init such as tini or dumb-init forwards SIGTERM to bash,
which dies at once without signalling its child, and the init exits with it, so uvicorn is killed
mid-shutdown.

| Package | Pin | Why |
|---|---|---|
| uvicorn | 0.34.2 | Unit suite only: the entrypoint test runs the image's script, and this is `src/pyproject.toml`'s pin. |
