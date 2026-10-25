# ABOUTME: Runs the image's ENTRYPOINT against the vendored entrypoint.sh and a factory that raises: more
# ABOUTME: than one worker is refused before uvicorn starts, and one worker is handed over unchanged.
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from tests.dockerfile import REPO_ROOT, parse

ENTRYPOINT = REPO_ROOT / "src" / "entrypoint.sh"
FACTORY_ERROR = "create_app was called"
REFUSAL = "this image runs one uvicorn worker per container"


def image_entrypoint() -> list[str]:
    (args,) = parse(REPO_ROOT / "Dockerfile").final.args_of("ENTRYPOINT")
    return json.loads(args)


def run_image_entrypoint(workdir: Path, workers: str | None) -> subprocess.CompletedProcess:
    """Run the ENTRYPOINT from the image's WORKDIR layout: ./entrypoint.sh beside the app package."""
    shutil.copy(ENTRYPOINT, workdir / "entrypoint.sh")
    (workdir / "entrypoint.sh").chmod(0o755)
    package = workdir / "app"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "app.py").write_text(f"def create_app():\n    raise RuntimeError({FACTORY_ERROR!r})\n")

    env = {
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(workdir),
    }
    if workers is not None:
        env["APP_WORKERS"] = workers
    # Its own session, so a supervisor left respawning workers (the bug) is killed with its children.
    process = subprocess.Popen(
        image_entrypoint(),
        cwd=workdir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


@pytest.mark.parametrize("workers", ["2", "4"])
def test_more_than_one_worker_exits_before_uvicorn_starts(tmp_path, workers):
    result = run_image_entrypoint(tmp_path, workers)

    assert result.returncode == 1, result.stderr
    assert f"APP_WORKERS={workers}: {REFUSAL}" in result.stderr
    assert "Uvicorn running" not in result.stderr
    assert "Child process" not in result.stderr
    assert FACTORY_ERROR not in result.stderr


@pytest.mark.parametrize("workers", [None, "", "1"])
def test_one_worker_is_handed_to_the_vendored_entrypoint(tmp_path, workers):
    result = run_image_entrypoint(tmp_path, workers)

    assert result.returncode == 1, result.stderr
    assert f"RuntimeError: {FACTORY_ERROR}" in result.stderr
    assert REFUSAL not in result.stderr
