"""Execute and check an independent reproduction of the linked fallback regression."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from crosslang_verifier.context import build_context
from crosslang_verifier.engine import analyze
from crosslang_verifier.models import InputError, Report, Value, load_pair
from crosslang_verifier.runners import IsolatedRunner

LINKEDIN_POST = "https://lnkd.in/p/gcqsjx2n"
TECHNICAL_SOURCE = (
    "https://github.blog/ai-and-ml/generative-ai/"
    "migrating-the-github-copilot-runtime-to-rust-using-copilot/"
)
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "linkedin-error-fallback"
INPUTS = [Value("undefined"), Value("null"), Value("string", ""), Value("string", "timeout")]


def verify_reports(regression: Report, control: Report) -> dict[str, bool]:
    """Check the specific observed witness and controls, not a simulated language model."""
    empty_difference = {
        "candidate_index": 2,
        "input": {"kind": "string", "value": ""},
        "typescript": {"kind": "string", "value": "Unknown error"},
        "rust": {"kind": "string", "value": ""},
    }
    expected = [
        Value("string", text)
        for text in ["Unknown error", "Unknown error", "Unknown error", "timeout"]
    ]
    return {
        "complete_four_input_domain": regression.candidates == control.candidates == INPUTS,
        "regression_confirmed_by_execution": regression.status == "confirmed_difference",
        "only_empty_string_is_a_counterexample": regression.differences == [empty_difference],
        "preserving_version_matches_candidates": (
            control.status == "no_difference_observed"
            and not control.differences
            and {run.language for run in control.executions} == {"typescript", "rust"}
            and len(control.executions) == 2
            and all(
                run.status == "ok" and run.observations == expected for run in control.executions
            )
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the LinkedIn/GitHub empty-error fallback example "
        "with real Node and Cargo."
    )
    parser.add_argument(
        "--backend",
        choices=["docker", "local"],
        default="docker",
        help="local executes only trusted sources with host permissions",
    )
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--format", choices=["console", "json"], default="console")
    args = parser.parse_args(argv)
    try:
        context = build_context(IsolatedRunner(args.backend, args.timeout))
        reports = [
            analyze(context, load_pair(EXAMPLE / name), execute=True)
            for name in ("regression.json", "control.json")
        ]
        checks = verify_reports(*reports)
        inconclusive = any(r.status in {"unsupported", "inconclusive"} for r in reports)
        code = 2 if inconclusive else 0 if all(checks.values()) else 1
        payload = {
            "schema_version": "1.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "linkedin_post": LINKEDIN_POST,
            "technical_source": TECHNICAL_SOURCE,
            "reproduction": "Independent minimal example; no audit of GitHub's source code.",
            "status": "inconclusive" if inconclusive else "passed" if code == 0 else "failed",
            "checks": checks,
            "reports": [report.to_dict() for report in reports],
            "equivalence_claim": False,
        }
    except (InputError, OSError, ValueError) as exc:
        code, payload = 2, {"schema_version": "1.0", "status": "inconclusive", "error": str(exc)}
    output = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(output, encoding="utf-8")
    if args.format == "json":
        print(output, end="")
    else:
        print(f"crosslang-verifier LinkedIn example: {payload['status']}")
        for name, passed in payload.get("checks", {}).items():
            print(f"  {'PASS' if passed else 'FAIL'} {name}")
        if "error" in payload:
            print(payload["error"])
        for report in payload.get("reports", []):
            for run in report["executions"]:
                if run["error"]:
                    print(f"  {report['pair_id']} / {run['language']}: {run['error']}")
        print("Bounded observations only; no full semantic equivalence is claimed.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
