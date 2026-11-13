"""Analysis orchestration. Context services are locally aliased at entry."""

from dataclasses import asdict

from .context import Context
from .models import InputError, Pair, Report


def analyze(context: Context, pair: Pair, execute: bool = False) -> Report:
    adapters, resolver = context.adapters, context.resolver
    candidates_service, rules, runner = context.candidates, context.rules, context.runner
    report = Report(
        pair.id,
        "unsupported",
        {"typescript": pair.typescript.sha256, "rust": pair.rust.sha256},
        pair.manifest_sha256,
        pair.assumptions,
        limitations=[
            "Bounded candidates under declared assumptions; no full semantic equivalence."
        ],
    )
    try:
        ts, rust = (
            adapters["typescript"].normalize(pair.typescript),
            adapters["rust"].normalize(pair.rust),
        )
        report.ir = [ts, rust]
        resolution = resolver.resolve(pair, ts, rust)
        report.resolution = asdict(resolution)
        report.candidates = candidates_service.generate(resolution, ts, rust)
        report.assessments = rules.assess(ts, rust, resolution, report.candidates)
    except InputError as exc:
        report.limitations.append(str(exc))
        return report
    if not report.assessments:
        report.limitations.append("No registered semantic rule applies to the resolved IR")
        return report
    report.status = (
        "static_warning" if any(a.warning for a in report.assessments) else "static_checked"
    )
    if not execute:
        report.limitations.append("Implementations were not executed")
        return report
    report.executions = runner.execute(pair, resolution, report.candidates)
    by_language = {run.language: run for run in report.executions}
    valid = (
        len(report.executions) == 2
        and set(by_language) == {"typescript", "rust"}
        and all(
            run.status == "ok" and len(run.observations) == len(report.candidates)
            for run in report.executions
        )
    )
    if not valid:
        report.status = "inconclusive"
        report.limitations.append("Both runners must succeed with a complete observation protocol")
        return report
    for index, candidate in enumerate(report.candidates):
        left, right = (by_language[lang].observations[index] for lang in ("typescript", "rust"))
        if left != right:
            report.differences.append(
                {
                    "candidate_index": index,
                    "input": asdict(candidate),
                    "typescript": asdict(left),
                    "rust": asdict(right),
                }
            )
    report.status = "confirmed_difference" if report.differences else "no_difference_observed"
    return report
