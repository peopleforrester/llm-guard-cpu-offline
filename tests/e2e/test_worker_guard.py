# ABOUTME: Starts the real API through the image's ENTRYPOINT with no network: one worker loads the
# ABOUTME: classifier and serves, and more than one is refused before any worker loads the app.
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from tests.dockerfile import REPO_ROOT, parse

SERVING = "Uvicorn running on http://0.0.0.0:8000"
REFUSAL = "this image runs one uvicorn worker per container"


def _config(tmp_path: Path, model_dir: str) -> Path:
    config = tmp_path / "scanners.yml"
    config.write_text(
        "app:\n"
        "  log_level: WARNING\n"
        "  lazy_load: false\n"
        "input_scanners:\n"
        "  - type: PromptInjection\n"
        "    params:\n"
        "      threshold: 0.92\n"
        f"      model_path: {model_dir}\n"
        "output_scanners: []\n"
    )
    return config


def _start(config: Path, workers: str, log: Path) -> subprocess.Popen:
    (entrypoint,) = parse(REPO_ROOT / "Dockerfile").final.args_of("ENTRYPOINT")
    # The image's WORKDIR holds ./entrypoint.sh, copied with --chmod=755; the repository's copy is 644.
    workdir = config.parent / "workdir"
    workdir.mkdir()
    shutil.copy(REPO_ROOT / "src" / "entrypoint.sh", workdir / "entrypoint.sh")
    (workdir / "entrypoint.sh").chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "CONFIG_FILE": str(config),
        "APP_WORKERS": workers,
    }
    # Its own session, so a uvicorn left serving is stopped together with the shell that started it.
    return subprocess.Popen(
        json.loads(entrypoint),
        cwd=workdir,
        env=env,
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _wait_for_exit_or_serving(process: subprocess.Popen, log: Path, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while process.poll() is None and SERVING not in log.read_text():
        assert time.monotonic() < deadline, f"neither exited nor served in {timeout}s:\n{log.read_text()}"
        time.sleep(0.5)
    return log.read_text()


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def test_two_workers_are_refused_before_the_app_loads(tmp_path, model_dir):
    log = tmp_path / "entrypoint.log"
    process = _start(_config(tmp_path, model_dir), "2", log)
    try:
        output = _wait_for_exit_or_serving(process, log, timeout=30)
    finally:
        _stop(process)

    assert process.returncode == 1, output
    assert f"APP_WORKERS=2: {REFUSAL}" in output
    assert SERVING not in output


def test_one_worker_loads_the_classifier_and_serves(tmp_path, model_dir):
    log = tmp_path / "entrypoint.log"
    process = _start(_config(tmp_path, model_dir), "1", log)
    try:
        output = _wait_for_exit_or_serving(process, log, timeout=180)
        assert process.poll() is None, output
    finally:
        _stop(process)

    assert SERVING in output
    assert REFUSAL not in output
