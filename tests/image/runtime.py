# ABOUTME: The container runtime call shared by the image E2E fixtures and tests, and the bearer token
# ABOUTME: the test config sets, so the fixture that writes it and the tests that send it agree.
import subprocess

TOKEN = "e2e-token"


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["docker", *args], check=False, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"docker {args[0]} exited {result.returncode}:\n{result.stderr}")
    return result
