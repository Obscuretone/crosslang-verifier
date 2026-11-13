"""Invoke original multi-argument functions with visibility-only bridges."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from .models import Execution, Value
from .runners import NODE_HARNESS, RUST_HELPERS, IsolatedRunner, rust_input

DOMAINS = {"f64": "number", "bool": "boolean", "string": "string"}


def rust_type(type_: object) -> str:
    if isinstance(type_, dict):
        return f"std::option::Option<{rust_type(type_['option'])}>"
    return {"f64": "f64", "bool": "bool", "string": "&str"}[type_]


def write_function_project(
    root: Path, sources: dict[str, str], function: dict, cases: list[list[Value]]
) -> None:
    alias = "__crosslang_probe"
    while any(alias in text for text in sources.values()):
        alias += "_"
    name, types = function["name"], function["parameters"]
    (root / "implementation.mts").write_text(
        sources["typescript"] + f"\nexport {{ {name} as {alias} }};\n", encoding="utf-8"
    )
    (root / "implementation.rs").write_text(sources["rust"], encoding="utf-8")
    (root / "candidates.json").write_text(
        json.dumps([[asdict(value) for value in case] for case in cases]), encoding="utf-8"
    )
    (root / "harness.mjs").write_text(
        NODE_HARNESS.replace("FUNCTION", alias).replace(
            "evaluate(decode(value))", "evaluate(...value.map(decode))"
        ),
        encoding="utf-8",
    )
    parameters = ", ".join(f"p{i}: {rust_type(t)}" for i, t in enumerate(types))
    arguments = ", ".join(f"p{i}" for i in range(len(types)))
    domain = DOMAINS[function["returns"]]
    bridge = (
        'mod implementation { include!("implementation.rs");\n'
        f"pub fn {alias}({parameters}) -> String {{ "
        f"super::encode_{domain}({name}({arguments})) }}\n}}\n"
    )
    calls = []
    for index, case in enumerate(cases):
        literals = []
        for value, type_ in zip(case, types, strict=True):
            literal = rust_input(value)
            literals.append(literal if isinstance(type_, dict) else literal[5:-1])
        calls.append(
            f'println!("{{{{\\"id\\":{index},\\"output\\":{{}}}}}}", '
            f"implementation::{alias}({', '.join(literals)}));"
        )
    (root / "main.rs").write_text(
        RUST_HELPERS + bridge + "fn main() {\n" + "\n".join(calls) + "\n}\n", encoding="utf-8"
    )
    (root / "Cargo.toml").write_text(
        '[package]\nname="ot_probe"\nversion="0.0.0"\nedition="2021"\n'
        '[workspace]\n[[bin]]\nname="ot_probe"\npath="main.rs"\n',
        encoding="utf-8",
    )
    (root / "Cargo.lock").write_text(
        'version = 4\n[[package]]\nname = "ot_probe"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    root.chmod(0o755)
    for path in root.iterdir():
        path.chmod(0o644)


class FunctionRunner:
    def __init__(self, runner: IsolatedRunner):
        self.runner = runner

    def execute(
        self, sources: dict[str, str], function: dict, cases: list[list[Value]]
    ) -> list[Execution]:
        runner = self.runner
        with tempfile.TemporaryDirectory(prefix="crosslang-functions-") as directory:
            root = Path(directory)
            write_function_project(root, sources, function, cases)
            return [
                runner.run_project(language, root, len(cases), DOMAINS[function["returns"]])
                for language in ("typescript", "rust")
            ]
