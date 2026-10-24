# ABOUTME: Downloads the classifier weights from the model image the guard Dockerfile pins by digest,
# ABOUTME: unpacks them into a directory, and verifies them against the hashes in model/LICENSE.model.
import hashlib
import json
import re
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.dockerfile import parse

MEDIA_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
ACCEPT = ", ".join(MEDIA_TYPES)


def expected_hashes() -> dict:
    text = (REPO_ROOT / "model" / "LICENSE.model").read_text()
    hashes = dict(re.findall(r"(model\.onnx|spm\.model)\s+sha256\s+([0-9a-f]{64})", text))
    if set(hashes) != {"model.onnx", "spm.model"}:
        raise SystemExit(f"model/LICENSE.model records hashes for {sorted(hashes)}, not both files")
    return hashes


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified(target: Path, hashes: dict) -> bool:
    return all((target / name).is_file() and sha256(target / name) == h for name, h in hashes.items())


def _get(url: str, token: str, accept: str = "") -> urllib.request.Request:
    headers = {"Authorization": f"Bearer {token}"}
    if accept:
        headers["Accept"] = accept
    return urllib.request.Request(url, headers=headers)


def _json(url: str, token: str, accept: str = "") -> dict:
    with urllib.request.urlopen(_get(url, token, accept), timeout=60) as response:
        return json.load(response)


def _download(url: str, token: str, size: int, destination: Path, label: str) -> None:
    start, done = time.monotonic(), 0
    with urllib.request.urlopen(_get(url, token), timeout=60) as response, destination.open("wb") as out:
        for chunk in iter(lambda: response.read(1 << 20), b""):
            out.write(chunk)
            done += len(chunk)
            elapsed = time.monotonic() - start
            eta = (size - done) / (done / elapsed) if done and elapsed else 0
            print(
                f"\r  {label}: {done / size:6.1%} of {size / 1e6:,.0f} MB, ~{eta:,.0f}s left",
                end="",
                flush=True,
            )
    print()
    if done != size:
        raise SystemExit(f"{label}: received {done} bytes, the manifest says {size}")


def fetch(target: Path) -> None:
    hashes = expected_hashes()
    if verified(target, hashes):
        print(f"Weights already present and verified in {target}")
        return

    reference = parse(REPO_ROOT / "Dockerfile").args["MODEL_IMAGE"]
    match = re.fullmatch(r"([^/]+)/([^:@]+)(?::[^@]+)?@(sha256:[0-9a-f]{64})", reference)
    if not match:
        raise SystemExit(f"MODEL_IMAGE is not a registry/repository@digest reference: {reference}")
    registry, repository, digest = match.groups()
    if registry != "ghcr.io":
        raise SystemExit(f"Only ghcr.io anonymous pulls are implemented, MODEL_IMAGE is on {registry}")

    print(f"Fetching weights from {registry}/{repository}@{digest}")
    token = _json(f"https://ghcr.io/token?scope=repository:{repository}:pull", "")["token"]
    base = f"https://ghcr.io/v2/{repository}"
    manifest = _json(f"{base}/manifests/{digest}", token, ACCEPT)
    if "manifests" in manifest:
        amd64 = [
            m["digest"]
            for m in manifest["manifests"]
            if m.get("platform", {}).get("os") == "linux"
            and m["platform"].get("architecture") == "amd64"
        ]
        if len(amd64) != 1:
            raise SystemExit(f"Expected one linux/amd64 manifest in {digest}, found {len(amd64)}")
        manifest = _json(f"{base}/manifests/{amd64[0]}", token, ACCEPT)

    target.mkdir(parents=True, exist_ok=True)
    layers = manifest["layers"]
    for index, layer in enumerate(layers, start=1):
        blob = target.parent / f"layer-{index}.tar.gz"
        _download(f"{base}/blobs/{layer['digest']}", token, layer["size"], blob, f"layer {index}/{len(layers)}")
        if f"sha256:{sha256(blob)}" != layer["digest"]:
            raise SystemExit(f"layer {index} does not match its digest {layer['digest']}")
        with tarfile.open(blob) as archive:
            members = [m for m in archive.getmembers() if m.name.startswith("model/")]
            for member in members:
                member.name = member.name.removeprefix("model/")
            archive.extractall(target, members=[m for m in members if m.name], filter="data")
        blob.unlink()

    for name, expected in hashes.items():
        actual = sha256(target / name) if (target / name).is_file() else "missing"
        if actual != expected:
            raise SystemExit(f"{name}: sha256 {actual}, model/LICENSE.model records {expected}")
    print(f"Weights verified against model/LICENSE.model in {target}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: fetch_weights.py <target directory>")
    fetch(Path(sys.argv[1]).resolve())
