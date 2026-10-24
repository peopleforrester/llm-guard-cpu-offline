# ABOUTME: Starts the guard image that tests/e2e/run.sh built, with --network none and a PromptInjection-only
# ABOUTME: config, and waits until it is ready; scans go in through docker exec because nothing can reach it.
import json
import os
import subprocess
import sys
import time

import pytest

from tests.dockerfile import REPO_ROOT, parse
from tests.image.runtime import TOKEN, docker

READY_TIMEOUT = 300
CONFIG_PATH = "/home/user/app/config/scanners.yml"

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
def model_dir() -> str:
    return parse(REPO_ROOT / "Dockerfile").final.env()["WIB_PI_MODEL_DIR"]


@pytest.fixture(scope="session")
def container(model_dir, tmp_path_factory):
    config = tmp_path_factory.mktemp("config") / "scanners.yml"
    config.write_text(
        "app:\n"
        "  log_level: WARNING\n"
        "  lazy_load: false\n"
        "  scan_prompt_timeout: 60\n"
        "auth:\n"
        "  type: http_bearer\n"
        f"  token: {TOKEN}\n"
        "input_scanners:\n"
        "  - type: PromptInjection\n"
        "    params:\n"
        "      threshold: 0.92\n"
        "      match_type: truncate_head_tail\n"
        "      model_max_length: 256\n"
        f"      model_path: {model_dir}\n"
        "output_scanners: []\n"
    )
    config.chmod(0o644)

    name = docker("create", "--network", "none", os.environ["E2E_IMAGE"]).stdout.strip()
    try:
        # Copied rather than bind-mounted, so the file's ownership does not depend on the runtime's uid mapping.
        docker("cp", str(config), f"{name}:{CONFIG_PATH}")
        docker("start", name)
        _wait_until_ready(name)
        yield name
    finally:
        logs = docker("logs", name, check=False)
        print(logs.stdout, logs.stderr)
        docker("rm", "--force", name, check=False)


def _wait_until_ready(name: str) -> None:
    deadline = time.monotonic() + READY_TIMEOUT
    while (remaining := deadline - time.monotonic()) > 0:
        if docker("inspect", "--format", "{{.State.Running}}", name).stdout.strip() != "true":
            raise RuntimeError(f"container exited before it was ready:\n{docker('logs', name).stderr}")
        probe = _exec(name, "GET", "/readyz", "", "")
        if probe.returncode == 0 and json.loads(probe.stdout)["status"] == 200:
            print(f"\r  container ready after {READY_TIMEOUT - remaining:.0f}s", file=sys.__stderr__)
            return
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
