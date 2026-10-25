# ABOUTME: Reproduces the image's ./entrypoint.sh outside a container: copies the vendored script and
# ABOUTME: applies the runtime stage's RUN that edits it, so tests start the file the image ships.
import subprocess
from pathlib import Path

from tests.dockerfile import REPO_ROOT, parse

VENDORED = REPO_ROOT / "src" / "entrypoint.sh"


def build(directory: Path) -> Path:
    entrypoint = directory / "entrypoint.sh"
    entrypoint.write_bytes(VENDORED.read_bytes())
    entrypoint.chmod(0o755)
    for run in parse(REPO_ROOT / "Dockerfile").final.args_of("RUN"):
        if "entrypoint.sh" in run:
            subprocess.run(["/bin/sh", "-c", run], cwd=directory, check=True)
    return entrypoint


def image_uvicorn_env() -> dict:
    env = parse(REPO_ROOT / "Dockerfile").final.env()
    return {key: value for key, value in env.items() if key.startswith("UVICORN_")}
