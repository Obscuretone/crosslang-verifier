"""Scoped functional checks: native evidence first, model claims kept explicit."""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .function_runner import DOMAINS, FunctionRunner
from .modelcheck import ModelChecker
from .models import InputError, Value
from .parity import ParityContext, compare_parity, named, part, source


class CandidateBank:
    def generate(self, function: dict, modules: list[dict], missing: list[list[str]], limit: int):
        literals = {"f64": [], "string": []}

        def visit(node):
            if isinstance(node, dict):
                if node.get("kind") == "literal" and node.get("type") in literals:
                    literals[node["type"]].append(node["value"])
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for item in node:
                    visit(item)

        for module in modules:
            visit(module)
        banks, finite = [], True
        for type_, absent in zip(function["parameters"], missing, strict=True):
            base = type_["option"] if isinstance(type_, dict) else type_
            finite &= base == "bool"
            if base == "bool":
                bank = [Value("boolean", False), Value("boolean", True)]
            elif base == "string":
                bank = [Value("string", text) for text in ["", "a", "0", "é😀", *literals[base]]]
            else:
                texts = [
                    "0",
                    "-0",
                    "NaN",
                    "Infinity",
                    "-Infinity",
                    "1",
                    "-1",
                    "2",
                    "5e-324",
                    "-5e-324",
                    "2.2250738585072014e-308",
                    "1.7976931348623157e308",
                    "9007199254740992",
                ]
                for text in literals[base]:
                    value = float(text)
                    texts.extend(
                        [
                            text,
                            repr(math.nextafter(value, -math.inf)),
                            repr(math.nextafter(value, math.inf)),
                        ]
                    )
                bank = []
                for text in texts:
                    if text in {"inf", "-inf"}:
                        text = "Infinity" if text == "inf" else "-Infinity"
                    if float(text) == 0 and text.startswith("-"):
                        text = "-0"
                    bank.append(Value("number", text))
            bank.extend(Value(kind) for kind in absent)
            banks.append(list(dict.fromkeys(bank)))
        total = math.prod(len(bank) for bank in banks)
        if finite and total <= limit:
            return [list(case) for case in itertools.product(*banks)], True
        cases = []

        def add(case):
            if len(cases) < limit and case not in cases:
                cases.append(case)

        baseline = [bank[0] for bank in banks]
        add(baseline)
        for i, bank in enumerate(banks):
            for value in bank:
                case = baseline.copy()
                case[i] = value
                add(case)
        for i in range(max((len(bank) for bank in banks), default=0)):
            add([bank[i % len(bank)] for bank in banks])
        for case in itertools.islice(itertools.product(*banks), limit):
            add(list(case))
        return cases, False


@dataclass
class VerificationContext:
    parity: ParityContext
    runner: FunctionRunner
    solver: ModelChecker
    candidates: CandidateBank


def nullish_inputs(parsed: dict, name: str) -> list[list[str]]:
    for item in named(parsed["ast"]):
        node = part(item, "declaration") if item["type"] == "export_statement" else item
        if node and node["type"] == "function_declaration" and source(part(node, "name")) == name:
            return [
                [
                    kind
                    for kind in ("null", "undefined")
                    if kind in source(part(param, "type")).split("|")
                ]
                for param in named(part(node, "parameters"))
            ]
    raise InputError("TypeScript function declaration not found")


def supported_type(type_: object) -> bool:
    if isinstance(type_, dict):
        return set(type_) == {"option"} and type_["option"] in DOMAINS
    return type_ in DOMAINS


def verify_functions(
    context: VerificationContext,
    left: Path,
    right: Path,
    *,
    assume_option_mapping: bool = False,
    function_name: str | None = None,
    max_cases: int = 128,
) -> dict:
    parity, runner, solver, candidates = (
        context.parity,
        context.runner,
        context.solver,
        context.candidates,
    )
    if not 1 <= max_cases <= 4096:
        raise InputError("Case budget must be between 1 and 4096")
    ast = compare_parity(parity, left, right, assume_option_mapping)
    result = {
        "schema_version": "1.0",
        "mode": "functional_verification",
        "status": "inconclusive",
        "ast_status": ast["status"],
        "assumptions": ast["assumptions"],
        "sources": [
            {k: ast[side][k] for k in ("path", "language", "sha256")} for side in ("left", "right")
        ],
        "functions": [],
        "issues": ast["issues"],
        "equivalence_claim": False,
        "scope": "Pure deterministic return values only. Finite verification enumerates the "
        "declared shared input domain. Model verification proves the normalized loop-free IR, "
        "conditional on its source mappings, and additionally requires native sample agreement. "
        "No claim about arbitrary ports, effects, resources, timing or full semantic equivalence.",
    }
    if ast["status"] == "unresolved":
        result["reason"] = "Unresolved syntax, types or methods"
        return result
    parsed = {ast[side]["language"]: ast[side] for side in ("left", "right")}
    if set(parsed) != {"typescript", "rust"}:
        result["reason"] = "Verification requires one .ts and one .rs file"
        return result
    modules = [parsed[language]["shared_ast"] for language in ("typescript", "rust")]
    functions = [{f["name"]: f for f in module["functions"]} for module in modules]
    names = (
        [function_name]
        if function_name
        else sorted({f["name"] for module in modules for f in module["functions"] if f["public"]})
    )
    if not names:
        result["reason"] = "No public functions; select one with --function"
        return result
    sources = {}
    for language, file in parsed.items():
        content = Path(file["path"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != file["sha256"]:
            raise InputError("Source changed during verification")
        sources[language] = content.decode("utf-8")
    for name in names:
        report = {"name": name, "status": "inconclusive", "differences": []}
        result["functions"].append(report)
        a, b = [module.get(name) for module in functions]
        if not a or not b or any(a[key] != b[key] for key in ("parameters", "returns", "public")):
            report["reason"] = "Missing function or mismatched API signature"
            continue
        if (
            not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name)
            or not all(supported_type(t) for t in a["parameters"])
            or not isinstance(a["returns"], str)
            or a["returns"] not in DOMAINS
        ):
            report["reason"] = (
                "Native verification supports f64/bool/string inputs, optional "
                "primitive inputs under the declared contract, and primitive returns"
            )
            continue
        missing = nullish_inputs(parsed["typescript"], name)
        cases, exhaustive = candidates.generate(a, modules, missing, max_cases)
        model = solver.check(*modules, name)
        witness = model.pop("candidate", None)
        if witness is not None:
            witness = [
                Value(missing[i][0]) if value.kind == "null" and missing[i] else value
                for i, value in enumerate(witness)
            ]
            if witness not in cases:
                cases.insert(0, witness)  # One solver candidate may exceed the sampling budget.
            model["candidate"] = [asdict(value) for value in witness]
        report.update(
            model=model,
            exhaustive_inputs=exhaustive,
            cases=[[asdict(value) for value in case] for case in cases],
        )
        executions = runner.execute(sources, a, cases)
        report["executions"] = [asdict(execution) for execution in executions]
        if (
            len(executions) != 2
            or any(run.status != "ok" for run in executions)
            or any(len(run.observations) != len(cases) for run in executions)
        ):
            report["reason"] = (
                "Both original sources must compile, execute and complete the protocol"
            )
            continue
        for index, (ts, rust) in enumerate(
            zip(executions[0].observations, executions[1].observations, strict=True)
        ):
            if ts != rust:
                report["differences"].append(
                    {
                        "case": index,
                        "input": report["cases"][index],
                        "typescript": asdict(ts),
                        "rust": asdict(rust),
                        "origin": "solver" if witness == cases[index] else "boundary_generator",
                    }
                )
        if report["differences"]:
            report["status"] = "confirmed_difference"
        elif model["status"] == "counterexample_candidate":
            report["reason"] = "Model predicts a difference but native execution did not confirm it"
        elif exhaustive:
            report["status"] = "verified_finite_domain"
        elif model["status"] == "unsat":
            report["status"] = "verified_model"
        else:
            report["status"] = "tested_agreement"
    statuses = [function["status"] for function in result["functions"]]
    if "confirmed_difference" in statuses:
        result["status"] = "confirmed_difference"
    elif "inconclusive" in statuses:
        result["status"] = "inconclusive"
    elif "tested_agreement" in statuses:
        result["status"] = "tested_agreement"
    else:
        result["status"] = (
            "verified_finite_domain"
            if set(statuses) == {"verified_finite_domain"}
            else "verified_model"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    from .runners import IsolatedRunner
    from .syntax import build_syntax_context

    parser = argparse.ArgumentParser(description="Check original TypeScript/Rust function behavior")
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--function")
    parser.add_argument("--assume-option-mapping", action="store_true")
    parser.add_argument(
        "--backend",
        choices=["docker", "local"],
        default="docker",
        help="local runs trusted sources with host permissions",
    )
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--solver-timeout-ms", type=int, default=5000)
    parser.add_argument("--max-cases", type=int, default=128)
    parser.add_argument("--format", choices=["console", "json"], default="console")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.json_output and args.json_output.resolve() in {
            args.left.resolve(),
            args.right.resolve(),
        }:
            raise InputError("JSON output must not overwrite an input file")
        context = VerificationContext(
            ParityContext(build_syntax_context()),
            FunctionRunner(IsolatedRunner(args.backend, args.timeout)),
            ModelChecker(args.solver_timeout_ms),
            CandidateBank(),
        )
        report = verify_functions(
            context,
            args.left,
            args.right,
            function_name=args.function,
            assume_option_mapping=args.assume_option_mapping,
            max_cases=args.max_cases,
        )
        output = json.dumps(report, indent=2) + "\n"
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(output, encoding="utf-8")
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for function in report["functions"]:
                query = function.get("model", {}).get("smt2")
                if query:
                    path = args.output_dir / f"{function['name']}.smt2"
                    if path.resolve() in {args.left.resolve(), args.right.resolve()}:
                        raise InputError("Solver output must not overwrite an input file")
                    path.write_text(query, encoding="utf-8")
        if args.format == "json":
            print(output, end="")
        else:
            print(f"crosslang-verifier: {report['status'].upper()} (AST: {report['ast_status']})")
            for function in report["functions"]:
                print(
                    f"  {function['name']}: {function['status']} "
                    f"({len(function.get('cases', []))} executed inputs)"
                )
                for difference in function["differences"][:3]:
                    print("    Counterexample: " + json.dumps(difference))
                if function.get("reason"):
                    print("    " + function["reason"])
            if report.get("reason"):
                print(report["reason"])
            print(report["scope"])
        return {"confirmed_difference": 1, "verified_finite_domain": 0, "verified_model": 0}.get(
            report["status"], 2
        )
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        error = {
            "mode": "functional_verification",
            "status": "inconclusive",
            "error": str(exc),
            "equivalence_claim": False,
        }
        if args.format == "json":
            print(json.dumps(error))
        else:
            print(f"crosslang-verifier: {exc}", file=sys.stderr)
        return 2
