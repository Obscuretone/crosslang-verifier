"""Dependency injection boundary for adapters, resolution, rules and execution."""

from dataclasses import dataclass
from typing import Protocol

from .adapters import TreeSitterAdapter
from .candidates import CandidateGenerator
from .models import Execution, FallbackIR, Pair, Resolution, Source, Value
from .resolution import AssumptionResolver
from .rules import RuleRegistry


class Adapter(Protocol):
    def normalize(self, source: Source) -> FallbackIR: ...


class Resolver(Protocol):
    def resolve(self, pair: Pair, ts: FallbackIR, rust: FallbackIR) -> Resolution: ...


class Candidates(Protocol):
    def generate(self, resolution: Resolution, ts: FallbackIR, rust: FallbackIR) -> list[Value]: ...


class Runner(Protocol):
    def execute(
        self, pair: Pair, resolution: Resolution, candidates: list[Value]
    ) -> list[Execution]: ...


@dataclass
class Context:
    adapters: dict[str, Adapter]
    resolver: Resolver
    candidates: Candidates
    rules: RuleRegistry
    runner: Runner


def build_context(runner: Runner) -> Context:
    return Context(
        {language: TreeSitterAdapter(language) for language in ("typescript", "rust")},
        AssumptionResolver(),
        CandidateGenerator(),
        RuleRegistry(),
        runner,
    )
