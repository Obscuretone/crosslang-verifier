"""Console entry point and CI-friendly exit codes."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .context import build_context
from .engine import analyze
from .models import InputError, load_pair
from .reporting import ConsoleReporter, JsonReporter
from .runners import IsolatedRunner


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="crosslang-verifier — Find behavioral differences in cross-language rewrites."
    )
    result.add_argument("--version", action="version", version=__version__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("compare", "suite"):
        command = commands.add_parser(name)
        command.add_argument("path", type=Path, help="Pair manifest or fixture corpus directory")
        command.add_argument("--execute", action="store_true", help="Execute the original sources")
        command.add_argument(
            "--backend",
            choices=["docker", "local"],
            default="docker",
            help="local executes trusted sources with host permissions",
        )
        command.add_argument("--timeout", type=float, default=30)
        command.add_argument("--node-image", default="node:22-bookworm-slim")
        command.add_argument("--rust-image", default="rust:1-slim-bookworm")
        command.add_argument("--format", choices=["console", "json"], default="console")
        command.add_argument("--json-output", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        runner = IsolatedRunner(args.backend, args.timeout, args.node_image, args.rust_image)
        context = build_context(runner)
        paths = (
            [args.path] if args.command == "compare" else sorted(args.path.rglob("manifest.json"))
        )
        if not paths:
            raise InputError("No fixture manifests found")
        reports, expectations = [], []
        for path in paths:
            pair = load_pair(path)
            report = analyze(context, pair, args.execute)
            reports.append(report.to_dict())
            target = {"regression": "confirmed_difference", "control": "no_difference_observed"}
            expectations.append(
                {
                    "pair_id": pair.id,
                    "expected": pair.expected,
                    "passed": report.status == target[pair.expected]
                    if args.execute and pair.expected
                    else None,
                }
            )
        if args.command == "compare":
            payload = reports[0]
            code = (
                1
                if payload["status"] == "confirmed_difference"
                else 2
                if payload["status"] in {"inconclusive", "unsupported"}
                else 0
            )
        else:
            summary = dict(Counter(report["status"] for report in reports))
            failed = sum(e["passed"] is False for e in expectations)
            summary.update(
                total=len(reports),
                expected_passed=sum(e["passed"] is True for e in expectations),
                expected_failed=failed,
            )
            payload = {
                "schema_version": "1.0",
                "tool_version": __version__,
                "generated_at": datetime.now(UTC).isoformat(),
                "reports": reports,
                "expectations": expectations,
                "summary": summary,
                "equivalence_claim": False,
            }
            code = (
                2
                if any(r["status"] in {"inconclusive", "unsupported"} for r in reports)
                else 1
                if failed
                else 0
            )
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(JsonReporter().render(payload), encoding="utf-8")
        reporter = JsonReporter() if args.format == "json" else ConsoleReporter()
        sys.stdout.write(reporter.render(payload))
        return code
    except (InputError, OSError, ValueError) as exc:
        if args.format == "json":
            sys.stdout.write(JsonReporter().render({"schema_version": "1.0", "error": str(exc)}))
        else:
            print(f"crosslang-verifier: {exc}", file=sys.stderr)
        return 2
