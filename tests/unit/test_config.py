# ABOUTME: Exercises the vendored config loader: ${VAR:default} substitution, the image's default
# ABOUTME: scanners.yml loading only the baked-in classifier, and a missing file reported rather than raised.
import pytest
from structlog.testing import capture_logs

from app.config import get_config, load_yaml
from tests.dockerfile import REPO_ROOT

SHIPPED_CONFIG = REPO_ROOT / "config" / "scanners.yml"


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "scanners.yml"
    path.write_text(
        "app:\n"
        "  name: ${E2E_APP_NAME:Default Name}\n"
        "  lazy_load: ${E2E_LAZY_LOAD:true}\n"
        "auth:\n"
        "  type: http_bearer\n"
        "  token: ${E2E_AUTH_TOKEN:}\n"
        "input_scanners:\n"
        "  - type: PromptInjection\n"
        "    params:\n"
        "      threshold: 0.92\n"
        "      model_path: ${E2E_MODEL_DIR:/models/pi}\n"
        "output_scanners: []\n"
    )
    return path


def test_unset_variables_take_their_defaults(config_file, monkeypatch):
    for name in ["E2E_APP_NAME", "E2E_LAZY_LOAD", "E2E_AUTH_TOKEN", "E2E_MODEL_DIR"]:
        monkeypatch.delenv(name, raising=False)

    config = get_config(str(config_file))

    assert config.app.name == "Default Name"
    assert config.app.lazy_load is True
    assert config.auth.token == ""
    assert config.input_scanners[0].params["model_path"] == "/models/pi"


def test_set_variables_override_the_defaults(config_file, monkeypatch):
    monkeypatch.setenv("E2E_APP_NAME", "Guard")
    monkeypatch.setenv("E2E_LAZY_LOAD", "false")
    monkeypatch.setenv("E2E_AUTH_TOKEN", "s3cret")
    monkeypatch.setenv("E2E_MODEL_DIR", "/home/user/models/prompt-injection")

    config = get_config(str(config_file))

    assert config.app.name == "Guard"
    assert config.app.lazy_load is False
    assert config.auth.token == "s3cret"
    assert config.input_scanners[0].params == {
        "threshold": 0.92,
        "model_path": "/home/user/models/prompt-injection",
    }


def test_shipped_config_parses(monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "token-from-env")
    monkeypatch.setenv("WIB_PI_MODEL_DIR", "/home/user/models/prompt-injection")
    monkeypatch.setenv("WIB_ZS_MODEL_DIR", "/home/user/models/zero-shot")

    config = get_config(str(SHIPPED_CONFIG))

    assert config.auth.type == "http_bearer"
    assert config.auth.token == "token-from-env"
    assert config.metrics.exporter == "prometheus"


def test_shipped_config_loads_the_classifier_at_start(monkeypatch):
    monkeypatch.delenv("LAZY_LOAD", raising=False)
    monkeypatch.setenv("WIB_PI_MODEL_DIR", "/home/user/models/prompt-injection")
    monkeypatch.setenv("WIB_ZS_MODEL_DIR", "/home/user/models/zero-shot")

    assert get_config(str(SHIPPED_CONFIG)).app.lazy_load is False


def test_shipped_config_scans_only_with_the_baked_in_classifiers(monkeypatch):
    monkeypatch.setenv("WIB_PI_MODEL_DIR", "/models/pi")
    monkeypatch.setenv("WIB_ZS_MODEL_DIR", "/models/zs")

    config = get_config(str(SHIPPED_CONFIG))

    assert [(s.type, s.params) for s in config.input_scanners] == [
        (
            "PromptInjection",
            {
                "threshold": 0.92,
                "match_type": "truncate_head_tail",
                "model_max_length": 256,
                "model_path": "/models/pi",
            },
        ),
        (
            "BanTopics",
            {
                "topics": ["violence"],
                "threshold": 0.8,
                "model_max_length": 256,
                "model_path": "/models/zs",
            },
        ),
    ]
    assert config.output_scanners == []


def test_missing_file_is_logged_and_yields_no_config(tmp_path):
    missing = tmp_path / "absent.yml"

    with capture_logs() as logs:
        assert load_yaml(str(missing)) == {}
        assert get_config(str(missing)) is None

    errors = [entry for entry in logs if entry["log_level"] == "error"]
    assert [entry["event"] for entry in errors] == ["Error loading YAML file"] * 2
    assert all(isinstance(entry["exception"], FileNotFoundError) for entry in errors)
