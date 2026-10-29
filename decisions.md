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
## 2026-10-24: `--factory` through the environment, not by patching `src/entrypoint.sh` (#7)

`src/entrypoint.sh` starts `uvicorn app.app:create_app` without `--factory`. Under uvicorn 0.34.2 a
TypeError raised inside `create_app()`, such as a scanner missing a required parameter, is swallowed
and the factory itself is served, so the pod stays up answering 500 with the wrong error. uvicorn
reads every flag from a `UVICORN_*` variable (`auto_envvar_prefix="UVICORN"`), so the Dockerfile sets
`UVICORN_FACTORY=true` and uvicorn exits 1 with `Error loading ASGI app factory: <the real error>`.

This keeps `src/` verbatim, which the README states, and is one line in the file this repository
owns. Editing the vendored script would have made that claim false; a second, packaging-owned
entrypoint would have left a dead copy of upstream's beside it.

| Package | Pin | Why |
|---|---|---|
| uvicorn | 0.34.2 | Unit suite only: the entrypoint test runs the vendored script, and this is `src/pyproject.toml`'s pin. |
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

## 2026-10-29: correction to "the E2E builds the image"

The 2026-10-24 entry "the E2E builds the image" ends with three lines left over from an earlier draft
("digest, and scans inside `unshare -rn`. It does not build the image: ..."). They are superseded and
wrong: `tests/e2e/run.sh` does build the image (step 5/6) and scans through it under
`--network none` (step 6/6). On 2026-10-29 the full run passed on a host with a working Docker: 14
venv scans, the build, and 11 image scans. Prior entries stay as written, per the append-only rule.

## 2026-10-29: image source labels name this repository

Both Dockerfiles set `org.opencontainers.image.source` to Unleash_an_Agent_Watch_It_Burn, where the
packaging lived before it got its own repository. They now name
`peopleforrester/llm-guard-cpu-offline`, so the label leads to the Dockerfile that built the image.

## 2026-10-29: main promoted by hand to 0750303

`ship.sh promote` counted GitHub's Dependabot and Dependency Graph runs as CI, so with no workflow
in this repository it waited for a run on the staging tip that never comes (filed as
peopleforrester/llm-coding-workflow#436). Promoted by hand with the same checks: `origin/main` was
an ancestor of the tip, the tip was `origin/staging` exactly, the five commits were the ones audited,
and the full E2E passed on that commit. `git push origin 0750303:main`, a fast-forward.

## 2026-10-29: CI on GitHub-hosted runners (#5)

`.github/workflows/test.yml` runs the unit suite and `tests/e2e/run.sh` on `ubuntu-24.04`, on push to
staging and main and on pull requests. Hosted rather than the fleet's `[self-hosted, general]`: the
repository is public, so fork pull requests must not reach a self-hosted runner, and the fleet runner
could not reach the docker daemon (#11). Public repositories run hosted minutes at no cost. The E2E
job lifts Ubuntu 24.04's AppArmor block on unprivileged user namespaces, which `unshare -rn` needs,
and removes the runner's preinstalled Android SDK, .NET and GHC for disk.

## 2026-10-29: PR #10 closed, alert tracked in #13

Dependabot's PR bumped only `opentelemetry-api` to 1.45.1 in `src/pyproject.toml`, which does not
resolve: `opentelemetry-sdk==1.33.1` pins the api exactly. It also edited the vendored `src/`. The
advisory (alert #1, unbounded tracestate parsing, medium) is tracked in #13 as one coherent
OpenTelemetry upgrade.
