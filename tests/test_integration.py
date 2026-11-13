import json
from dataclasses import replace

import pytest
from conftest import MANIFESTS, ROOT
from test_analysis import changed

from crosslang_verifier.cli import main
from crosslang_verifier.engine import analyze
from crosslang_verifier.models import Value, load_pair
from crosslang_verifier.runners import IsolatedRunner

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_actual_corpus(integration_context, path):
    pair = load_pair(path)
    report = analyze(integration_context, pair, execute=True)
    status = "confirmed_difference" if pair.expected == "regression" else "no_difference_observed"
    assert report.status == status, report.to_dict()
    assert len(report.executions) == 2
    assert all(run.status == "ok" for run in report.executions)
    if pair.expected == "regression":
        witness = Value(**json.loads(path.read_text())["witness"])
        assert witness in [Value(**d["input"]) for d in report.differences]
    if integration_context.runner.backend == "docker":
        for execution in report.executions:
            command = execution.commands[0]
            assert "--network=none" in command and "--read-only" in command
            assert "--user=65534:65534" in command and "--cap-drop=ALL" in command


def test_compiler_error_is_inconclusive(integration_context, pair):
    # Same normalized expression, but function is private and cannot be called by the harness.
    broken = replace(pair, rust=changed(pair.rust, pair.rust.content.replace("pub fn", "fn")))
    report = analyze(integration_context, broken, execute=True)
    assert report.status == "inconclusive"
    rust = next(run for run in report.executions if run.language == "rust")
    assert rust.status == "error" and "private" in rust.stderr
    assert report.differences == []


def test_runtime_error_is_not_a_difference(integration_context, pair):
    # Direct runner test intentionally bypasses the conservative normalizer.
    ts, rust = (
        integration_context.adapters[lang].normalize(getattr(pair, lang))
        for lang in ("typescript", "rust")
    )
    resolution = integration_context.resolver.resolve(pair, ts, rust)
    source = 'export function evaluate(x: number): number { throw new Error("fixture failure"); }'
    broken = replace(pair, typescript=changed(pair.typescript, source))
    runs = integration_context.runner.execute(broken, resolution, [Value("number", "0")])
    assert runs[0].status == "error" and "fixture failure" in runs[0].stderr


def test_cli_confirmed_exit_and_report(integration_context, tmp_path, capsys):
    output = tmp_path / "report.json"
    code = main(
        [
            "compare",
            str(ROOT / "fixtures/regressions/01-zero-count/manifest.json"),
            "--execute",
            "--backend",
            integration_context.runner.backend,
            "--timeout",
            str(integration_context.runner.timeout),
            "--format",
            "json",
            "--json-output",
            str(output),
        ]
    )
    assert code == 1
    data = json.loads(capsys.readouterr().out)
    assert data == json.loads(output.read_text())
    assert data["status"] == "confirmed_difference"


def test_local_trusted_node_runner(pair, context, tmp_path):
    from crosslang_verifier.runners import write_project

    ts = context.adapters["typescript"].normalize(pair.typescript)
    rust = context.adapters["rust"].normalize(pair.rust)
    resolution = context.resolver.resolve(pair, ts, rust)
    write_project(tmp_path, pair, resolution, [Value("number", "0")])
    result = IsolatedRunner("local")._run("typescript", tmp_path, 1, "number")
    assert result.status == "ok", result
    assert result.observations == [Value("number", "10")]
