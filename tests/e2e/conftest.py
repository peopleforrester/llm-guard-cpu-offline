# ABOUTME: Preconditions for the offline scan tests: they refuse to run with a network, because a pass
# ABOUTME: with one proves nothing about scanning behind a default-deny egress policy.
import os
import socket
from pathlib import Path

import pytest


def pytest_sessionstart(session):
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3).close()
    except OSError:
        pass
    else:
        raise pytest.UsageError("E2E tests reached the network; run them through tests/e2e/run.sh")

    model_dir = os.environ.get("WIB_PI_MODEL_DIR")
    if not model_dir or not (Path(model_dir) / "model.onnx").is_file():
        raise pytest.UsageError(
            f"WIB_PI_MODEL_DIR={model_dir!r} holds no model.onnx; run through tests/e2e/run.sh"
        )


@pytest.fixture(scope="session")
def model_dir() -> str:
    return os.environ["WIB_PI_MODEL_DIR"]
