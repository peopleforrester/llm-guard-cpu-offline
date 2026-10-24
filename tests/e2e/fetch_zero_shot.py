# ABOUTME: Downloads the BanTopics zero-shot weights from the URLs model-zero-shot/Dockerfile ADDs, and
# ABOUTME: verifies each file against the sha256 that Dockerfile pins, so the E2E scans the bytes the image ships.
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.dockerfile import parse
from tests.e2e.fetch_weights import sha256

ADD = re.compile(r"--checksum=sha256:([0-9a-f]{64}) --chmod=644 (https://\S+) /model/(\S+)")


def pinned_files() -> list[tuple[str, str, str]]:
    dockerfile = parse(REPO_ROOT / "model-zero-shot" / "Dockerfile")
    files = []
    for args in dockerfile.final.args_of("ADD"):
        match = ADD.fullmatch(args)
        if not match:
            raise SystemExit(f"model-zero-shot/Dockerfile ADD is not checksum-pinned: {args}")
        checksum, url, name = match.groups()
        files.append((name, url, checksum))
    if not files:
        raise SystemExit("model-zero-shot/Dockerfile ADDs no files")
    return files


def _download(url: str, destination: Path, label: str) -> None:
    start, done = time.monotonic(), 0
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as out:
        size = int(response.headers["Content-Length"])
        for chunk in iter(lambda: response.read(1 << 20), b""):
            out.write(chunk)
            done += len(chunk)
            elapsed = time.monotonic() - start
            eta = (size - done) / (done / elapsed) if done and elapsed else 0
            print(
                f"\r  {label}: {done / size:6.1%} of {size / 1e6:,.1f} MB, ~{eta:,.0f}s left",
                end="",
                flush=True,
            )
    print()
    if done != size:
        raise SystemExit(f"{label}: received {done} bytes, the server announced {size}")


def fetch(target: Path) -> None:
    files = pinned_files()
    target.mkdir(parents=True, exist_ok=True)
    for index, (name, url, checksum) in enumerate(files, start=1):
        path = target / name
        if path.is_file() and sha256(path) == checksum:
            print(f"  {name}: already present and verified")
            continue
        _download(url, path, f"{index}/{len(files)} {name}")
        actual = sha256(path)
        if actual != checksum:
            raise SystemExit(f"{name}: sha256 {actual}, model-zero-shot/Dockerfile pins {checksum}")
    print(f"Zero-shot weights verified against model-zero-shot/Dockerfile in {target}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: fetch_zero_shot.py <target directory>")
    fetch(Path(sys.argv[1]).resolve())
