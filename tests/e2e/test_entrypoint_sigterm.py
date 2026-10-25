# ABOUTME: Runs the real API through the image's entrypoint.sh as PID 1 of its own PID namespace, as a
# ABOUTME: container does, then sends that PID 1 SIGTERM from outside and expects a graceful uvicorn exit.
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from tests.dockerfile import REPO_ROOT
from tests.image_entrypoint import build, image_uvicorn_env

SERVING = "Uvicorn running on http://0.0.0.0:8000"


def _namespace_init(unshare: subprocess.Popen) -> int:
    children = Path(f"/proc/{unshare.pid}/task/{unshare.pid}/children").read_text().split()
    assert len(children) == 1, children
    return int(children[0])


def test_sigterm_to_pid_1_shuts_uvicorn_down_gracefully(tmp_path, model_dir):
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
    entrypoint = build(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "CONFIG_FILE": str(config),
        **image_uvicorn_env(),
    }
    log = tmp_path / "entrypoint.log"
    # The kernel delivers a signal to a namespace's PID 1 only if PID 1 handles it, which is what a
    # container runtime runs into when it sends SIGTERM to the container's entrypoint.
    unshare = subprocess.Popen(
        ["unshare", "-rpf", "--mount-proc", str(entrypoint)],
        cwd=tmp_path,
        env=env,
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
    )
    init = None
    try:
        deadline = time.monotonic() + 180
        while SERVING not in log.read_text():
            assert unshare.poll() is None, log.read_text()
            assert time.monotonic() < deadline, f"did not serve in 180s:\n{log.read_text()}"
            time.sleep(0.5)
        init = _namespace_init(unshare)
        os.kill(init, signal.SIGTERM)
        try:
            returncode = unshare.wait(timeout=30)
        except subprocess.TimeoutExpired:
            returncode = "still running 30s after SIGTERM"
    finally:
        if unshare.poll() is None:
            # SIGKILL reaches PID 1 regardless, and ends every process in its namespace.
            os.kill(init or _namespace_init(unshare), signal.SIGKILL)
            unshare.wait()

    output = log.read_text()
    assert returncode == 0, output
    assert "Started server process [1]" in output
    assert "Shutting down" in output
    assert "Application shutdown complete." in output
    assert "Finished server process [1]" in output
