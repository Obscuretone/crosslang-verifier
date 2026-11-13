#!/usr/bin/env python3
"""Reproduce independent functional-verification experiments with actual runtimes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from crosslang_verifier.function_runner import FunctionRunner
from crosslang_verifier.modelcheck import ModelChecker
from crosslang_verifier.parity import ParityContext
from crosslang_verifier.runners import IsolatedRunner
from crosslang_verifier.syntax import build_syntax_context
from crosslang_verifier.verification import CandidateBank, VerificationContext, verify_functions

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["docker", "local"], default="docker")
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    context = VerificationContext(
        ParityContext(build_syntax_context()),
        FunctionRunner(IsolatedRunner(args.backend, args.timeout)),
        ModelChecker(),
        CandidateBank(),
    )
    corpus = ROOT / "examples/verification"
    results = []
    for case in json.loads((corpus / "cases.json").read_text()):
        folder = corpus / case["id"]
        report = verify_functions(
            context,
            folder / "before.ts",
            folder / "after.rs",
            assume_option_mapping=case["assume_option_mapping"],
        )
        passed = report["status"] == case["expected"]
        if case["id"] == "solver-branch":
            passed &= any(d["origin"] == "solver" for d in report["functions"][0]["differences"])
        if case["id"] == "compile-error":
            passed &= report["ast_status"] == "parity" and any(
                execution["status"] == "error"
                and execution["language"] == "rust"
                and "unknown character escape" in execution["stderr"]
                for execution in report["functions"][0].get("executions", [])
            )
        results.append(
            {"id": case["id"], "expected": case["expected"], "passed": passed, "report": report}
        )
        print(f"{case['id']}: {report['status']} ({'PASS' if passed else 'FAIL'})", flush=True)
    summary = {
        "total": len(results),
        "passed": sum(case["passed"] for case in results),
        "statuses": dict(Counter(case["report"]["status"] for case in results)),
    }
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "backend": args.backend,
        "summary": summary,
        "cases": results,
        "equivalence_claim": False,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
