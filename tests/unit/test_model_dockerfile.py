# ABOUTME: Guards the weights image: a pinned source, a scratch result carrying the license, and one
# ABOUTME: set of provenance hashes agreed by the Dockerfile, the license file, and the README.
import re

from tests.dockerfile import REPO_ROOT, parse

MODEL_DIR = REPO_ROOT / "model"
DOCKERFILE = parse(MODEL_DIR / "Dockerfile")
REVISION = "90c9989b1a342275dd0d1a95aad283c04e075671"
HASH = re.compile(r"(model\.onnx|spm\.model)\s+sha256\s+([0-9a-f]{64})")


def _hashes(text: str) -> dict:
    return dict(HASH.findall(text))


def test_source_image_is_pinned_by_digest():
    assert re.search(r"@sha256:[0-9a-f]{64}$", DOCKERFILE.args["MODEL_SOURCE"])


def test_result_is_scratch_with_the_weights_and_the_license():
    assert DOCKERFILE.final.base == "scratch"
    copies = DOCKERFILE.final.args_of("COPY")
    assert "--from=source /home/user/models/prompt-injection /model" in copies
    assert "LICENSE.model /LICENSE" in copies
    assert (MODEL_DIR / "LICENSE.model").is_file()


def test_result_executes_nothing():
    assert DOCKERFILE.final.args_of("RUN") == []
    assert DOCKERFILE.final.args_of("ENTRYPOINT") == []
    assert DOCKERFILE.final.args_of("CMD") == []


def test_provenance_agrees_everywhere_it_is_recorded():
    dockerfile = _hashes((MODEL_DIR / "Dockerfile").read_text())
    license_file = _hashes((MODEL_DIR / "LICENSE.model").read_text())
    assert set(dockerfile) == {"model.onnx", "spm.model"}
    assert dockerfile == license_file


def test_revision_agrees_everywhere_it_is_recorded():
    for path in [MODEL_DIR / "Dockerfile", MODEL_DIR / "LICENSE.model", REPO_ROOT / "README.md"]:
        assert REVISION in path.read_text(), path
    assert "LICENSE.model" in (REPO_ROOT / "Dockerfile").read_text()
