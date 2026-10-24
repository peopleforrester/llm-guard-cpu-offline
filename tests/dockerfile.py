# ABOUTME: A minimal Dockerfile reader for the tests: joins continuation lines and splits the file
# ABOUTME: into build stages of (instruction, arguments) pairs, so assertions can name a stage.
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Stage:
    base: str
    name: str | None
    instructions: list[tuple[str, str]] = field(default_factory=list)

    def args_of(self, instruction: str) -> list[str]:
        return [args for name, args in self.instructions if name == instruction]

    def env(self) -> dict:
        values = {}
        for args in self.args_of("ENV"):
            for key, value in re.findall(r"(\w+)=(\S+)", args):
                values[key] = value
        return values


@dataclass
class Dockerfile:
    args: dict
    stages: list[Stage]

    def stage(self, name: str) -> Stage:
        matches = [s for s in self.stages if s.name == name]
        assert len(matches) == 1, f"expected one stage named {name!r}, found {len(matches)}"
        return matches[0]

    @property
    def final(self) -> Stage:
        return self.stages[-1]


def _logical_lines(text: str) -> list[str]:
    lines, current = [], ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not current and (not stripped or stripped.startswith("#")):
            continue
        if current and stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            current += stripped[:-1] + " "
            continue
        lines.append(current + stripped)
        current = ""
    assert not current, "Dockerfile ends inside a line continuation"
    return lines


def parse(path: Path) -> Dockerfile:
    args, stages = {}, []
    for line in _logical_lines(path.read_text()):
        instruction, _, rest = line.partition(" ")
        instruction, rest = instruction.upper(), rest.strip()
        if instruction == "FROM":
            parts = rest.split()
            name = parts[2] if len(parts) == 3 and parts[1].upper() == "AS" else None
            stages.append(Stage(base=parts[0], name=name))
        elif not stages and instruction == "ARG":
            key, _, value = rest.partition("=")
            args[key] = value
        else:
            assert stages, f"{instruction} before the first FROM in {path}"
            stages[-1].instructions.append((instruction, rest))
    return Dockerfile(args=args, stages=stages)
