import json

import pytest

from crosslang_verifier.cli import main as cli_main
from crosslang_verifier.syntax import build_syntax_context, compare_files, parse_file


def main(arguments):
    return cli_main(["--raw", *arguments])


def nodes(tree):
    yield tree
    for child in tree.get("children", []):
        yield from nodes(child)


@pytest.fixture
def files(tmp_path):
    left, right = tmp_path / "old.ts", tmp_path / "new.rs"
    left.write_text('export function run(x: string) { return x || "fallback"; }')
    right.write_text('pub fn run(x: Option<&str>) -> &str { x.unwrap_or("fallback") }')
    return left, right


def test_two_files_dump_complete_trees_without_execution(files, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Basic syntax dumps must not construct behavioral services")

    monkeypatch.setattr("crosslang_verifier.cli.build_context", forbidden)
    monkeypatch.setattr("crosslang_verifier.cli.IsolatedRunner", forbidden)
    assert main([str(p) for p in files]) == 1
    output = capsys.readouterr().out
    assert "LEFT AST" in output and "RIGHT AST" in output and "AST DIFF" in output
    assert "binary_expression" in output and "call_expression" in output
    assert "does not prove behavioral equivalence" in output


def test_json_retains_operators_leaf_values_and_spans(files, capsys):
    assert main([*(str(p) for p in files), "--format", "json"]) == 1
    result = json.loads(capsys.readouterr().out)
    operator = next(n for n in nodes(result["left"]["ast"]) if n["type"] == "||")
    assert operator["text"] == "||" and operator["field"] == "operator"
    assert operator["named"] is False and operator["start"][0] == 1
    assert result["left"]["language"] == "typescript"
    assert result["right"]["language"] == "rust"
    assert len(result["left"]["sha256"]) == 64
    assert result["equivalence_claim"] is False


def test_saved_tree_files_and_combined_json(files, tmp_path, capsys):
    output, combined = tmp_path / "trees", tmp_path / "combined.json"
    assert (
        main(
            [
                *(str(p) for p in files),
                "--output-dir",
                str(output),
                "--json-output",
                str(combined),
                "--format",
                "json",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert json.loads(combined.read_text()) == payload
    for side in ("left", "right"):
        assert json.loads((output / f"{side}.ast.json").read_text()) == payload[side]
    assert (output / "diff.txt").read_text().strip() == payload["comparison"]["diff"]


def test_whitespace_and_positions_do_not_change_syntax(tmp_path):
    left, right = tmp_path / "a.ts", tmp_path / "b.ts"
    left.write_text("const x=1;")
    right.write_text("\n const   x = 1;\n")
    result = compare_files(build_syntax_context(), left, right)
    assert result["left"]["sha256"] != result["right"]["sha256"]
    assert result["comparison"] == {"same_syntax": True, "diff": ""}


@pytest.mark.parametrize(
    "first,second",
    [
        ("let x = 1;", "const x = 1;"),
        ("const x = a || b;", "const x = a ?? b;"),
        ("const x = 1;", "const x = 2;"),
        ("const x = 1;", "const y = 1;"),
    ],
)
def test_syntax_differences_are_not_erased(tmp_path, first, second):
    left, right = tmp_path / "a.ts", tmp_path / "b.ts"
    left.write_text(first)
    right.write_text(second)
    assert compare_files(build_syntax_context(), left, right)["comparison"]["same_syntax"] is False


def test_same_files_have_zero_exit_code(files, capsys):
    assert main([str(files[0]), str(files[0])]) == 0
    assert "Same syntax tree." in capsys.readouterr().out


def test_general_programs_need_no_fixture_assumptions(tmp_path):
    path = tmp_path / "module.ts"
    path.write_text('import fs from "node:fs";\nfunction add(a, b) { return a+b; }\nadd(1,2);')
    tree = parse_file(build_syntax_context(), path)
    assert any(n["type"] == "import_statement" for n in nodes(tree["ast"]))


def test_tsx_and_utf8_leaf_text(tmp_path):
    path = tmp_path / "ui.tsx"
    path.write_text("const element = <span>é</span>;", encoding="utf-8")
    tree = parse_file(build_syntax_context(), path)
    assert tree["language"] == "tsx"
    assert any(n.get("text") == "é" for n in nodes(tree["ast"]))


@pytest.mark.parametrize(
    "suffix,source", [(".ts", "const x = ;"), (".rs", "fn broken( {"), (".py", "x = 1")]
)
def test_bad_or_unsupported_input_is_not_a_success(tmp_path, capsys, suffix, source):
    path = tmp_path / f"bad{suffix}"
    path.write_text(source)
    assert main([str(path), str(path), "--format", "json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "ast" and "error" in payload


def test_missing_file_and_bad_encoding(files, tmp_path, capsys):
    assert main([str(tmp_path / "missing.ts"), str(files[1])]) == 2
    assert "missing.ts" in capsys.readouterr().err
    bad = tmp_path / "bytes.ts"
    bad.write_bytes(b"\xff")
    assert main([str(bad), str(files[1])]) == 2


def test_output_cannot_overwrite_input(files, capsys):
    before = files[0].read_bytes()
    assert main([*(str(p) for p in files), "--json-output", str(files[0])]) == 2
    assert files[0].read_bytes() == before
    assert "overwrite an input" in capsys.readouterr().err


def test_help_leads_with_two_files(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert "left right" in output
    assert "Parse two files" in output
