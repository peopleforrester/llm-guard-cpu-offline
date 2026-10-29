# ABOUTME: Guards the packaging-owned overrides of the vendored pins: the OpenTelemetry set moves as one
# ABOUTME: release past the tracestate fix, and the Dockerfile and the E2E install both apply it.
import re
import tomllib

from packaging.requirements import Requirement
from packaging.version import Version

from tests.dockerfile import REPO_ROOT, parse

OVERRIDES_FILE = REPO_ROOT / "overrides.txt"
DOCKERFILE = parse(REPO_ROOT / "Dockerfile")
# Dependabot alert #1: opentelemetry-api's tracestate parsing is fixed in this release.
TRACESTATE_FIX = Version("1.45.1")


def _overrides() -> dict[str, Requirement]:
    lines = [line.strip() for line in OVERRIDES_FILE.read_text().splitlines()]
    requirements = [Requirement(line) for line in lines if line and not line.startswith("#")]
    return {r.name: r for r in requirements}


def _upstream() -> dict[str, Requirement]:
    project = tomllib.loads((REPO_ROOT / "src" / "pyproject.toml").read_text())["project"]
    requirements = [Requirement(line) for line in project["dependencies"]]
    return {r.name: r for r in requirements}


def _pinned_version(requirement: Requirement) -> Version:
    (specifier,) = requirement.specifier
    assert specifier.operator == "==", requirement
    return Version(specifier.version)


def test_every_override_is_an_exact_pin_of_a_package_upstream_declares():
    upstream = _upstream()
    for name, requirement in _overrides().items():
        assert name in upstream, f"{name} is not a dependency of src/pyproject.toml"
        _pinned_version(requirement)


def test_opentelemetry_api_is_past_the_tracestate_fix():
    assert _pinned_version(_overrides()["opentelemetry-api"]) >= TRACESTATE_FIX


def test_every_package_of_upstreams_opentelemetry_release_moves_together():
    upstream, overrides = _upstream(), _overrides()
    # Upstream pins the core packages and the contrib b-releases of one release, identified here by
    # the api and the FastAPI instrumentation. Every package upstream pins to either moves.
    def pinned_with(package: str) -> set[str]:
        version = _pinned_version(upstream[package])
        return {name for name, r in upstream.items() if name.startswith("opentelemetry-") and _pinned_version(r) == version}

    core = pinned_with("opentelemetry-api")
    contrib = pinned_with("opentelemetry-instrumentation-fastapi")
    assert core == {"opentelemetry-api", "opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-http"}
    assert contrib == {"opentelemetry-instrumentation-fastapi", "opentelemetry-exporter-prometheus"}

    assert len({_pinned_version(overrides[name]) for name in core}) == 1
    (contrib_version,) = {_pinned_version(overrides[name]) for name in contrib}
    assert contrib_version.is_prerelease


def test_builder_installs_the_package_with_the_overrides():
    builder = DOCKERFILE.stage("builder")
    assert "--chown=user:user overrides.txt ./" in builder.args_of("COPY")
    (install,) = [run for run in builder.args_of("RUN") if '".[cpu]"' in run]
    assert re.fullmatch(r'uv pip install --no-cache --override overrides\.txt "\.\[cpu\]"', install), install


def test_uv_is_pinned_and_installed_outside_the_venv_that_ships():
    builder = DOCKERFILE.stage("builder")
    names = [name for name, _ in builder.instructions]
    (uv_install,) = [i for i, (name, args) in enumerate(builder.instructions) if name == "RUN" and "uv==" in args]
    assert re.search(r"\buv==\d+\.\d+\.\d+\b", builder.instructions[uv_install][1])
    # As root, before the venv exists and before USER, so it lands in the system Python and the
    # runtime stage's copy of /home/user/.venv does not carry it.
    assert uv_install < names.index("USER")
    assert not any("uv" in args.split() for args in DOCKERFILE.final.args_of("RUN"))


def test_e2e_install_applies_the_same_overrides():
    run_sh = (REPO_ROOT / "tests" / "e2e" / "run.sh").read_text()
    (install,) = [line for line in run_sh.splitlines() if "/src[cpu]" in line]
    assert '--override "$REPO_ROOT/overrides.txt"' in install, install
