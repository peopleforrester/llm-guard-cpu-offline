# ABOUTME: Starts the image's entrypoint.sh with the uvicorn the image runs and checks the process it
# ABOUTME: starts as becomes uvicorn itself, so uvicorn rather than bash is PID 1 and receives SIGTERM.
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from tests.image_entrypoint import VENDORED, build, image_uvicorn_env

# src/entrypoint.sh at upstream v0.3.16. The fix belongs in the Dockerfile, not in this line.
UPSTREAM_UVICORN_LINE = (
    'uvicorn app.app:create_app --host=0.0.0.0 --port=8000 --workers="$APP_WORKERS"'
    ' --forwarded-allow-ips="*" --proxy-headers --timeout-keep-alive="2"'
)

# Lifespan startup never completes, so uvicorn stays up without binding port 8000 on the test host.
APP = """\
import asyncio
from pathlib import Path


async def app(scope, receive, send):
    assert scope["type"] == "lifespan"
    await receive()
    Path("started").touch()
    await asyncio.Future()


def create_app():
    return app
"""


def _cmdline(pid: int) -> list[str]:
    return Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")[:-1]


def test_the_entrypoint_process_becomes_uvicorn(tmp_path):
    package = tmp_path / "app"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "app.py").write_text(APP)
    entrypoint = build(tmp_path)

    env = {
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(tmp_path),
        **image_uvicorn_env(),
    }
    # Its own session, so a uvicorn left behind by a bash that did not exec is killed with it.
    process = subprocess.Popen(
        [str(entrypoint)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not (tmp_path / "started").exists():
            assert process.poll() is None, process.communicate()
            assert time.monotonic() < deadline, "uvicorn did not reach lifespan startup in 30s"
            time.sleep(0.1)
        cmdline = _cmdline(process.pid)
    finally:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()

    assert Path(cmdline[0]).name.startswith("python"), cmdline
    assert Path(cmdline[1]).name == "uvicorn", cmdline
    assert cmdline[2] == "app.app:create_app", cmdline
    assert str(entrypoint) not in cmdline


def test_the_vendored_script_stays_as_upstream_wrote_it():
    lines = VENDORED.read_text().splitlines()
    assert [line for line in lines if "uvicorn " in line] == [UPSTREAM_UVICORN_LINE]
