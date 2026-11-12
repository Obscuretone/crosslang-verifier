"""Shared, language-neutral IR and versioned report data."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class InputError(ValueError):
    """Invalid manifest, unsupported source, or untrusted resolution evidence."""


@dataclass(frozen=True)
class Value:
    """Lossless primitive wire value; non-finite numbers and -0 have explicit tags."""

    kind: str
    value: str | bool | None = None

    def __post_init__(self) -> None:
        if self.kind in {"null", "undefined"} and self.value is None:
            return
        if self.kind == "boolean" and type(self.value) is bool:
            return
        if self.kind == "string" and isinstance(self.value, str):
            # Rust strings cannot contain lone UTF-16 surrogates.
            try:
                self.value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise InputError("Lone UTF-16 surrogates are outside the shared domain") from exc
            return
        if self.kind == "number" and isinstance(self.value, str):
            if self.value in {"NaN", "Infinity", "-Infinity", "-0"}:
                return
            try:
                number = float(self.value)
            except ValueError as exc:
                raise InputError("Invalid numeric wire value") from exc
            if math.isfinite(number) and not (number == 0 and self.value.startswith("-")):
                object.__setattr__(self, "value", str(number))
                return
        raise InputError(f"Invalid wire value: {self.kind!r}, {self.value!r}")

    @property
    def falsy(self) -> bool:
        return (
            self.kind in {"null", "undefined"}
            or (self.kind == "boolean" and self.value is False)
            or (self.kind == "string" and self.value == "")
            or (self.kind == "number" and self.value in {"0.0", "-0", "NaN"})
        )


@dataclass(frozen=True)
class Span:
    path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class FallbackIR:
    language: str
    function: str
    parameter: str
    parameter_type: str
    trigger: str  # falsy, nullish, none, or filtered_falsy
    fallback: Value
    span: Span
    source_sha256: str


@dataclass(frozen=True)
class Source:
    path: Path
    function: str
    content: str
    sha256: str


@dataclass(frozen=True)
class Pair:
    id: str
    typescript: Source
    rust: Source
    assumptions: dict[str, Any]
    manifest_sha256: str
    expected: str | None = None


@dataclass(frozen=True)
class Resolution:
    domain: str
    rust_inner: str
    evidence: dict[str, Any]
    allowed_inputs: tuple[Value, ...] | None = None


@dataclass(frozen=True)
class RuleAssessment:
    rule_id: str
    message: str
    warning: bool


@dataclass
class Execution:
    language: str
    status: str
    observations: list[Value] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    backend: str = ""
    isolation: str = ""


@dataclass
class Report:
    pair_id: str
    status: str
    sources: dict[str, str]
    manifest_sha256: str
    assumptions: dict[str, Any]
    resolution: dict[str, Any] | None = None
    ir: list[FallbackIR] = field(default_factory=list)
    assessments: list[RuleAssessment] = field(default_factory=list)
    candidates: list[Value] = field(default_factory=list)
    executions: list[Execution] = field(default_factory=list)
    differences: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    schema_version: str = "1.0"
    equivalence_claim: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_pair(path: Path) -> Pair:
    try:
        if path.stat().st_size > 131_072:
            raise InputError("Manifest exceeds 128 KiB")
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if data["schema_version"] != 1:
            raise InputError("Unsupported manifest schema_version")
        sources = []
        for language in ("typescript", "rust"):
            entry = data[language]
            source_path = (path.parent / entry["path"]).resolve()
            if source_path.stat().st_size > 65_536:
                raise InputError("Source exceeds 64 KiB")
            source = source_path.read_text(encoding="utf-8")
            sha = digest(source)
            if sha != entry["sha256"]:
                raise InputError(f"{language} source hash mismatch; re-review assumptions")
            name = entry.get("function", "evaluate")
            if not isinstance(name, str) or not name.isascii() or not name.isidentifier():
                raise InputError("Function name must be an ASCII identifier")
            sources.append(Source(source_path, name, source, sha))
        if not isinstance(data["id"], str) or not isinstance(data["assumptions"], dict):
            raise InputError("id must be a string and assumptions must be an object")
        expected = data.get("expected")
        if expected not in {None, "regression", "control"}:
            raise InputError("expected must be regression or control")
        return Pair(data["id"], *sources, data["assumptions"], digest(content), expected)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError(f"Invalid manifest {path}: {exc}") from exc
