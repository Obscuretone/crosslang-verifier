import json

from conftest import ROOT

from crosslang_verifier.cli import main

REGRESSION = ROOT / "fixtures/regressions/01-zero-count/manifest.json"


def test_console_static(capsys):
    assert main(["compare", str(REGRESSION)]) == 0
    output = capsys.readouterr().out
    assert "STATIC WARNING" in output and "CONFIRMED" not in output


def test_json_and_saved_report(tmp_path, capsys):
    output = tmp_path / "nested/report.json"
    assert main(["compare", str(REGRESSION), "--format", "json", "--json-output", str(output)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == json.loads(output.read_text())
    assert data["schema_version"] == "1.0" and not data["equivalence_claim"]


def test_static_suite(capsys):
    assert main(["suite", str(ROOT / "fixtures"), "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["static_warning"] == data["summary"]["static_checked"] == 20
    assert data["summary"]["expected_passed"] == 0
    assert all(e["passed"] is None for e in data["expectations"])


def test_empty_suite(tmp_path, capsys):
    assert main(["suite", str(tmp_path), "--format", "json"]) == 2
    assert "No fixture" in json.loads(capsys.readouterr().out)["error"]


def test_bad_manifest_json(tmp_path, capsys):
    path = tmp_path / "broken.json"
    path.write_text("{}")
    assert main(["compare", str(path), "--format", "json"]) == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_bad_manifest_console(tmp_path, capsys):
    assert main(["compare", str(tmp_path / "missing")]) == 2
    assert "crosslang-verifier" in capsys.readouterr().err


def test_invalid_timeout(capsys):
    assert main(["compare", str(REGRESSION), "--timeout", "0"]) == 2
    assert "Invalid runner" in capsys.readouterr().err
