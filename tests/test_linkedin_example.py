import importlib.util
import json
import subprocess
import sys

import pytest
from conftest import ROOT

from crosslang_verifier.engine import analyze
from crosslang_verifier.models import load_pair


@pytest.fixture
def demo():
    spec = importlib.util.spec_from_file_location(
        "linkedin_demo", ROOT / "tools" / "check_linkedin_example.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_static_predictions_do_not_pass_the_demo(demo, context):
    reports = [
        analyze(context, load_pair(demo.EXAMPLE / name))
        for name in ("regression.json", "control.json")
    ]
    assert reports[0].status == "static_warning"
    assert reports[1].status == "static_checked"
    assert not all(demo.verify_reports(*reports).values())


@pytest.mark.parametrize("timeout", ["0", "nan"])
def test_invalid_runner_configuration_is_inconclusive(demo, capsys, timeout):
    assert demo.main(["--timeout", timeout, "--format", "json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "inconclusive"
    assert "Invalid runner configuration" in payload["error"]


def test_module_entry_point():
    result = subprocess.run(
        [sys.executable, "-m", "crosslang_verifier", "--version"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "0.1.0"


@pytest.mark.integration
def test_checked_demo_script_with_real_implementations(integration_context, tmp_path):
    output = tmp_path / "demo.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "check_linkedin_example.py"),
            "--backend",
            integration_context.runner.backend,
            "--timeout",
            str(integration_context.runner.timeout),
            "--json-output",
            str(output),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=4 * integration_context.runner.timeout + 30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload == json.loads(output.read_text())
    assert payload["status"] == "passed"
    assert len(payload["checks"]) == 4 and all(payload["checks"].values())
    assert payload["reports"][0]["differences"][0]["input"] == {"kind": "string", "value": ""}
    assert payload["equivalence_claim"] is False
