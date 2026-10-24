# ABOUTME: Runs the vendored entrypoint.sh with the image's uvicorn settings against a factory that raises
# ABOUTME: TypeError, and checks uvicorn exits with that error instead of serving the factory as an app.
import os
import signal
import subprocess
import sys
from pathlib import Path

from tests.dockerfile import REPO_ROOT, parse

ENTRYPOINT = REPO_ROOT / "src" / "entrypoint.sh"
CONFIG_ERROR = "BanTopics.__init__() missing 1 required positional argument: 'topics'"


def image_uvicorn_env() -> dict:
    env = parse(REPO_ROOT / "Dockerfile").final.env()
    return {key: value for key, value in env.items() if key.startswith("UVICORN_")}


def test_image_tells_uvicorn_that_create_app_is_a_factory():
    assert image_uvicorn_env() == {"UVICORN_FACTORY": "true"}


def test_a_type_error_in_create_app_exits_with_the_real_error(tmp_path):
    package = tmp_path / "app"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "app.py").write_text(f"def create_app():\n    raise TypeError({CONFIG_ERROR!r})\n")

    env = {
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(tmp_path),
        **image_uvicorn_env(),
    }
    # Its own session, so a uvicorn left serving (the bug) is killed with the bash that started it.
    process = subprocess.Popen(
        ["bash", str(ENTRYPOINT)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        _, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        _, stderr = process.communicate()

    assert process.returncode == 1, stderr
    assert f"Error loading ASGI app factory: {CONFIG_ERROR}" in stderr
    assert "takes 0 positional arguments" not in stderr
    assert "Uvicorn running" not in stderr
