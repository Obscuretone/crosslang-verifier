import json

import pytest

from crosslang_verifier.parity import ParityContext, compare_parity, main
from crosslang_verifier.syntax import build_syntax_context


def compare(tmp_path, ts, rust, assume=False):
    left, right = tmp_path / "source.ts", tmp_path / "source.rs"
    left.write_text(ts, encoding="utf-8")
    right.write_text(rust, encoding="utf-8")
    return compare_parity(ParityContext(build_syntax_context()), left, right, assume)


def number_pair(ts_body, rust_body):
    return (
        f"export function f(x: number): number {{ {ts_body} }}",
        f"pub fn f(value: f64) -> f64 {{ {rust_body} }}",
    )


EQUIVALENT = [
    number_pair("return x;", "value"),
    number_pair("return 1;", "1.0"),
    number_pair("return x + 2;", "value + 2.0"),
    number_pair("return (x + 2) * 3;", "(value + 2.0) * 3.0"),
    number_pair("return -x;", "-value"),
    number_pair("return -0;", "-0.0"),
    number_pair("const a = x + 1; return a;", "let renamed = value + 1.0; renamed"),
    number_pair(
        "let a: number = x; a = a + 1; return a;",
        "let mut renamed: f64 = value; renamed = renamed + 1.0; renamed",
    ),
    number_pair(
        "if (x > 0) { return x; } else { return -x; }", "if value > 0.0 { value } else { -value }"
    ),
    number_pair("if (x > 0) return x; else return 0;", "if value > 0.0 { value } else { 0.0 }"),
    number_pair(
        "let n = x; while (n < 10) { n = n + 1; } return n;",
        "let mut n = value; while n < 10.0 { n = n + 1.0; } n",
    ),
    number_pair("const a = x; { const a = 2; } return a;", "let a = value; { let a = 2.0; } a"),
    (
        "export function f(a: boolean, b: boolean): boolean { return a && b; }",
        "pub fn f(left: bool, right: bool) -> bool { left && right }",
    ),
    (
        "export function f(a: boolean, b: boolean): boolean { return a || b; }",
        "pub fn f(left: bool, right: bool) -> bool { left || right }",
    ),
    (
        "export function f(a: boolean): boolean { return !a; }",
        "pub fn f(left: bool) -> bool { !left }",
    ),
    (
        "export function f(a: number): boolean { return a === 1; }",
        "pub fn f(left: f64) -> bool { left == 1.0 }",
    ),
    (
        "export function f(a: string, b: string): boolean { return a !== b; }",
        "pub fn f(left: &str, right: &str) -> bool { left != right }",
    ),
    (
        "export function f(a: string): string { return 'hello'; }",
        'pub fn f(left: &str) -> &str { "hello" }',
    ),
    (
        "function helper(a: number): number { return a * 2; } "
        "export function f(a: number): number { return helper(a); }",
        "pub fn f(x: f64) -> f64 { helper(x) } fn helper(x: f64) -> f64 { x * 2.0 }",
    ),
    ("export function f(): void {}", "pub fn f() {}"),
]


@pytest.mark.parametrize("ts,rust", EQUIVALENT)
def test_cross_language_shared_ast_parity(tmp_path, ts, rust):
    result = compare(tmp_path, ts, rust)
    assert result["status"] == "parity", result["issues"]
    assert result["left"]["shared_ast"] == result["right"]["shared_ast"]
    assert result["left"]["ast"] != result["right"]["ast"]
    assert not result["issues"]
    assert result["equivalence_claim"] is False


DIFFERENT = [
    number_pair("return x + 1;", "value - 1.0"),
    number_pair("return 1;", "2.0"),
    number_pair("return x;", "-value"),
    number_pair("return x / 2;", "2.0 / value"),
    number_pair("if (x > 0) return x; else return 0;", "if value >= 0.0 { value } else { 0.0 }"),
    ("export function f(x: number): number { return x; }", "pub fn f(x: i32) -> i32 { x }"),
    ("export function f(x: number): number { return x; }", "fn f(x: f64) -> f64 { x }"),
    ("export function f(x: number): number { return x; }", "pub fn renamed(x: f64) -> f64 { x }"),
    (
        "export function f(a: boolean, b: boolean): boolean { return a && b; }",
        "pub fn f(a: bool, b: bool) -> bool { a || b }",
    ),
    (
        "export function f(a: string): string { return a; }",
        'pub fn f(a: &str) -> &str { "replacement" }',
    ),
]


@pytest.mark.parametrize("ts,rust", DIFFERENT)
def test_real_normalized_differences_are_preserved(tmp_path, ts, rust):
    result = compare(tmp_path, ts, rust)
    assert result["status"] == "different", result["issues"]
    assert result["comparison"]["same_shared_ast"] is False
    assert result["comparison"]["diff"]


@pytest.mark.parametrize(
    "ts,rust",
    [
        (
            "export function f(x: unknown): unknown { return x; }",
            "pub fn f(x: Mystery) -> Mystery { x }",
        ),
        (
            "export function f(x: number): number { return Math.abs(x); }",
            "pub fn f(x: f64) -> f64 { x.abs() }",
        ),
        (
            "export function f(x: number): number { return other(x); }",
            "pub fn f(x: f64) -> f64 { other(x) }",
        ),
        (
            "export async function f(x: number): number { return x; }",
            "pub async fn f(x: f64) -> f64 { x }",
        ),
        (
            "export function f<T>(x: number): number { return x; }",
            "pub fn f<T>(x: f64) -> f64 { x }",
        ),
        (
            "import x from 'elsewhere'; export function f(): number { return 1; }",
            "pub fn f() -> f64 { 1.0 }",
        ),
        ("export function f(x: number): number { return x; }", "pub fn f(x: f64) -> f64 { x; }"),
        (
            "export function f(x: number): number { const a = x; a = 2; return a; }",
            "pub fn f(x: f64) -> f64 { x }",
        ),
        (
            "export function f(x: number): number { return x; }",
            "pub unsafe fn f(x: f64) -> f64 { x }",
        ),
        (
            "export function f(x: number): number { return x; }",
            "pub(crate) fn f(x: f64) -> f64 { x }",
        ),
        (
            "export default function f(x: number): number { return x; }",
            "pub fn f(x: f64) -> f64 { x }",
        ),
        (
            "export function f(x: number): number { return [x][0]; }",
            "pub fn f(x: f64) -> f64 { [x][0] }",
        ),
    ],
)
def test_unresolved_never_reports_parity(tmp_path, ts, rust):
    result = compare(tmp_path, ts, rust)
    assert result["status"] == "unresolved"
    assert result["issues"]


def option_pair(operator="??", filter_receiver=False):
    receiver = "error.filter(|v| !v.is_empty())" if filter_receiver else "error"
    return (
        "export function f(error: string | null | undefined): string { "
        f'return error {operator} "Unknown error"; }}',
        "pub fn f(error: std::option::Option<&str>) -> &str { "
        f'{receiver}.unwrap_or("Unknown error") }}',
    )


def test_standard_option_assumption_is_required(tmp_path):
    result = compare(tmp_path, *option_pair())
    assert result["status"] == "unresolved"
    assert result["assumptions"] == []


@pytest.mark.parametrize(
    "op,filtered,status",
    [
        ("??", False, "parity"),
        ("||", True, "parity"),
        ("||", False, "different"),
        ("??", True, "different"),
    ],
)
def test_fallback_trigger_parity_with_explicit_mapping(tmp_path, op, filtered, status):
    result = compare(tmp_path, *option_pair(op, filtered), assume=True)
    assert result["status"] == status, result["issues"]
    assert len(result["assumptions"]) == 1


def test_identical_unsupported_trees_are_still_unresolved(tmp_path):
    code = "export class Unhandled {}"
    left, right = tmp_path / "a.ts", tmp_path / "b.ts"
    left.write_text(code)
    right.write_text(code)
    result = compare_parity(ParityContext(build_syntax_context()), left, right)
    assert result["comparison"]["same_shared_ast"] is None
    assert result["left"]["shared_ast"] == result["right"]["shared_ast"]
    assert result["status"] == "unresolved"


def test_cli_saves_shared_and_original_asts(tmp_path, capsys):
    ts, rust = EQUIVALENT[2]
    left, right = tmp_path / "a.ts", tmp_path / "b.rs"
    left.write_text(ts)
    right.write_text(rust)
    output = tmp_path / "asts"
    assert main([str(left), str(right), "--output-dir", str(output), "--format", "json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "parity"
    assert json.loads((output / "left.ast.json").read_text()) == result["left"]["shared_ast"]
    assert json.loads((output / "left.syntax.json").read_text()) == result["left"]["ast"]
    assert (output / "left.ast.json").read_bytes() == (output / "right.ast.json").read_bytes()


def test_cli_missing_file_does_not_claim_parity(tmp_path, capsys):
    assert (
        main([str(tmp_path / "missing.ts"), str(tmp_path / "missing.rs"), "--format", "json"]) == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "unresolved"


def test_primary_command_uses_shared_trees(tmp_path, capsys):
    from crosslang_verifier.cli import main as cli_main

    ts, rust = EQUIVALENT[0]
    left, right = tmp_path / "a.ts", tmp_path / "b.rs"
    left.write_text(ts)
    right.write_text(rust)
    assert cli_main([str(left), str(right), "--format", "json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "cross_language_ast_parity"
    assert result["status"] == "parity"


@pytest.mark.parametrize(
    "ts,rust",
    [
        ("export function f(x: number = 1): number { return x; }", "pub fn f(x: f64) -> f64 { x }"),
        (
            "export function f(x: number): number { if (x > 0) return x; }",
            "pub fn f(x: f64) -> f64 { if x > 0.0 { x } }",
        ),
        (
            "export function f(): boolean { return undefined === undefined; }",
            "pub fn f() -> bool { true }",
        ),
        (
            "export function f(x: number): number { return 1e999; }",
            "pub fn f(x: f64) -> f64 { 1.0 }",
        ),
        (
            "export function f(x: string | null): boolean { "
            "if (x) return true; else return false; }",
            "pub fn f(x: std::option::Option<&str>) -> bool { true }",
        ),
    ],
)
def test_uncertain_or_invalid_constructs_do_not_crash_or_pass(tmp_path, ts, rust):
    assert compare(tmp_path, ts, rust)["status"] == "unresolved"


def test_single_statement_while_preserves_nested_condition(tmp_path):
    ts = (
        "export function f(flag: boolean, other: boolean, x: number): number { "
        "while (flag) if (other) return x; return 0; }"
    )
    good = (
        "pub fn f(flag: bool, other: bool, x: f64) -> f64 { "
        "while flag { if other { return x; } } 0.0 }"
    )
    bad = "pub fn f(flag: bool, other: bool, x: f64) -> f64 { while flag { other; return x; } 0.0 }"
    assert compare(tmp_path, ts, good)["status"] == "parity"
    assert compare(tmp_path, ts, bad)["status"] == "different"


def test_shadowed_local_function_is_not_resolved_as_the_original(tmp_path):
    ts = (
        "function helper(x: number): number { return x; } "
        "export function f(helper: number): number { return helper(1); }"
    )
    rust = "fn helper(x: f64) -> f64 { x } pub fn f(helper: f64) -> f64 { helper(1.0) }"
    result = compare(tmp_path, ts, rust)
    assert result["status"] == "unresolved"
    assert any("shadowed" in issue["reason"] for issue in result["issues"])


def test_large_rust_integer_literals_are_not_rounded_into_parity(tmp_path):
    left, right = tmp_path / "a.rs", tmp_path / "b.rs"
    left.write_text("pub fn f() -> i64 { 9007199254740992 }")
    right.write_text("pub fn f() -> i64 { 9007199254740993 }")
    result = compare_parity(ParityContext(build_syntax_context()), left, right)
    assert result["status"] == "different"


def test_out_of_range_integer_type_is_unresolved(tmp_path):
    left, right = tmp_path / "a.rs", tmp_path / "b.rs"
    for path in (left, right):
        path.write_text("pub fn f() -> u8 { 300 }")
    assert (
        compare_parity(ParityContext(build_syntax_context()), left, right)["status"] == "unresolved"
    )


def test_type_comments_do_not_change_parity(tmp_path):
    ts, rust = number_pair("return x;", "value")
    ts = ts.replace("number", "number /* a type comment */")
    assert compare(tmp_path, ts, rust)["status"] == "parity"


@pytest.mark.parametrize(
    "ts,rust,expected,code",
    [
        (*EQUIVALENT[0], "parity", 0),
        (*DIFFERENT[0], "different", 1),
        (
            "export function f(x: number): number { return Math.abs(x); }",
            "pub fn f(x: f64) -> f64 { x.abs() }",
            "unresolved",
            2,
        ),
    ],
)
def test_console_status_and_saved_report(tmp_path, capsys, ts, rust, expected, code):
    left, right = tmp_path / "a.ts", tmp_path / "b.rs"
    left.write_text(ts)
    right.write_text(rust)
    report = tmp_path / "nested" / "report.json"
    assert main([str(left), str(right), "--json-output", str(report)]) == code
    assert f"crosslang-verifier: {expected.upper()}" in capsys.readouterr().out
    assert json.loads(report.read_text())["status"] == expected


def test_parity_report_cannot_overwrite_input(tmp_path, capsys):
    left, right = tmp_path / "a.ts", tmp_path / "b.rs"
    ts, rust = EQUIVALENT[0]
    left.write_text(ts)
    right.write_text(rust)
    assert main([str(left), str(right), "--json-output", str(left)]) == 2
    assert left.read_text() == ts
    assert "overwrite an input" in capsys.readouterr().err
