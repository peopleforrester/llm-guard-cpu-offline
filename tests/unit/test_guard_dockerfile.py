# ABOUTME: Guards the properties the guard image exists for: CPU-only torch, weights from our pinned
# ABOUTME: mirror, Hugging Face offline at runtime, and no compiler in the stage that ships.
import json
import re

import pytest

from tests.dockerfile import REPO_ROOT, parse

DOCKERFILE = parse(REPO_ROOT / "Dockerfile")
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def test_stages_are_model_builder_then_runtime():
    assert [s.name for s in DOCKERFILE.stages] == ["model", "builder", None]
    assert DOCKERFILE.stage("model").base == "${MODEL_IMAGE}"
    assert DOCKERFILE.stage("builder").base == "python:3.12-slim"
    assert DOCKERFILE.final.base == "python:3.12-slim"


def test_model_image_is_pinned_by_digest():
    assert DIGEST.search(DOCKERFILE.args["MODEL_IMAGE"]), DOCKERFILE.args["MODEL_IMAGE"]


def test_torch_comes_pinned_from_the_cpu_index_before_the_package_install():
    runs = DOCKERFILE.stage("builder").args_of("RUN")
    torch_runs = [i for i, run in enumerate(runs) if re.search(r"\btorch\b", run)]
    assert len(torch_runs) == 1, runs
    torch_run = runs[torch_runs[0]]
    assert re.search(r"torch==\d+\.\d+\.\d+", torch_run), torch_run
    assert "--index-url https://download.pytorch.org/whl/cpu" in torch_run

    package_runs = [i for i, run in enumerate(runs) if '".[cpu]"' in run]
    assert len(package_runs) == 1, runs
    assert torch_runs[0] < package_runs[0]


def test_builder_takes_the_weights_from_the_model_stage():
    copies = DOCKERFILE.stage("builder").args_of("COPY")
    assert any(c.startswith("--from=model") and "/model ${WIB_PI_MODEL_DIR}" in c for c in copies)
    assert any(c.startswith("--from=model") and "/LICENSE" in c for c in copies)


def test_nothing_in_the_build_downloads_from_hugging_face():
    for stage in DOCKERFILE.stages:
        for _, args in stage.instructions:
            assert "huggingface" not in args.lower(), args
            assert "hf_hub_download" not in args, args


@pytest.mark.parametrize("variable", ["HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"])
def test_runtime_switches_hugging_face_offline(variable):
    assert DOCKERFILE.final.env()[variable] == "1"


def test_runtime_points_the_scanner_at_the_baked_in_model():
    assert DOCKERFILE.final.env()["WIB_PI_MODEL_DIR"] == "/home/user/models/prompt-injection"
    copies = DOCKERFILE.final.args_of("COPY")
    assert any(
        c.startswith("--from=builder") and c.endswith("/home/user/models /home/user/models")
        for c in copies
    ), copies


def test_runtime_has_no_compiler():
    runs = " ".join(DOCKERFILE.final.args_of("RUN"))
    for package in ["build-essential", "gcc", "g++", "linux-libc-dev"]:
        assert package not in runs
    assert "libgomp1" in runs


def test_runtime_runs_as_an_unprivileged_user():
    assert DOCKERFILE.final.args_of("USER") == ["user"]


def test_runtime_ships_the_upstream_license_and_the_entrypoint():
    copies = DOCKERFILE.final.args_of("COPY")
    assert any("src/LICENSE.upstream" in c for c in copies)
    assert any("src/entrypoint.sh ./entrypoint.sh" in c for c in copies)
    (entrypoint,) = DOCKERFILE.final.args_of("ENTRYPOINT")
    shell, flag, script, name = json.loads(entrypoint)
    assert (shell, flag, name) == ("/bin/sh", "-c", "entrypoint.sh")
    assert script.endswith('; exec ./entrypoint.sh "$@"'), script


def test_runtime_default_config_is_the_offline_one_not_the_vendored_one():
    copies = DOCKERFILE.final.args_of("COPY")
    configs = [c for c in copies if c.endswith(" ./config/scanners.yml")]
    assert configs == ["--chown=user:user config/scanners.yml ./config/scanners.yml"], copies


def test_every_copied_source_exists_in_the_repository():
    for stage in DOCKERFILE.stages:
        for copy in stage.args_of("COPY"):
            if "--from=" in copy:
                continue
            sources = [part for part in copy.split() if not part.startswith("--")][:-1]
            for source in sources:
                assert (REPO_ROOT / source).exists(), source
