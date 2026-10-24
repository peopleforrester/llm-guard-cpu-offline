# ABOUTME: Starts the real API through the vendored entrypoint.sh with the image's uvicorn settings: a
# ABOUTME: config whose scanner cannot be built exits with that error, and a valid config still serves.
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from tests.dockerfile import REPO_ROOT, parse

ENTRYPOINT = REPO_ROOT / "src" / "entrypoint.sh"
SERVING = "Uvicorn running on http://0.0.0.0:8000"


def _start(config: Path, log: Path) -> subprocess.Popen:
    image_env = parse(REPO_ROOT / "Dockerfile").final.env()
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "CONFIG_FILE": str(config),
        **{key: value for key, value in image_env.items() if key.startswith("UVICORN_")},
    }
    # Its own session, so a uvicorn left serving is stopped together with the bash that started it.
    return subprocess.Popen(
        ["bash", str(ENTRYPOINT)],
        cwd=REPO_ROOT / "src",
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


def test_a_scanner_missing_its_parameters_exits_with_the_real_error(tmp_path):
    config = tmp_path / "scanners.yml"
    config.write_text(
        "app:\n"
        "  lazy_load: false\n"
        "input_scanners:\n"
        "  - type: BanTopics\n"
        "output_scanners: []\n"
    )
    log = tmp_path / "entrypoint.log"
    process = _start(config, log)
    try:
        output = _wait_for_exit_or_serving(process, log, timeout=120)
    finally:
        _stop(process)

    assert process.returncode == 1, output
    assert "Error loading ASGI app factory:" in output
    assert "missing 1 required positional argument: 'topics'" in output
    assert "takes 0 positional arguments" not in output
    assert SERVING not in output


def test_a_valid_config_still_serves(tmp_path, model_dir):
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
    log = tmp_path / "entrypoint.log"
    process = _start(config, log)
    try:
        output = _wait_for_exit_or_serving(process, log, timeout=180)
        assert process.poll() is None, output
    finally:
        _stop(process)

    assert SERVING in output
    assert "ASGI app factory detected" not in output
