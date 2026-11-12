"""Execute original sources in isolated projects, never Python emulations.

Docker is the default security boundary. Local processes are for trusted inputs only.
"""

from __future__ import annotations

import json
import math
import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .models import Execution, InputError, Pair, Resolution, Value

NODE_HARNESS = r"""
import { readFileSync } from 'node:fs';
import { FUNCTION as evaluate } from './implementation.mts';
const decode = (v) => v.kind === 'undefined' ? undefined : v.kind === 'null' ? null :
    v.kind === 'number' ? Number(v.value) : v.value;
const encode = (v) => {
    if (typeof v === 'number') return {
        kind: 'number', value: Object.is(v, -0) ? '-0' : String(v)
    };
    if (typeof v === 'string') return { kind: 'string', value: v };
    if (typeof v === 'boolean') return { kind: 'boolean', value: v };
    throw new Error('Unsupported output type');
};
const cases = JSON.parse(readFileSync(new URL('./candidates.json', import.meta.url), 'utf8'));
for (const [id, value] of cases.entries()) {
    console.log(JSON.stringify({ id, output: encode(evaluate(decode(value))) }));
}
"""

RUST_HELPERS = r"""
fn json_quote(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""), '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"), '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 32 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"'); out
}
fn encode_number(v: f64) -> String {
    let value = if v.is_nan() { "NaN".to_owned() }
        else if v == f64::INFINITY { "Infinity".to_owned() }
        else if v == f64::NEG_INFINITY { "-Infinity".to_owned() }
        else if v == 0.0 && v.is_sign_negative() { "-0".to_owned() }
        else { v.to_string() };
    format!("{{\"kind\":\"number\",\"value\":{}}}", json_quote(&value))
}
fn encode_boolean(v: bool) -> String {
    format!("{{\"kind\":\"boolean\",\"value\":{}}}", v)
}
fn encode_string(v: &str) -> String {
    format!("{{\"kind\":\"string\",\"value\":{}}}", json_quote(v))
}
"""


def rust_string(value: str) -> str:
    # JSON escapes differ from Rust's unicode escape syntax.
    quoted = '"'
    for char in value:
        if char in {'"', "\\"}:
            quoted += "\\" + char
        elif ord(char) < 32 or ord(char) == 127:
            quoted += f"\\u{{{ord(char):x}}}"
        else:
            quoted += char
    return quoted + '"'


def rust_input(value: Value) -> str:
    if value.kind in {"null", "undefined"}:
        return "None"
    if value.kind == "number":
        literal = {
            "NaN": "f64::NAN",
            "Infinity": "f64::INFINITY",
            "-Infinity": "f64::NEG_INFINITY",
            "-0": "-0.0_f64",
        }.get(value.value, f"{value.value}_f64")
    elif value.kind == "boolean":
        literal = "true" if value.value else "false"
    else:
        literal = rust_string(value.value)
    return f"Some({literal})"


def write_project(root: Path, pair: Pair, resolution: Resolution, candidates: list[Value]) -> None:
    (root / "implementation.mts").write_text(pair.typescript.content, encoding="utf-8")
    (root / "implementation.rs").write_text(pair.rust.content, encoding="utf-8")
    (root / "candidates.json").write_text(
        json.dumps([asdict(v) for v in candidates]), encoding="utf-8"
    )
    (root / "harness.mjs").write_text(
        NODE_HARNESS.replace("FUNCTION", pair.typescript.function),
        encoding="utf-8",
    )
    (root / "Cargo.toml").write_text(
        '[package]\nname = "ot_probe"\nversion = "0.0.0"\nedition = "2021"\n'
        '[workspace]\n[[bin]]\nname = "ot_probe"\npath = "main.rs"\n',
        encoding="utf-8",
    )
    (root / "Cargo.lock").write_text(
        'version = 4\n[[package]]\nname = "ot_probe"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )
    calls = []
    for index, value in enumerate(candidates):
        calls.append(
            f'println!("{{{{\\"id\\":{index},\\"output\\":{{}}}}}}", '
            f"encode_{resolution.domain}(implementation::{pair.rust.function}({rust_input(value)})));"
        )
    harness = '#[path = "implementation.rs"]\nmod implementation;\n' + RUST_HELPERS
    harness += "\nfn main() {\n" + "\n".join(calls) + "\n}\n"
    (root / "main.rs").write_text(harness, encoding="utf-8")
    # Non-root containers need traversal permission through the bind mount root.
    root.chmod(0o755)
    for path in root.iterdir():
        path.chmod(0o644)


def bounded_process(
    command: list[str], cwd: Path, timeout: float, max_output: int, env: dict[str, str]
) -> tuple[int, str, str, str | None]:
    """Drain both pipes with hard byte/deadline bounds and kill the process group on failure."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    output: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    deadline, total, error = time.monotonic() + timeout, 0, None
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    error = f"Process timed out after {timeout:g}s"
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    block = os.read(key.fileobj.fileno(), 65536)
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    room = max(0, max_output - total)
                    output[key.data].extend(block[:room])
                    total += len(block)
                    if total > max_output:
                        error = f"Process exceeded {max_output} output bytes"
                        break
                if error:
                    break
        if error:
            os.killpg(process.pid, signal.SIGKILL)
        try:
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            error = f"Process timed out after {timeout:g}s"
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        process.stdout.close()
        process.stderr.close()
    return code, *(output[k].decode("utf-8", errors="replace") for k in ("stdout", "stderr")), error


def decode_observations(stdout: str, count: int, domain: str) -> list[Value]:
    lines = stdout.splitlines()
    if len(lines) != count:
        raise InputError("Runner protocol: wrong observation count")
    observations = []
    for index, line in enumerate(lines):
        try:
            data = json.loads(line)
            if type(data["id"]) is not int or data["id"] != index:
                raise InputError("Runner protocol: unexpected candidate identity")
            value = Value(**data["output"])
            if value.kind != domain:
                raise InputError("Runner protocol: output type differs from declared domain")
            observations.append(value)
        except (ValueError, TypeError, KeyError) as exc:
            raise InputError(f"Runner protocol: {exc}") from exc
    return observations


class IsolatedRunner:
    def __init__(
        self,
        backend: str = "docker",
        timeout: float = 30,
        node_image: str = "node:22-bookworm-slim",
        rust_image: str = "rust:1-slim-bookworm",
        max_output: int = 1_048_576,
    ) -> None:
        if (
            backend not in {"docker", "local"}
            or not math.isfinite(timeout)
            or timeout <= 0
            or max_output < 1
        ):
            raise ValueError("Invalid runner configuration")
        self.backend, self.timeout, self.max_output = backend, timeout, max_output
        self.images = {"typescript": node_image, "rust": rust_image}

    def execute(
        self, pair: Pair, resolution: Resolution, candidates: list[Value]
    ) -> list[Execution]:
        with tempfile.TemporaryDirectory(prefix="obscuretone-") as directory:
            root = Path(directory)
            write_project(root, pair, resolution, candidates)
            return [
                self._run(language, root, len(candidates), resolution.domain)
                for language in ("typescript", "rust")
            ]

    def _run(self, language: str, root: Path, count: int, domain: str) -> Execution:
        isolation = (
            "container: no network; read-only root and sources; unprivileged; bounded resources"
            if self.backend == "docker"
            else "trusted local process only: fresh directory, clean environment, "
            "timeout and output bounds"
        )
        result = Execution(language, "error", backend=self.backend, isolation=isolation)
        name = f"obscuretone-{uuid.uuid4().hex}"
        env = {
            k: v
            for k, v in os.environ.items()
            if k in {"PATH", "SYSTEMROOT", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"}
        }
        try:
            if self.backend == "docker":
                executable = shutil.which("docker")
                if executable is None:
                    raise OSError("Docker is unavailable; pull runner images before execution")
                base = [
                    executable,
                    "run",
                    "--rm",
                    "--name",
                    name,
                    "--pull=never",
                    "--network=none",
                    "--read-only",
                    "--user=65534:65534",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--pids-limit=64",
                    "--memory=512m",
                    "--cpus=1",
                    "--tmpfs=/tmp:rw,exec,nosuid,nodev,size=268435456",
                    "--mount",
                    f"type=bind,src={root},dst=/job,readonly",
                    "--workdir=/job",
                    "--env=HOME=/tmp",
                    "--env=CARGO_HOME=/tmp/cargo",
                    self.images[language],
                ]
                inner = (
                    ["node", "--experimental-strip-types", "harness.mjs"]
                    if language == "typescript"
                    else [
                        "cargo",
                        "run",
                        "--quiet",
                        "--offline",
                        "--locked",
                        "--target-dir",
                        "/tmp/target",
                    ]
                )
                commands = [[*base, *inner]]
            else:
                # No inherited credentials, NODE_OPTIONS, RUSTFLAGS, or parent Cargo configuration.
                env.update(
                    HOME=str(root),
                    CARGO_HOME=str(root / ".cargo"),
                    RUSTUP_HOME=os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup")),
                )
                binary = shutil.which("node" if language == "typescript" else "cargo")
                if binary is None:
                    raise OSError(f"{language} runtime unavailable on PATH")
                commands = (
                    [[binary, "--experimental-strip-types", "harness.mjs"]]
                    if language == "typescript"
                    else [
                        [binary, "build", "--quiet", "--offline", "--locked"],
                        [str(root / "target" / "debug" / "ot_probe")],
                    ]
                )
            for command in commands:
                result.commands.append(command)
                code, stdout, stderr, error = bounded_process(
                    command,
                    root,
                    self.timeout,
                    self.max_output,
                    env,
                )
                result.stdout, result.stderr = stdout, result.stderr + stderr
                if error or code != 0:
                    result.error = error or f"Process exited with status {code}"
                    return result
            result.observations = decode_observations(result.stdout, count, domain)
            result.status = "ok"
        except (OSError, InputError) as exc:
            result.error = str(exc)
        finally:
            if self.backend == "docker" and result.status != "ok" and shutil.which("docker"):
                # A timed-out Docker client can leave its container running.
                try:
                    subprocess.run(
                        ["docker", "rm", "--force", name],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    result.error = f"{result.error}; container cleanup failed: {exc}"
        return result
