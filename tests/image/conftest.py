# ABOUTME: Starts the guard image that tests/e2e/run.sh built, with --network none and its shipped config,
# ABOUTME: and waits until it is ready; scans go in through docker exec because nothing can reach it.
import json
import os
import subprocess
import sys
import time

import pytest

from tests.dockerfile import REPO_ROOT, parse
from tests.image.runtime import TOKEN, docker

READY_TIMEOUT = 300

# Runs inside the container with the image's own Python: argv is method, path, token, JSON body or "".
REQUEST = """
import json, sys, urllib.error, urllib.request
method, path, token, body = sys.argv[1:5]
headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = "Bearer " + token
request = urllib.request.Request(
    "http://127.0.0.1:8000" + path, data=body.encode() or None, headers=headers, method=method
)
try:
    with urllib.request.urlopen(request, timeout=120) as response:
        status, text = response.status, response.read().decode()
except urllib.error.HTTPError as error:
    status, text = error.code, error.read().decode()
print(json.dumps({"status": status, "body": text}))
"""


def pytest_sessionstart(session):
    image = os.environ.get("E2E_IMAGE")
    if not image or docker("image", "inspect", image, check=False).returncode != 0:
        raise pytest.UsageError(f"E2E_IMAGE={image!r} is not a built image; run through tests/e2e/run.sh")


@pytest.fixture(scope="session")
def zero_shot_dir() -> str:
    return parse(REPO_ROOT / "Dockerfile").final.env()["WIB_ZS_MODEL_DIR"]


@pytest.fixture(scope="session")
def started():
    """The running container and the seconds it took to answer /readyz."""
    # The config the image ships, with both classifiers, set only through the variables it reads.
    name = docker(
        "create", "--network", "none",
        "--env", f"AUTH_TOKEN={TOKEN}",
        "--env", "LOG_LEVEL=WARNING",
        "--env", "SCAN_PROMPT_TIMEOUT=60",
        os.environ["E2E_IMAGE"],
    ).stdout.strip()
    try:
        docker("start", name)
        yield name, _wait_until_ready(name)
    finally:
        logs = docker("logs", name, check=False)
        print(logs.stdout, logs.stderr)
        docker("rm", "--force", name, check=False)


@pytest.fixture(scope="session")
def container(started) -> str:
    return started[0]


@pytest.fixture(scope="session")
def ready_seconds(started) -> float:
    return started[1]


def _wait_until_ready(name: str) -> float:
    deadline = time.monotonic() + READY_TIMEOUT
    while (remaining := deadline - time.monotonic()) > 0:
        if docker("inspect", "--format", "{{.State.Running}}", name).stdout.strip() != "true":
            raise RuntimeError(f"container exited before it was ready:\n{docker('logs', name).stderr}")
        probe = _exec(name, "GET", "/readyz", "", "")
        if probe.returncode == 0 and json.loads(probe.stdout)["status"] == 200:
            print(f"\r  container ready after {READY_TIMEOUT - remaining:.0f}s", file=sys.__stderr__)
            return READY_TIMEOUT - remaining
        print(f"\r  waiting for the container: {READY_TIMEOUT - remaining:.0f}s of at most {READY_TIMEOUT}s",
              end="", file=sys.__stderr__, flush=True)
        time.sleep(2)
    raise RuntimeError(f"container not ready after {READY_TIMEOUT}s:\n{docker('logs', name).stderr}")


def _exec(name: str, method: str, path: str, token: str, payload: str) -> subprocess.CompletedProcess:
    return docker("exec", name, "python", "-c", REQUEST, method, path, token, payload, check=False)


@pytest.fixture(scope="session")
def api(container):
    """Sends one request from inside the container; returns its status and body."""

    def send(method: str, path: str, token: str = "", body: dict | None = None) -> dict:
        result = _exec(container, method, path, token, json.dumps(body) if body is not None else "")
        assert result.returncode == 0, f"docker exec failed:\n{result.stderr}"
        return json.loads(result.stdout)

    return send
