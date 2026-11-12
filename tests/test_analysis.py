import json
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import MANIFESTS

from obscuretone_semantic_diff.engine import analyze
from obscuretone_semantic_diff.models import Execution, InputError, Value, digest, load_pair
from obscuretone_semantic_diff.rules import RuleRegistry


def changed(source, content):
    return replace(source, content=content, sha256=digest(content))


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: f"{p.parent.parent.name}/{p.parent.name}")
def test_corpus_static_contract(context, path):
    pair = load_pair(path)
    report = analyze(context, pair)
    assert report.status == (
        "static_warning" if pair.expected == "regression" else "static_checked"
    )
    assert report.resolution["evidence"]["compiler_verified"] is False
    assert report.differences == []
    assert report.equivalence_claim is False
    assert all(ir.span.start_line == 2 for ir in report.ir)
    data = json.loads(path.read_text())
    if pair.expected == "regression":
        assert Value(**data["witness"]) in report.candidates


def test_corpus_count():
    assert len(MANIFESTS) == 40
    assert sum(load_pair(p).expected == "regression" for p in MANIFESTS) == 20
    assert sum(load_pair(p).expected == "control" for p in MANIFESTS) == 20


@pytest.mark.parametrize(
    "key,value",
    [
        ("rust_method", "custom::Option::unwrap_or"),
        ("typescript_type", "any"),
        ("rust_type", "Result<f64,E>"),
        ("domain", "object"),
        ("domain", []),
        ("input_mapping", "invented"),
        ("note", ""),
        ("allowed_inputs", []),
        ("allowed_inputs", [True]),
        ("allowed_inputs", [{"kind": "boolean", "value": True}]),
    ],
)
def test_resolution_blocks_rules(context, pair, key, value):
    class ForbiddenRules:
        def assess(self, *args):
            pytest.fail("Semantic rules ran without resolution")

    context.rules = ForbiddenRules()
    pair = replace(pair, assumptions={**pair.assumptions, key: value})
    report = analyze(context, pair, execute=True)
    assert report.status == "unsupported"
    assert report.executions == []


def test_missing_assumptions(context, pair):
    assert analyze(context, replace(pair, assumptions={})).status == "unsupported"


def test_filter_needs_method_resolution(context):
    pair = load_pair(next(p for p in MANIFESTS if p.parent.name == "04-filter-number"))
    assumptions = {k: v for k, v in pair.assumptions.items() if k != "rust_filter_method"}
    assert analyze(context, replace(pair, assumptions=assumptions)).status == "unsupported"


@pytest.mark.parametrize(
    "language,content",
    [
        ("typescript", "export function evaluate(x: number) { return x || ; }"),
        ("typescript", "export function evaluate(x: number): number { const y=1; return x || 2; }"),
        ("typescript", "export function evaluate(x: number): number { x || 2; }"),
        ("typescript", "export default function evaluate(x: number): number { return x || 2; }"),
        ("typescript", "export async function evaluate(x: number): number { return x || 2; }"),
        ("typescript", "export function evaluate<T>(x: number): number { return x || 2; }"),
        ("typescript", "export function evaluate(x: number): number { return x && 2; }"),
        ("typescript", "export function evaluate(x: number): number { return other || 2; }"),
        ("typescript", "export function evaluate(x: number, y: number): number { return x || 2; }"),
        ("typescript", "export function evaluate(x): number { return x || 2; }"),
        ("typescript", "export function evaluate(x: number): number { return x || (1+2); }"),
        ("typescript", "export function evaluate(x: string): string { return x || 'single'; }"),
        ("typescript", "function evaluate(x: number): number { return x || 2; }"),
        ("typescript", "export function evaluate(x: number): boolean { return x || 2; }"),
        ("typescript", "export function other(x: number): number { return x || 2; }"),
        ("rust", "pub fn evaluate(x: Option<f64>) -> f64 { x.unwrap_or(1.0); }"),
        ("rust", "pub fn evaluate(x: Option<f64>) -> f64 { x.unwrap_or_else(|| 1.0) }"),
        (
            "rust",
            "pub fn evaluate(x: Option<f64>) -> f64 { x.filter(|v| *v > 0.0).unwrap_or(1.0) }",
        ),
        ("rust", "struct Option; pub fn evaluate(x: Option<f64>) -> f64 { x.unwrap_or(1.0) }"),
        ("rust", "mod m { pub fn evaluate(x: Option<f64>) -> f64 { x.unwrap_or(1.0) } }"),
        ("rust", "pub fn evaluate(x: Option<f64>) -> f64 { x.unwrap_or() }"),
    ],
)
def test_unsupported_syntax_does_not_guess(context, pair, language, content):
    pair = replace(pair, **{language: changed(getattr(pair, language), content)})
    report = analyze(context, pair, execute=True)
    assert report.status == "unsupported", report.to_dict()
    assert report.assessments == report.executions == []


def test_empty_rule_registry(context, pair):
    context.rules = RuleRegistry([])
    assert analyze(context, pair).status == "unsupported"


def test_custom_rule_extension(context, pair):
    from obscuretone_semantic_diff.models import RuleAssessment

    class Rule:
        def assess(self, ts, rust, resolution, candidates):
            assert resolution.evidence["source_hashes_validated"]
            return RuleAssessment("custom", "custom check", False)

    context.rules = RuleRegistry([Rule()])
    report = analyze(context, pair)
    assert report.assessments[0].rule_id == "custom"


@pytest.mark.parametrize(
    "runs",
    [
        [],
        [Execution("rust", "ok")],
        [Execution("typescript", "error"), Execution("rust", "ok")],
        [Execution("typescript", "ok"), Execution("rust", "ok")],
        [Execution("typescript", "ok"), Execution("typescript", "ok")],
    ],
)
def test_execution_failure_is_inconclusive(context, pair, runs):
    class Runner:
        def execute(self, *args):
            return runs

    context.runner = Runner()
    report = analyze(context, pair, execute=True)
    assert report.status == "inconclusive"
    assert report.differences == []


def test_source_hash_requires_assumption_review(tmp_path):
    source = tmp_path / "source.ts"
    source.write_text("changed")
    manifest = {"schema_version": 1, "typescript": {"path": "source.ts", "sha256": "old"}}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(InputError, match="hash mismatch"):
        load_pair(path)


@pytest.mark.parametrize("content", ["{}", "null", "[]", "{", '{"schema_version":2}'])
def test_bad_manifest(tmp_path, content):
    path = tmp_path / "manifest.json"
    path.write_text(content)
    with pytest.raises(InputError):
        load_pair(path)


def test_manifest_limits(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(" " * 131_073)
    with pytest.raises(InputError, match="128 KiB"):
        load_pair(path)


def test_missing_manifest():
    with pytest.raises(InputError):
        load_pair(Path("/nonexistent/obscuretone-manifest.json"))
