# ABOUTME: Exercises the vendored config loader: ${VAR:default} substitution, the shipped default
# ABOUTME: scanners.yml parsing into a Config, and a missing file reported rather than raised.
import pytest
from structlog.testing import capture_logs

from app.config import get_config, load_yaml
from tests.dockerfile import REPO_ROOT

DEFAULT_CONFIG = REPO_ROOT / "src" / "config" / "scanners.yml"


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


def test_shipped_default_config_parses(monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "token-from-env")

    config = get_config(str(DEFAULT_CONFIG))

    assert config.auth.type == "http_bearer"
    assert config.auth.token == "token-from-env"
    assert config.app.lazy_load is True
    assert config.metrics.exporter == "prometheus"
    input_types = [s.type for s in config.input_scanners]
    assert "PromptInjection" in input_types
    assert len(input_types) == len(set(input_types))
    assert [s.type for s in config.output_scanners]


def test_missing_file_is_logged_and_yields_no_config(tmp_path):
    missing = tmp_path / "absent.yml"

    with capture_logs() as logs:
        assert load_yaml(str(missing)) == {}
        assert get_config(str(missing)) is None

    errors = [entry for entry in logs if entry["log_level"] == "error"]
    assert [entry["event"] for entry in errors] == ["Error loading YAML file"] * 2
    assert all(isinstance(entry["exception"], FileNotFoundError) for entry in errors)
