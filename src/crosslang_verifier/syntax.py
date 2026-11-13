"""Two files in, syntax trees and a syntax diff out. No source execution."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_rust
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from . import __version__
from .models import InputError

GRAMMARS = {".ts": "typescript", ".tsx": "tsx", ".rs": "rust"}


@dataclass
class SyntaxContext:
    parsers: dict[str, Parser]


def build_syntax_context() -> SyntaxContext:
    return SyntaxContext(
        {
            "typescript": Parser(Language(tree_sitter_typescript.language_typescript())),
            "tsx": Parser(Language(tree_sitter_typescript.language_tsx())),
            "rust": Parser(Language(tree_sitter_rust.language())),
        }
    )


def export_node(node: Node, field: str | None = None) -> dict:
    result = {
        "type": node.type,
        "named": node.is_named,
        "start": [node.start_point.row + 1, node.start_point.column + 1],
        "end": [node.end_point.row + 1, node.end_point.column + 1],
    }
    if field:
        result["field"] = field
    if node.child_count:
        result["children"] = [
            export_node(child, node.field_name_for_child(i))
            for i, child in enumerate(node.children)
        ]
    else:
        result["text"] = node.text.decode("utf-8")
    return result


def parse_file(context: SyntaxContext, path: Path) -> dict:
    parsers = context.parsers
    language = GRAMMARS.get(path.suffix.lower())
    if language is None:
        raise InputError(f"Unsupported file extension {path.suffix!r}; use .ts, .tsx or .rs")
    source = path.read_bytes()
    source.decode("utf-8")
    root = parsers[language].parse(source).root_node
    if root.has_error:
        # Tree-sitter normally recovers from invalid input; do not hide that recovery.
        pending = [root]
        while pending:
            node = pending.pop()
            if node.type == "ERROR" or node.is_missing:
                point = node.start_point
                raise InputError(f"{path}:{point.row + 1}:{point.column + 1}: syntax error")
            pending.extend(reversed(node.children))
        raise InputError(f"{path}: syntax error")
    return {
        "path": str(path),
        "language": language,
        "sha256": hashlib.sha256(source).hexdigest(),
        "ast": export_node(root),
    }


def tree_lines(node: dict, depth: int = 0) -> list[str]:
    label = f"{node['field']}: " if "field" in node else ""
    label += node["type"]
    if "text" in node and node["text"] != node["type"]:
        label += " " + json.dumps(node["text"], ensure_ascii=True)
    lines = ["  " * depth + label]
    for child in node.get("children", []):
        lines.extend(tree_lines(child, depth + 1))
    return lines


def compare_files(context: SyntaxContext, left: Path, right: Path) -> dict:
    left_tree, right_tree = parse_file(context, left), parse_file(context, right)
    left_lines, right_lines = tree_lines(left_tree["ast"]), tree_lines(right_tree["ast"])
    diff = "\n".join(
        difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=str(left),
            tofile=str(right),
            lineterm="",
        )
    )
    return {
        "schema_version": "1.0",
        "mode": "ast",
        "left": left_tree,
        "right": right_tree,
        "comparison": {"same_syntax": left_lines == right_lines, "diff": diff},
        "scope": "Tree-sitter syntax only. Positions are ignored by the diff; "
        "tokens, names, literals and comments are preserved. "
        "Different languages normally produce different trees.",
        "equivalence_claim": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse two files, dump their ASTs, and show a syntax diff.",
        epilog="Supported: .ts, .tsx, .rs. Advanced behavioral checks: compare / suite.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--format", choices=["console", "json"], default="console")
    parser.add_argument(
        "--json-output", type=Path, help="Save both trees and the diff in one JSON file"
    )
    parser.add_argument(
        "--output-dir", type=Path, help="Save left.ast.json, right.ast.json and diff.txt"
    )
    args = parser.parse_args(argv)
    try:
        if args.json_output and args.json_output.resolve() in {
            args.left.resolve(),
            args.right.resolve(),
        }:
            raise InputError("JSON output must not overwrite an input file")
        payload = compare_files(build_syntax_context(), args.left, args.right)
        output = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(output, encoding="utf-8")
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for side in ("left", "right"):
                (args.output_dir / f"{side}.ast.json").write_text(
                    json.dumps(payload[side], indent=2) + "\n",
                    encoding="utf-8",
                )
            (args.output_dir / "diff.txt").write_text(
                payload["comparison"]["diff"] + "\n", encoding="utf-8"
            )
        if args.format == "json":
            print(output, end="")
        else:
            for side in ("left", "right"):
                print(f"{side.upper()} AST: {payload[side]['path']}")
                print("\n".join(tree_lines(payload[side]["ast"])))
                print()
            print("AST DIFF")
            print(payload["comparison"]["diff"] or "Same syntax tree.")
            print("\nSyntax comparison only; this does not prove behavioral equivalence.")
        return 0 if payload["comparison"]["same_syntax"] else 1
    except (InputError, OSError, UnicodeError, RecursionError) as exc:
        message = (
            "Syntax tree is too deeply nested" if isinstance(exc, RecursionError) else str(exc)
        )
        if args.format == "json":
            print(json.dumps({"schema_version": "1.0", "mode": "ast", "error": message}))
        else:
            print(f"crosslang-verifier: {message}", file=sys.stderr)
        return 2
