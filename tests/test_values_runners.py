import json
import os
import sys

import pytest

from obscuretone_semantic_diff.models import InputError, Value
from obscuretone_semantic_diff.runners import (
    IsolatedRunner,
    bounded_process,
    decode_observations,
    rust_input,
    rust_string,
)


@pytest.mark.parametrize(
    "value,falsy",
    [
        (Value("null"), True),
        (Value("undefined"), True),
        (Value("number", "0"), True),
        (Value("number", "-0"), True),
        (Value("number", "NaN"), True),
        (Value("boolean", False), True),
        (Value("string", ""), True),
        (Value("string", "0"), False),
        (Value("string", "false"), False),
        (Value("string", " "), False),
        (Value("number", "Infinity"), False),
        (Value("number", "-Infinity"), False),
        (Value("number", "-1"), False),
    ],
)
def test_truthiness(value, falsy):
    assert value.falsy is falsy


@pytest.mark.parametrize(
    "kind,value",
    [
        ("number", float("nan")),
        ("number", "nan"),
        ("number", "1e999"),
        ("number", "not-a-number"),
        ("boolean", 0),
        ("object", {}),
        ("null", "null"),
        ("string", "\ud800"),
        ("number", "-0.0"),
    ],
)
def test_wire_rejects_lossy_or_invalid(kind, value):
    with pytest.raises(InputError):
        Value(kind, value)


def test_number_normalization_is_binary64_and_sign_sensitive():
    assert Value("number", "1e0") == Value("number", "1.0")
    assert Value("number", "0") != Value("number", "-0")
    assert Value("number", "NaN") == Value("number", "NaN")


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "not json",
        "{}",
        '{"id":1,"output":{"kind":"number","value":"1"}}',
        '{"id":true,"output":{"kind":"number","value":"1"}}',
        '{"id":0,"output":{"kind":"boolean","value":false}}',
        '{"id":0,"output":{"kind":"number","value":"nan"}}',
    ],
)
def test_protocol_failure(stdout):
    with pytest.raises(InputError):
        decode_observations(stdout, 1, "number")


def test_protocol_success():
    line = json.dumps({"id": 0, "output": {"kind": "number", "value": "1"}})
    assert decode_observations(line, 1, "number") == [Value("number", "1")]


def test_rust_escaping_and_inputs():
    assert rust_string('\x00\t"\\音') == '"\\u{0}\\u{9}\\"\\\\音"'
    assert rust_input(Value("undefined")) == "None"
    assert rust_input(Value("number", "NaN")) == "Some(f64::NAN)"
    assert rust_input(Value("boolean", False)) == "Some(false)"
    assert rust_input(Value("string", "")) == 'Some("")'


def test_subprocess_timeout(tmp_path):
    code, out, err, error = bounded_process(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        tmp_path,
        0.1,
        4096,
        dict(os.environ),
    )
    assert code != 0 and "timed out" in error


def test_subprocess_output_bound(tmp_path):
    code, out, err, error = bounded_process(
        [sys.executable, "-c", "import sys; sys.stdout.write('x'*1000000)"],
        tmp_path,
        5,
        1024,
        dict(os.environ),
    )
    assert len(out) + len(err) <= 1024
    assert "output bytes" in error


def test_subprocess_captures_both_streams_and_exit(tmp_path):
    code, out, err, error = bounded_process(
        [
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr); sys.exit(7)",
        ],
        tmp_path,
        5,
        4096,
        dict(os.environ),
    )
    assert (code, out.strip(), err.strip(), error) == (7, "out", "err", None)


def test_missing_runtime_is_not_a_behavior_difference(context, pair, monkeypatch):
    from obscuretone_semantic_diff.engine import analyze

    monkeypatch.setattr("obscuretone_semantic_diff.runners.shutil.which", lambda _: None)
    report = analyze(context, pair, execute=True)
    assert report.status == "inconclusive"
    assert all(run.error for run in report.executions)


@pytest.mark.parametrize(
    "backend,timeout,limit", [("unknown", 1, 10), ("local", 0, 10), ("docker", 1, 0)]
)
def test_runner_configuration(backend, timeout, limit):
    with pytest.raises(ValueError):
        IsolatedRunner(backend, timeout, max_output=limit)
