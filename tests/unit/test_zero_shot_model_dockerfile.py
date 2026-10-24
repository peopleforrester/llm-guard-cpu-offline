# ABOUTME: Guards the BanTopics weights image: a scratch result that executes nothing, every file pinned to
# ABOUTME: the revision and a sha256, and one set of hashes agreed by the Dockerfile and the license file.
import re

from tests.dockerfile import REPO_ROOT, parse

MODEL_DIR = REPO_ROOT / "model-zero-shot"
DOCKERFILE = parse(MODEL_DIR / "Dockerfile")
REPOSITORY = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"
REVISION = "8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8"
FILES = {
    "added_tokens.json",
    "config.json",
    "model.onnx",
    "special_tokens_map.json",
    "spm.model",
    "tokenizer.json",
    "tokenizer_config.json",
}
# The two LFS hashes the Hugging Face API publishes for this revision.
LFS_HASHES = {
    "model.onnx": "d46fa6c1addc598abd34af8651120291f51417ddfce45b9d5f70bc32d3efa81c",
    "spm.model": "c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd",
}
HASH = re.compile(
    r"^\s*(?:#\s*(?:files)?\s*)?([\w.]+\.(?:json|onnx|model))\s+sha256\s+([0-9a-f]{64})\s*$",
    re.MULTILINE,
)
ADD = re.compile(r"^--checksum=sha256:([0-9a-f]{64}) --chmod=644 (https://\S+) /model/(\S+)$")


def _hashes(text: str) -> dict:
    return dict(HASH.findall(text))


def _adds() -> dict:
    adds = {}
    for args in DOCKERFILE.final.args_of("ADD"):
        match = ADD.fullmatch(args)
        assert match, f"ADD without a sha256 checksum, mode 644 and a /model/ destination: {args}"
        checksum, url, name = match.groups()
        assert url == f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/onnx/{name}", url
        adds[name] = checksum
    return adds


def test_result_is_a_single_scratch_stage():
    assert [s.base for s in DOCKERFILE.stages] == ["scratch"]
    assert DOCKERFILE.args == {}


def test_result_executes_nothing():
    assert DOCKERFILE.final.args_of("RUN") == []
    assert DOCKERFILE.final.args_of("ENTRYPOINT") == []
    assert DOCKERFILE.final.args_of("CMD") == []


def test_every_file_of_the_onnx_directory_is_added_at_the_top_level_with_its_checksum():
    assert set(_adds()) == FILES


def test_lfs_files_carry_the_hashes_the_hugging_face_api_publishes():
    adds = _adds()
    assert {name: adds[name] for name in LFS_HASHES} == LFS_HASHES


def test_provenance_agrees_everywhere_it_is_recorded():
    adds = _adds()
    assert _hashes((MODEL_DIR / "Dockerfile").read_text()) == adds
    assert _hashes((MODEL_DIR / "LICENSE.model").read_text()) == adds


def test_license_travels_with_the_weights():
    assert "LICENSE.model /LICENSE" in DOCKERFILE.final.args_of("COPY")
    license_text = (MODEL_DIR / "LICENSE.model").read_text()
    assert REPOSITORY in license_text
    assert REVISION in license_text
    assert "MIT License" in license_text
    assert "Permission is hereby granted, free of charge" in license_text


def test_image_labels_name_the_revision_and_the_license():
    labels = " ".join(DOCKERFILE.final.args_of("LABEL"))
    assert REVISION in labels
    assert "org.opencontainers.image.licenses=MIT" in labels
