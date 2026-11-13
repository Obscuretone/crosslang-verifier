"""Tree-sitter adapters. This module recognizes syntax; it does not resolve types."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

import tree_sitter_rust
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from .models import FallbackIR, InputError, Source, Span, Value


def walk(node: Node) -> Iterator[Node]:
    yield node
    for child in node.named_children:
        yield from walk(child)


def text(node: Node) -> str:
    return node.text.decode("utf-8")


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def children(node: Node) -> list[Node]:
    return [
        c for c in node.named_children if c.type not in {"comment", "line_comment", "block_comment"}
    ]


def literal(node: Node) -> Value:
    raw = text(node)
    if node.type in {"true", "false", "boolean_literal"}:
        return Value("boolean", raw == "true")
    if node.type in {"string", "string_literal"}:
        # A deliberately narrow, shared JSON-compatible string literal subset.
        try:
            return Value("string", json.loads(raw))
        except ValueError as exc:
            raise InputError("Use a double-quoted JSON-compatible fallback string") from exc
    if node.type in {"number", "integer_literal", "float_literal", "unary_expression"}:
        if re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", raw):
            return Value("number", "-0" if float(raw) == 0 and raw.startswith("-") else raw)
    raise InputError(f"Unsupported fallback literal: {raw}")


class TreeSitterAdapter:
    def __init__(self, language: str) -> None:
        self.language = language
        capsule = (
            tree_sitter_typescript.language_typescript()
            if language == "typescript"
            else tree_sitter_rust.language()
        )
        self.parser = Parser(Language(capsule))

    def normalize(self, source: Source) -> FallbackIR:
        tree = self.parser.parse(source.content.encode("utf-8"))
        if tree.root_node.has_error:
            raise InputError(f"{self.language}: Tree-sitter reported a syntax error")
        kind = "function_declaration" if self.language == "typescript" else "function_item"
        matches = [
            n
            for n in walk(tree.root_node)
            if n.type == kind and text(n.child_by_field_name("name")) == source.function
        ]
        if len(matches) != 1:
            raise InputError(f"{self.language}: require exactly one named function")
        function = matches[0]
        top = children(tree.root_node)
        if len(top) != 1 or top[0].type not in {kind, "export_statement"}:
            raise InputError("Only a standalone function file is supported; no imports or shadows")
        if self.language == "typescript":
            if (
                top[0].type != "export_statement"
                or "default" in text(top[0]).split("function", 1)[0]
            ):
                raise InputError("TypeScript requires a named exported function")
            if any(c.type == "async" for c in function.children):
                raise InputError("Async functions are unsupported")
        if function.child_by_field_name("type_parameters") is not None:
            raise InputError("Generic functions are unsupported")
        # Nested functions are outside the executable adapter contract.
        parent = function.parent
        while parent is not None:
            if parent.type in {"statement_block", "block", "mod_item", "impl_item"}:
                raise InputError("Selected function must be top-level")
            parent = parent.parent
        params = children(function.child_by_field_name("parameters"))
        if len(params) != 1 or params[0].type not in {"required_parameter", "parameter"}:
            raise InputError("Only one explicitly typed parameter is supported")
        param = params[0]
        pattern, annotation = (
            param.child_by_field_name("pattern"),
            param.child_by_field_name("type"),
        )
        if pattern is None or pattern.type != "identifier" or annotation is None:
            raise InputError("Parameter requires a simple identifier and explicit type")
        name, type_name = text(pattern), compact(text(annotation)).removeprefix(":")
        body_node = function.child_by_field_name("body")
        if body_node is None:
            raise InputError("Function requires a body")
        body = children(body_node)
        if len(body) != 1:
            raise InputError("Only a single direct return expression is supported")
        expr = body[0]
        if self.language == "typescript" and expr.type != "return_statement":
            raise InputError("TypeScript body must return its fallback expression")
        if expr.type == "expression_statement":
            expr = children(expr)[0]
            if expr.type != "return_expression":
                raise InputError("Rust body requires a tail expression or explicit return")
        if expr.type in {"return_statement", "return_expression"}:
            exprs = children(expr)
            if len(exprs) != 1:
                raise InputError("Return must contain one expression")
            expr = exprs[0]
        while expr.type == "parenthesized_expression":
            expr = children(expr)[0]
        if self.language == "typescript":
            trigger, fallback = self._typescript(expr, name)
        else:
            trigger, fallback = self._rust(expr, name, type_name)
        annotation = function.child_by_field_name("return_type")
        expected_return = (
            fallback.kind
            if self.language == "typescript"
            else {
                "number": "f64",
                "boolean": "bool",
                "string": "&str",
            }[fallback.kind]
        )
        if annotation is None or compact(text(annotation)).removeprefix(":") != expected_return:
            raise InputError("Return annotation must match the supported primitive fallback type")
        start, end = expr.start_point, expr.end_point
        return FallbackIR(
            self.language,
            source.function,
            name,
            type_name,
            trigger,
            fallback,
            Span(str(source.path), start.row + 1, start.column + 1, end.row + 1, end.column + 1),
            source.sha256,
        )

    @staticmethod
    def _typescript(expr: Node, name: str) -> tuple[str, Value]:
        if expr.type != "binary_expression":
            raise InputError("TypeScript requires parameter || literal or parameter ?? literal")
        left, op = expr.child_by_field_name("left"), expr.child_by_field_name("operator")
        if left.type != "identifier" or text(left) != name or text(op) not in {"||", "??"}:
            raise InputError("Unsupported TypeScript fallback expression")
        return (
            "falsy" if text(op) == "||" else "nullish",
            literal(expr.child_by_field_name("right")),
        )

    @staticmethod
    def _rust(expr: Node, name: str, type_name: str) -> tuple[str, Value]:
        if expr.type != "call_expression":
            raise InputError("Rust requires a direct unwrap_or call")
        field, args = expr.child_by_field_name("function"), expr.child_by_field_name("arguments")
        if (
            field.type != "field_expression"
            or text(field.child_by_field_name("field")) != "unwrap_or"
        ):
            raise InputError("Rust requires a syntactic unwrap_or candidate")
        if len(children(args)) != 1:
            raise InputError("unwrap_or requires a literal argument")
        receiver = field.child_by_field_name("value")
        trigger = "none"
        if receiver.type != "identifier" or text(receiver) != name:
            # Exact known pure closures only. Their method semantics still need resolution evidence.
            patterns = {
                "f64": f"{name}.filter(|v|*v!=0.0&&!v.is_nan())",
                "bool": f"{name}.filter(|v|*v)",
                "&str": f"{name}.filter(|v|!v.is_empty())",
            }
            inner = type_name.split("<", 1)[-1].removesuffix(">")
            if receiver.type != "call_expression" or compact(text(receiver)) != patterns.get(inner):
                raise InputError("Unsupported Rust receiver or filter closure")
            trigger = "filtered_falsy"
        return trigger, literal(children(args)[0])
