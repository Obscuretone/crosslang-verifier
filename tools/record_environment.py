"""Record actual tool versions and image provenance, including missing tools."""

import argparse
import importlib.metadata
import json
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def capture(command: list[str]) -> dict:
    if not shutil.which(command[0]):
        return {"command": command, "available": False}
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        return {
            "command": command,
            "available": True,
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "error": str(exc)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["docker", "local"], default="docker")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    commands = [
        ["node", "--version"],
        ["cargo", "--version"],
        ["rustc", "--version"],
        ["git", "--version"],
        ["git", "rev-parse", "HEAD"],
    ]
    if args.backend == "docker":
        commands += [
            ["docker", "version", "--format", "{{.Server.Version}}"],
            [
                "docker",
                "image",
                "inspect",
                "node:22-bookworm-slim",
                "rust:1-slim-bookworm",
                "--format",
                "{{.RepoTags}} {{.RepoDigests}} {{.Architecture}}",
            ],
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--pull=never",
                "node:22-bookworm-slim",
                "node",
                "--version",
            ],
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--pull=never",
                "rust:1-slim-bookworm",
                "cargo",
                "--version",
            ],
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "--pull=never",
                "rust:1-slim-bookworm",
                "rustc",
                "--version",
            ],
        ]
    packages = [
        "crosslang-verifier",
        "tree-sitter",
        "tree-sitter-typescript",
        "tree-sitter-rust",
        "z3-solver",
        "pytest",
        "pytest-cov",
        "ruff",
        "build",
    ]
    payload = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "backend": args.backend,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in packages},
        "tools": [capture(command) for command in commands],
        "note": "Actual tool output; no benchmark or equivalence claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
