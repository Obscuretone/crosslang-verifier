"""Rule registry: consume resolved IR only; static predictions never confirm a bug."""

from typing import Protocol

from .models import FallbackIR, Resolution, RuleAssessment, Value


class Rule(Protocol):
    def assess(
        self, ts: FallbackIR, rust: FallbackIR, resolution: Resolution, candidates: list[Value]
    ) -> RuleAssessment | None: ...


def predicted(ir: FallbackIR, value: Value) -> Value:
    use_fallback = (
        value.falsy
        if ir.trigger in {"falsy", "filtered_falsy"}
        else value.kind in {"null", "undefined"}
    )
    return ir.fallback if use_fallback else value


class TruthinessFallbackRule:
    def assess(
        self, ts: FallbackIR, rust: FallbackIR, resolution: Resolution, candidates: list[Value]
    ) -> RuleAssessment | None:
        if ts.trigger not in {"falsy", "nullish"} or rust.trigger not in {"none", "filtered_falsy"}:
            return None
        differs = any(predicted(ts, v) != predicted(rust, v) for v in candidates)
        message = (
            "Resolved fallback policies predict a candidate difference; execution required."
            if differs
            else "No candidate difference predicted under assumptions; execution required."
        )
        return RuleAssessment("OT-FALLBACK-001", message, differs)


class RuleRegistry:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = rules if rules is not None else [TruthinessFallbackRule()]

    def assess(
        self, ts: FallbackIR, rust: FallbackIR, resolution: Resolution, candidates: list[Value]
    ) -> list[RuleAssessment]:
        return [
            assessment
            for rule in self.rules
            if (assessment := rule.assess(ts, rust, resolution, candidates)) is not None
        ]
