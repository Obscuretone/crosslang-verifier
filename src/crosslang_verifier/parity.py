"""Normalize a conservative TypeScript/Rust subset to the same typed AST."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .models import InputError, Value
from .syntax import SyntaxContext, build_syntax_context, parse_file


def source(node: dict) -> str:
    if "text" in node:
        return node["text"]
    return "".join(
        source(child) for child in node.get("children", []) if "comment" not in child["type"]
    )


def named(node: dict) -> list[dict]:
    return [c for c in node.get("children", []) if c["named"] and "comment" not in c["type"]]


def part(node: dict, name: str) -> dict | None:
    return next((c for c in node.get("children", []) if c.get("field") == name), None)


@dataclass
class Binding:
    canonical: str
    type: object
    mutable: bool = False


@dataclass
class Normalizer:
    language: str
    assume_option_mapping: bool = False
    issues: list[dict] = field(default_factory=list)
    signatures: dict[str, dict] = field(default_factory=dict)
    scopes: list[dict[str, Binding]] = field(default_factory=list)
    return_type: object = "unit"
    next_local: int = 0
    loop_depth: int = 0

    def issue(self, node: dict | None, reason: str) -> dict:
        self.issues.append(
            {
                "reason": reason,
                "syntax": node["type"] if node else None,
                "start": node.get("start") if node else None,
            }
        )
        return {"kind": "unresolved", "source": source(node) if node else "", "reason": reason}

    def type_of(self, node: dict | None) -> object:
        if node is None:
            return self.issue(node, "An explicit primitive type is required")
        text = source(node).removeprefix(":")
        primitives = {
            "number": "f64",
            "boolean": "bool",
            "string": "string",
            "void": "unit",
            "f64": "f64",
            "bool": "bool",
            "&str": "string",
            "()": "unit",
        }
        if text in primitives:
            return primitives[text]
        if re.fullmatch(r"[iu](8|16|32|64|128|size)|f32", text):
            return text  # Integer/float-width differences must not be erased.
        if "|" in text:
            types = text.split("|")
            bases = [t for t in types if t not in {"null", "undefined"}]
            if len(bases) == 1 and bases[0] in primitives and len(bases) < len(types):
                if self.assume_option_mapping:
                    return {"option": primitives[bases[0]]}
                return self.issue(
                    node, "Nullish/Option correspondence needs --assume-option-mapping"
                )
        match = re.fullmatch(r"(?:std::option::)?Option<(.+)>", text)
        if match and match[1] in primitives:
            if self.assume_option_mapping:
                return {"option": primitives[match[1]]}
            return self.issue(node, "Standard Option identity needs --assume-option-mapping")
        return self.issue(node, f"Unsupported type: {text}")

    def lookup(self, name: str) -> Binding | None:
        return next((scope[name] for scope in reversed(self.scopes) if name in scope), None)

    def module(self, root: dict) -> dict:
        functions, other = [], []
        for item in named(root):
            public = item["type"] == "export_statement"
            if public and any(c["type"] == "default" for c in item.get("children", [])):
                other.append(
                    self.issue(item, "Default exports need an explicit API correspondence")
                )
                continue
            node = part(item, "declaration") if public else item
            if node is None or node["type"] not in {"function_declaration", "function_item"}:
                other.append(
                    self.issue(item, "Only standalone function declarations are supported")
                )
                continue
            if part(node, "type_parameters") or any(
                c["type"] in {"async", "const", "unsafe", "extern", "function_modifiers"}
                for c in node.get("children", [])
            ):
                other.append(
                    self.issue(node, "Generic/async/const/unsafe/extern functions are unsupported")
                )
                continue
            name = source(part(node, "name"))
            if name in self.signatures:
                other.append(self.issue(node, f"Duplicate function: {name}"))
                continue
            parameters = named(part(node, "parameters"))
            types = [self.type_of(part(p, "type")) for p in parameters]
            result_node = part(node, "return_type")
            result = self.type_of(result_node) if result_node else "unit"
            public = public or any(
                source(c) == "pub" for c in named(node) if c["type"] == "visibility_modifier"
            )
            if any(source(c) != "pub" for c in named(node) if c["type"] == "visibility_modifier"):
                other.append(self.issue(node, "Restricted Rust visibility needs module context"))
                continue
            signature = {"name": name, "public": public, "parameters": types, "returns": result}
            self.signatures[name] = signature
            functions.append((node, parameters, signature))
        normalized = []
        for node, parameters, signature in functions:
            self.scopes, self.next_local, self.return_type = [{}], 0, signature["returns"]
            for index, param in enumerate(parameters):
                pattern = part(param, "pattern")
                if (
                    param["type"] not in {"required_parameter", "parameter"}
                    or pattern is None
                    or pattern["type"] != "identifier"
                    or part(param, "value") is not None
                    or any(
                        c["type"]
                        not in {
                            "identifier",
                            "type_annotation",
                            "primitive_type",
                            "reference_type",
                            "generic_type",
                            "mutable_specifier",
                        }
                        for c in named(param)
                        if c.get("field") not in {"pattern", "type"}
                    )
                ):
                    self.issue(param, "Only simple typed parameters without defaults are supported")
                    continue
                if source(pattern) in self.scopes[0]:
                    self.issue(param, "Duplicate parameter binding")
                mutable = self.language == "typescript" or any(
                    c["type"] == "mutable_specifier" for c in named(param)
                )
                self.scopes[0][source(pattern)] = Binding(
                    f"p{index}", signature["parameters"][index], mutable
                )
            body = part(node, "body")
            statements = (
                self.block(body, tail=self.language == "rust")
                if body
                else [self.issue(node, "Function body is missing")]
            )
            if self.return_type != "unit" and not self.terminates(statements):
                self.issue(node, "Return paths are incomplete or the final value is discarded")
            normalized.append({"kind": "function", **signature, "body": statements})
        return {
            "kind": "module",
            "functions": sorted(normalized, key=lambda f: f["name"]),
            "unresolved_items": other,
        }

    @staticmethod
    def terminates(statements: list[dict]) -> bool:
        if not statements:
            return False
        last = statements[-1]
        if last["kind"] == "return":
            return True
        if last["kind"] == "block":
            return Normalizer.terminates(last["body"])
        return (
            last["kind"] == "if"
            and Normalizer.terminates(last["then"])
            and Normalizer.terminates(last["else"])
        )

    @staticmethod
    def infer_integer(value: dict, expected: object) -> dict:
        if (
            value.get("type") == "integer_literal"
            and isinstance(expected, str)
            and re.fullmatch(r"[iu](8|16|32|64|128|size)", expected)
        ):
            if expected[1:] != "size":
                bits = int(expected[1:])
                limit = 2 ** (bits if expected.startswith("u") else bits - 1)
                if not 0 <= int(value["value"]) < limit:
                    return value
            return {**value, "type": expected}
        return value

    def block(self, node: dict, tail: bool = False) -> list[dict]:
        self.scopes.append({})
        statements = []
        children = named(node)
        for index, child in enumerate(children):
            statements.extend(self.statement(child, tail=tail and index == len(children) - 1))
        self.scopes.pop()
        return statements

    def condition(self, node: dict) -> dict:
        expr = self.expression(node)
        if expr.get("type") == "bool":
            return expr
        if (
            self.language == "typescript"
            and isinstance(expr.get("type"), str)
            and expr["type"] in {"f64", "string"}
        ):
            return {"kind": "truthy", "value": expr, "type": "bool"}
        self.issue(node, "Condition does not resolve to a supported boolean/primitive")
        return {"kind": "unresolved_condition", "value": expr}

    def statement(self, node: dict, tail: bool = False) -> list[dict]:
        kind = node["type"]
        if kind in {"statement_block", "block"}:
            return [{"kind": "block", "body": self.block(node, tail)}]
        if kind == "expression_statement":
            child = named(node)[0]
            # A semicolon discards a Rust value. It cannot turn into a return.
            retains_value = tail and not any(c["type"] == ";" for c in node.get("children", []))
            return (
                self.statement(child, retains_value)
                if child["type"]
                in {
                    "return_expression",
                    "if_expression",
                    "while_expression",
                    "assignment_expression",
                    "block",
                }
                else [{"kind": "evaluate", "value": self.expression(child)}]
            )
        if kind in {"return_statement", "return_expression"}:
            values = named(node)
            value = self.expression(values[0]) if values else {"kind": "unit", "type": "unit"}
            value = self.infer_integer(value, self.return_type)
            self.check_type(node, value.get("type"), self.return_type)
            return [{"kind": "return", "value": value}]
        if kind in {"lexical_declaration", "let_declaration"}:
            declarations = named(node) if kind == "lexical_declaration" else [node]
            declarations = [
                d for d in declarations if d["type"] in {"variable_declarator", "let_declaration"}
            ]
            result = []
            for declaration in declarations:
                pattern = part(declaration, "name") or part(declaration, "pattern")
                value_node = part(declaration, "value")
                if pattern is None or pattern["type"] != "identifier" or value_node is None:
                    result.append(
                        self.issue(declaration, "Binding requires a simple name and initializer")
                    )
                    continue
                value = self.expression(value_node)
                annotation = part(declaration, "type")
                value_type = self.type_of(annotation) if annotation else value.get("type")
                value = self.infer_integer(value, value_type)
                self.check_type(declaration, value.get("type"), value_type)
                mutable = (
                    source(part(node, "kind")) == "let"
                    if kind == "lexical_declaration"
                    else any(c["type"] == "mutable_specifier" for c in named(node))
                )
                binding = Binding(f"v{self.next_local}", value_type, mutable)
                self.next_local += 1
                if self.language == "typescript" and source(pattern) in self.scopes[-1]:
                    self.issue(declaration, "Duplicate binding in the same TypeScript scope")
                self.scopes[-1][source(pattern)] = binding
                result.append(
                    {"kind": "bind", "id": binding.canonical, "type": value_type, "value": value}
                )
            return result
        if kind in {"if_statement", "if_expression"}:
            condition = self.condition(part(node, "condition"))
            consequence = part(node, "consequence")
            then = (
                self.block(consequence, tail)
                if consequence["type"] in {"block", "statement_block"}
                else self.statement(consequence, tail)
            )
            alternative = part(node, "alternative")
            otherwise = []
            if alternative:
                branch = (
                    named(alternative)[0] if alternative["type"] == "else_clause" else alternative
                )
                otherwise = (
                    self.block(branch, tail)
                    if branch["type"] in {"block", "statement_block"}
                    else self.statement(branch, tail)
                )
            if tail and self.return_type != "unit" and not alternative:
                self.issue(node, "Value-returning conditional needs both branches")
            return [{"kind": "if", "condition": condition, "then": then, "else": otherwise}]
        if kind in {"while_statement", "while_expression"}:
            condition = self.condition(part(node, "condition"))
            self.loop_depth += 1
            body_node = part(node, "body")
            body = (
                self.block(body_node)
                if body_node["type"] in {"block", "statement_block"}
                else self.statement(body_node)
            )
            self.loop_depth -= 1
            return [{"kind": "while", "condition": condition, "body": body}]
        if kind == "assignment_expression":
            target = part(node, "left")
            binding = (
                self.lookup(source(target)) if target and target["type"] == "identifier" else None
            )
            if binding is None or not binding.mutable:
                return [self.issue(node, "Assignment target is unresolved or immutable")]
            value = self.expression(part(node, "right"))
            value = self.infer_integer(value, binding.type)
            self.check_type(node, value.get("type"), binding.type)
            return [{"kind": "assign", "target": binding.canonical, "value": value}]
        if kind in {
            "break_statement",
            "break_expression",
            "continue_statement",
            "continue_expression",
        }:
            if named(node) or not self.loop_depth:
                return [self.issue(node, "Labeled/value-carrying loop control is unsupported")]
            return [{"kind": "break" if kind.startswith("break") else "continue"}]
        value = self.expression(node)
        if tail:
            value = self.infer_integer(value, self.return_type)
            self.check_type(node, value.get("type"), self.return_type)
            return [{"kind": "return", "value": value}]
        return [{"kind": "evaluate", "value": value}]

    def check_type(self, node: dict, actual: object, expected: object) -> None:
        if actual != expected:
            self.issue(node, f"Type does not resolve consistently: {actual!r} versus {expected!r}")

    def expression(self, node: dict) -> dict:
        kind, raw = node["type"], source(node)
        if kind == "parenthesized_expression":
            return self.expression(named(node)[0])
        if kind == "identifier":
            binding = self.lookup(raw)
            if binding is None:
                return self.issue(node, f"Unresolved identifier: {raw}")
            return {"kind": "load", "id": binding.canonical, "type": binding.type}
        if kind in {"number", "float_literal", "integer_literal"}:
            if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", raw):
                return self.issue(node, "Only unsuffixed decimal numbers are supported")
            if kind == "integer_literal":
                return {"kind": "literal", "type": "integer_literal", "value": str(int(raw))}
            try:
                value = Value("number", raw)
            except InputError:
                return self.issue(node, "Number is outside the supported finite literal domain")
            return {"kind": "literal", "type": "f64", "value": value.value}
        if kind in {"true", "false", "boolean_literal"}:
            return {"kind": "literal", "type": "bool", "value": raw == "true"}
        if kind in {"string", "string_literal"}:
            try:
                text = raw[1:-1] if re.fullmatch(r"'[^'\\\r\n]*'", raw) else json.loads(raw)
                Value("string", text)
                return {"kind": "literal", "type": "string", "value": text}
            except (ValueError, TypeError):
                return self.issue(node, "Unsupported string escape/literal")
        if kind == "unary_expression":
            children = named(node)
            if len(children) != 1:
                return self.issue(node, "Unsupported unary expression")
            value = self.expression(children[0])
            operator = next((source(c) for c in node["children"] if not c["named"]), "")
            if operator == "-" and value.get("type") == "f64":
                if value.get("kind") == "literal":
                    number = Value(
                        "number", "-0" if float(value["value"]) == 0 else "-" + value["value"]
                    )
                    return {"kind": "literal", "type": "f64", "value": number.value}
                return {"kind": "unary", "operator": "negate", "value": value, "type": "f64"}
            if operator == "!" and value.get("type") == "bool":
                return {"kind": "unary", "operator": "not", "value": value, "type": "bool"}
            return self.issue(node, "Unary operator/type is unresolved")
        if kind == "binary_expression":
            left, right = self.expression(part(node, "left")), self.expression(part(node, "right"))
            operator_node = part(node, "operator")
            operator = (
                source(operator_node)
                if operator_node
                else next((source(c) for c in node["children"] if not c["named"]), "")
            )
            if self.language == "typescript" and operator in {"||", "??"}:
                if operator == "||" and left.get("type") == right.get("type") == "bool":
                    return {
                        "kind": "binary",
                        "operator": "||",
                        "left": left,
                        "right": right,
                        "type": "bool",
                    }
                base = left.get("type")
                if isinstance(base, dict) and "option" in base:
                    base = base["option"]
                if (
                    isinstance(base, str)
                    and base in {"f64", "bool", "string"}
                    and right.get("type") == base
                ):
                    return {
                        "kind": "fallback",
                        "trigger": "falsy" if operator == "||" else "missing",
                        "value": left,
                        "default": right,
                        "type": base,
                    }
                return self.issue(node, "Fallback operand types are unresolved")
            left = self.infer_integer(left, right.get("type"))
            right = self.infer_integer(right, left.get("type"))
            types = left.get("type"), right.get("type")
            numeric = isinstance(types[0], str) and bool(
                re.fullmatch(r"f64|[iu](8|16|32|64|128|size)", types[0])
            )
            if types[0] != types[1] or not (numeric or types[0] in ("bool", "string")):
                return self.issue(node, "Binary operand types are unresolved or unsupported")
            if operator in {"+", "-", "*", "/", "%", "<", "<=", ">", ">="}:
                if not numeric:
                    return self.issue(
                        node, "Numeric operator requires resolved f64/number operands"
                    )
                result_type = "bool" if operator in {"<", "<=", ">", ">="} else types[0]
            elif operator in {"===", "!==", "==", "!="}:
                # Local primitive resolution avoids coercive/overloaded custom-object rules.
                operator = "eq" if operator in {"===", "=="} else "ne"
                result_type = "bool"
            elif operator in {"&&", "||"} and types[0] == "bool":
                result_type = "bool"
            else:
                return self.issue(node, "Unsupported binary operator")
            return {
                "kind": "binary",
                "operator": operator,
                "left": left,
                "right": right,
                "type": result_type,
            }
        if kind == "call_expression":
            function, arguments = part(node, "function"), named(part(node, "arguments"))
            if any(c.get("field") not in {"function", "arguments"} for c in named(node)):
                return self.issue(node, "Generic/optional call metadata is unsupported")
            # TypeScript calls use a function field too; known local declarations are resolved.
            if (
                function
                and function["type"] == "identifier"
                and source(function) in self.signatures
            ):
                if self.lookup(source(function)) is not None:
                    return self.issue(node, "Local function call is shadowed by a value binding")
                signature = self.signatures[source(function)]
                values = [self.expression(arg) for arg in arguments]
                if len(values) == len(signature["parameters"]):
                    values = [
                        self.infer_integer(v, t)
                        for v, t in zip(values, signature["parameters"], strict=True)
                    ]
                if [v.get("type") for v in values] != signature["parameters"]:
                    return self.issue(
                        node, "Call arguments do not match the resolved local function"
                    )
                return {
                    "kind": "call",
                    "function": signature["name"],
                    "arguments": values,
                    "type": signature["returns"],
                }
            if self.language == "rust" and function and function["type"] == "field_expression":
                return self.option_fallback(node, function, arguments)
            return self.issue(node, "External/dynamic call is not resolved")
        return self.issue(node, f"Unsupported expression: {kind}")

    def option_fallback(self, node: dict, function: dict, arguments: list[dict]) -> dict:
        if not self.assume_option_mapping:
            return self.issue(
                node, "Method identity is unresolved; use --assume-option-mapping only if justified"
            )
        if source(part(function, "field")) != "unwrap_or" or len(arguments) != 1:
            return self.issue(node, "Only the assumed standard Option::unwrap_or call is supported")
        receiver = part(function, "value")
        trigger = "missing"
        if receiver["type"] == "call_expression":
            filtered = part(receiver, "function")
            if filtered and filtered["type"] == "field_expression":
                original = part(filtered, "value")
                value = self.expression(original)
                inner = (
                    value.get("type", {}).get("option")
                    if isinstance(value.get("type"), dict)
                    else None
                )
                patterns = {
                    "f64": ".filter(|v|*v!=0.0&&!v.is_nan())",
                    "bool": ".filter(|v|*v)",
                    "string": ".filter(|v|!v.is_empty())",
                }
                if source(receiver) != source(original) + patterns.get(inner, "<unsupported>"):
                    return self.issue(node, "Filter closure is not a supported truthiness filter")
                trigger, receiver = "falsy", original
        value = self.expression(receiver)
        inner = value.get("type", {}).get("option") if isinstance(value.get("type"), dict) else None
        default = self.expression(arguments[0])
        if inner not in {"f64", "bool", "string"} or default.get("type") != inner:
            return self.issue(node, "Option fallback receiver/default types are unresolved")
        if default.get("kind") != "literal":
            return self.issue(
                node, "Only literal Option defaults are supported; eager/lazy effects unresolved"
            )
        return {
            "kind": "fallback",
            "trigger": trigger,
            "value": value,
            "default": default,
            "type": inner,
        }


@dataclass
class ParityContext:
    syntax: SyntaxContext


def compare_parity(
    context: ParityContext, left: Path, right: Path, assume_option_mapping: bool = False
) -> dict:
    syntax = context.syntax
    raw = [parse_file(syntax, path) for path in (left, right)]
    normalized = []
    issues = []
    for side, parsed in zip(("left", "right"), raw, strict=True):
        language = "typescript" if parsed["language"] == "tsx" else parsed["language"]
        normalizer = Normalizer(language, assume_option_mapping)
        tree = normalizer.module(parsed["ast"])
        normalized.append({**parsed, "shared_ast": tree})
        issues.extend({"side": side, **issue} for issue in normalizer.issues)
    shared = [json.dumps(n["shared_ast"], indent=2, sort_keys=True) for n in normalized]
    same = normalized[0]["shared_ast"] == normalized[1]["shared_ast"]
    status = "unresolved" if issues else "parity" if same else "different"
    return {
        "schema_version": "1.0",
        "mode": "cross_language_ast_parity",
        "status": status,
        "left": normalized[0],
        "right": normalized[1],
        "issues": issues,
        "comparison": {
            "same_shared_ast": None if issues else same,
            "diff": "\n".join(
                difflib.unified_diff(
                    shared[0].splitlines(),
                    shared[1].splitlines(),
                    fromfile=str(left),
                    tofile=str(right),
                    lineterm="",
                )
            ),
        },
        "resolution": "Local primitive declarations, lexical bindings and function signatures; "
        "not full compiler verification.",
        "assumptions": (
            [
                "Rust Option methods are standard library methods; "
                "TypeScript null/undefined map to None and present primitives to Some."
            ]
            if assume_option_mapping
            else []
        ),
        "equivalence_claim": False,
        "scope": "Normalized typed AST parity for the supported subset; no source execution "
        "or proof of full behavioral equivalence.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare TypeScript/Rust through a shared typed AST."
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--format", choices=["console", "json"], default="console")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--raw", action="store_true", help="Dump language-specific parser trees instead"
    )
    parser.add_argument(
        "--assume-option-mapping",
        action="store_true",
        help="Assert standard Option methods and a nullish-to-None input mapping",
    )
    args = parser.parse_args(argv)
    if args.raw:
        from .syntax import main as raw_main

        return raw_main([arg for arg in (sys.argv[1:] if argv is None else argv) if arg != "--raw"])
    try:
        if args.json_output and args.json_output.resolve() in {
            args.left.resolve(),
            args.right.resolve(),
        }:
            raise InputError("JSON output must not overwrite an input file")
        result = compare_parity(
            ParityContext(build_syntax_context()), args.left, args.right, args.assume_option_mapping
        )
        output = json.dumps(result, indent=2) + "\n"
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(output, encoding="utf-8")
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for side in ("left", "right"):
                for suffix, data in (
                    ("ast", result[side]["shared_ast"]),
                    ("syntax", result[side]["ast"]),
                ):
                    (args.output_dir / f"{side}.{suffix}.json").write_text(
                        json.dumps(data, indent=2) + "\n", encoding="utf-8"
                    )
            (args.output_dir / "diff.txt").write_text(
                result["comparison"]["diff"] + "\n", encoding="utf-8"
            )
        if args.format == "json":
            print(output, end="")
        else:
            print(f"crosslang-verifier: {result['status'].upper()}")
            for side in ("left", "right"):
                print(f"\n{side.upper()} SHARED AST")
                print(json.dumps(result[side]["shared_ast"], indent=2))
            if result["comparison"]["diff"]:
                print("\nSHARED AST DIFF\n" + result["comparison"]["diff"])
            for issue in result["issues"]:
                print(f"Unresolved ({issue['side']}): {issue['reason']}")
            print("\nSupported-subset AST parity only; not a proof of behavioral equivalence.")
        return {"parity": 0, "different": 1, "unresolved": 2}[result["status"]]
    except (InputError, OSError, UnicodeError, RecursionError) as exc:
        error = {
            "mode": "cross_language_ast_parity",
            "status": "unresolved",
            "error": str(exc),
            "equivalence_claim": False,
        }
        if args.format == "json":
            print(json.dumps(error))
        else:
            print(f"crosslang-verifier: {exc}", file=sys.stderr)
        return 2
