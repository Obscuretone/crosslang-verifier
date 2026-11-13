"""Independent source pairs, solver adversaries and classification boundaries."""

import json
from dataclasses import dataclass

import pytest
from conftest import ROOT

from crosslang_verifier.cli import main
from crosslang_verifier.function_runner import FunctionRunner, write_function_project
from crosslang_verifier.modelcheck import ModelChecker
from crosslang_verifier.models import Execution, InputError, Value
from crosslang_verifier.parity import ParityContext, compare_parity
from crosslang_verifier.runners import IsolatedRunner
from crosslang_verifier.syntax import build_syntax_context
from crosslang_verifier.verification import CandidateBank, VerificationContext, verify_functions

CORPUS = ROOT / "examples/verification"
CASES = json.loads((CORPUS / "cases.json").read_text())


def parity(case):
    folder = CORPUS / case["id"]
    return compare_parity(
        ParityContext(build_syntax_context()),
        folder / "before.ts",
        folder / "after.rs",
        case["assume_option_mapping"],
    )


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["expected"] != "inconclusive"], ids=lambda c: c["id"]
)
def test_solver_on_independent_source_pairs(case):
    report = parity(case)
    result = ModelChecker().check(
        report["left"]["shared_ast"], report["right"]["shared_ast"], "check"
    )
    expected = (
        "counterexample_candidate"
        if case["expected"] == "confirmed_difference"
        else "unsupported"
        if case["expected"] == "tested_agreement"
        else "unsat"
    )
    assert result["status"] == expected, result
    if result["status"] == "counterexample_candidate":
        assert all(isinstance(value, Value) for value in result["candidate"])
    if result["status"] == "unsat":
        assert "check-sat" in result["smt2"]


@dataclass
class ConstantRunner:
    outputs: tuple[Value, Value] = (Value("boolean", True), Value("boolean", True))
    failure: bool = False

    def execute(self, sources, function, cases):
        return [
            Execution(
                language, "error" if self.failure else "ok", observations=[value] * len(cases)
            )
            for language, value in zip(("typescript", "rust"), self.outputs, strict=True)
        ]


def context(runner=None, solver=None):
    return VerificationContext(
        ParityContext(build_syntax_context()),
        runner or ConstantRunner(),
        solver or ModelChecker(),
        CandidateBank(),
    )


def verify(case_id, ctx=None, **kwargs):
    case = next(case for case in CASES if case["id"] == case_id)
    folder = CORPUS / case_id
    return verify_functions(
        ctx or context(),
        folder / "before.ts",
        folder / "after.rs",
        assume_option_mapping=case["assume_option_mapping"],
        **kwargs,
    )


def test_finite_domain_is_exhaustive():
    report = verify("finite-optional-boolean")
    function = report["functions"][0]
    assert report["status"] == "verified_finite_domain"
    assert function["exhaustive_inputs"]
    assert function["cases"] == [
        [{"kind": "boolean", "value": False}],
        [{"kind": "boolean", "value": True}],
        [{"kind": "null", "value": None}],
        [{"kind": "undefined", "value": None}],
    ]


def test_compilation_failure_defeats_unsat_model():
    report = verify("arithmetic", context(ConstantRunner(failure=True)))
    assert report["status"] == "inconclusive"
    assert report["functions"][0]["model"]["status"] == "unsat"


def test_native_difference_overrides_model():
    runner = ConstantRunner((Value("number", "1"), Value("number", "2")))
    report = verify("arithmetic", context(runner))
    assert report["status"] == "confirmed_difference"
    assert report["functions"][0]["differences"]


def test_unconfirmed_model_candidate_is_not_a_source_difference():
    assert verify("boolean-regression")["status"] == "inconclusive"
    # Even finite agreement must expose a conflict with the symbolic mapping.
    report = verify(
        "solver-branch", context(ConstantRunner((Value("number", "0"), Value("number", "0"))))
    )
    assert report["status"] == "inconclusive"
    assert "did not confirm" in report["functions"][0]["reason"]


def test_budget_cannot_be_called_exhaustive():
    report = verify("boolean-demorgan", max_cases=1)
    assert report["status"] == "verified_model"
    assert report["functions"][0]["exhaustive_inputs"] is False
    with pytest.raises(InputError, match="Case budget"):
        verify("boolean-demorgan", max_cases=0)


@pytest.mark.parametrize("case_id", ["type-mismatch", "unresolved-method"])
def test_resolution_and_signature_gates(case_id):
    report = verify(case_id)
    assert report["status"] == "inconclusive"
    assert not any(function.get("executions") for function in report["functions"])


def test_project_keeps_original_bodies_and_variadic_arguments(tmp_path):
    sources = {
        "typescript": "function check(a:boolean,b:boolean):boolean{return a&&b;}",
        "rust": "fn check(a:bool,b:bool)->bool{a&&b}",
    }
    function = {"name": "check", "parameters": ["bool", "bool"], "returns": "bool"}
    write_function_project(
        tmp_path, sources, function, [[Value("boolean", False), Value("boolean", True)]]
    )
    assert (tmp_path / "implementation.rs").read_text() == sources["rust"]
    assert (tmp_path / "implementation.mts").read_text().startswith(sources["typescript"])
    assert "evaluate(...value.map(decode))" in (tmp_path / "harness.mjs").read_text()
    assert "__crosslang_probe(false, true)" in (tmp_path / "main.rs").read_text()


def test_cli_missing_runtime_is_inconclusive(monkeypatch, capsys):
    monkeypatch.setenv("PATH", "")
    folder = CORPUS / "boolean-demorgan"
    assert (
        main(
            [
                str(folder / "before.ts"),
                str(folder / "after.rs"),
                "--verify",
                "--backend",
                "local",
                "--format",
                "json",
            ]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "inconclusive"
    assert report["functions"][0]["executions"][0]["status"] == "error"


def test_cli_protects_source(capsys):
    folder = CORPUS / "arithmetic"
    assert (
        main(
            [
                str(folder / "before.ts"),
                str(folder / "after.rs"),
                "--verify",
                "--json-output",
                str(folder / "before.ts"),
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert "overwrite" in json.loads(capsys.readouterr().out)["error"]


@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_actual_functional_experiments(request, case):
    ctx = context(
        FunctionRunner(
            IsolatedRunner(
                request.config.getoption("--integration-backend"),
                request.config.getoption("--integration-timeout"),
            )
        )
    )
    report = verify(case["id"], ctx)
    assert report["status"] == case["expected"], report
    if case["id"] == "boolean-demorgan":
        assert report["ast_status"] == "different"
        assert len(report["functions"][0]["cases"]) == 4
    if case["id"] == "solver-branch":
        assert any(
            difference["origin"] == "solver" for difference in report["functions"][0]["differences"]
        )
    if case["id"] == "compile-error":
        assert report["ast_status"] == "parity"
        assert report["functions"][0]["executions"][1]["status"] == "error"
        assert "unknown character escape" in report["functions"][0]["executions"][1]["stderr"]


def test_multi_function_port_models():
    root = ROOT / "examples/port"
    ast = compare_parity(
        ParityContext(build_syntax_context()), root / "before.ts", root / "after.rs"
    )
    assert ast["status"] == "different"
    for name in ("shipping", "eligible"):
        model = ModelChecker().check(ast["left"]["shared_ast"], ast["right"]["shared_ast"], name)
        assert model["status"] == "unsat", model


def test_outside_model_and_recursion_are_explicit(tmp_path):
    ts = tmp_path / "before.ts"
    rs = tmp_path / "after.rs"
    ts.write_text("export function check(x:boolean):boolean{return check(x);}")
    rs.write_text("pub fn check(x:bool)->bool{check(x)}")
    ast = compare_parity(ParityContext(build_syntax_context()), ts, rs)
    answer = ModelChecker().check(ast["left"]["shared_ast"], ast["right"]["shared_ast"], "check")
    assert answer["status"] == "unsupported" and "Recursion" in answer["reason"]
    with pytest.raises(ValueError, match="timeout"):
        ModelChecker(0)


@pytest.mark.integration
def test_multi_function_cli_and_actual_threshold_regression(request, tmp_path, capsys):
    root = ROOT / "examples/port"
    args = [
        str(root / "before.ts"),
        str(root / "after.rs"),
        "--verify",
        "--backend",
        request.config.getoption("--integration-backend"),
        "--timeout",
        "120",
        "--format",
        "json",
        "--json-output",
        str(tmp_path / "report.json"),
        "--output-dir",
        str(tmp_path / "queries"),
    ]
    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "verified_model"
    assert {function["name"] for function in report["functions"]} == {"eligible", "shipping"}
    assert (tmp_path / "queries/shipping.smt2").is_file()
    broken = tmp_path / "threshold.rs"
    broken.write_text((root / "after.rs").read_text().replace(">= 100.0", "> 100.0"))
    args[1] = str(broken)
    assert main(args) == 1
    report = json.loads(capsys.readouterr().out)
    shipping = next(function for function in report["functions"] if function["name"] == "shipping")
    assert any(difference["input"][0]["value"] == "100.0" for difference in shipping["differences"])
