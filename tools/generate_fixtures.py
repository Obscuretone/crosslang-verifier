"""Rebuild the synthetic, reviewed fixture corpus. No performance claims implied."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "fixtures"


def val(kind: str, value=None) -> dict:
    return {"kind": kind, "value": value}


def case(
    name,
    expected,
    domain,
    fallback,
    *,
    op="||",
    filtered=False,
    rust_fallback=None,
    allowed=None,
    witness=None,
    description="",
):
    number = domain == "number"
    ts_literal = json.dumps(fallback, ensure_ascii=False)
    rs_literal = json.dumps(
        fallback if rust_fallback is None else rust_fallback, ensure_ascii=False
    )
    if number:
        ts_literal = str(fallback)
        rs_literal = str(float(fallback if rust_fallback is None else rust_fallback))
    primitive = {"number": "f64", "boolean": "bool", "string": "&str"}[domain]
    ts_type = f"{domain}|null|undefined"
    rs_type = f"std::option::Option<{primitive}>"
    receiver = "x"
    if filtered:
        receiver += {
            "number": ".filter(|v| *v != 0.0 && !v.is_nan())",
            "boolean": ".filter(|v| *v)",
            "string": ".filter(|v| !v.is_empty())",
        }[domain]
    ts = (
        f"export function evaluate(x: {domain} | null | undefined): {domain} {{\n"
        f"    return x {op} {ts_literal};\n}}\n"
    )
    rust = (
        f"pub fn evaluate(x: {rs_type}) -> {primitive} {{\n"
        f"    {receiver}.unwrap_or({rs_literal})\n}}\n"
    )
    directory = ROOT / ("regressions" if expected == "regression" else "controls") / name
    directory.mkdir(parents=True, exist_ok=True)
    assumptions = {
        "typescript_type": ts_type,
        "rust_type": rs_type,
        "rust_method": "std::option::Option::unwrap_or",
        "input_mapping": "nullish-to-none;present-to-some",
        "domain": domain,
        "note": "Synthetic standalone fixture: primitives map directly to Some; "
        "null and undefined map to None. " + description,
    }
    if filtered:
        assumptions["rust_filter_method"] = "std::option::Option::filter"
    if allowed is not None:
        assumptions["allowed_inputs"] = allowed
    manifest = {
        "schema_version": 1,
        "id": name,
        "expected": expected,
        "description": description,
        "assumptions": assumptions,
    }
    if witness is not None:
        manifest["witness"] = witness
    for lang, filename, source in [("typescript", "source.ts", ts), ("rust", "source.rs", rust)]:
        (directory / filename).write_text(source, encoding="utf-8")
        manifest[lang] = {
            "path": filename,
            "function": "evaluate",
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
        }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main():
    def N(v):
        return val("number", str(v))

    def B(v):
        return val("boolean", v)

    def S(v):
        return val("string", v)

    missing = [val("null"), val("undefined")]
    regressions = [
        ("01-zero-count", "number", 10, N(0), "Zero count is replaced by a default in TypeScript."),
        (
            "02-zero-retries",
            "number",
            -1,
            N(0),
            "A zero retry budget is replaced by a negative sentinel.",
        ),
        (
            "03-zero-fraction",
            "number",
            0.25,
            N(0),
            "Zero rate is replaced by a fractional default.",
        ),
        (
            "04-negative-zero",
            "number",
            1,
            N("-0"),
            "Signed negative zero is falsy but remains Some(-0.0).",
        ),
        (
            "05-nan-reading",
            "number",
            42,
            N("NaN"),
            "NaN is falsy but is a present Rust floating-point value.",
        ),
        (
            "06-signed-zero-default",
            "number",
            -0.0,
            N(0),
            "Positive zero and a negative-zero fallback have distinct observable signs.",
        ),
        (
            "07-disabled-flag",
            "boolean",
            True,
            B(False),
            "False flag is replaced by true by logical OR.",
        ),
        (
            "08-empty-username",
            "string",
            "anonymous",
            S(""),
            "Empty username triggers the TypeScript default.",
        ),
        (
            "09-empty-label",
            "string",
            "untitled",
            S(""),
            "Empty display label is present in Option.",
        ),
        (
            "10-empty-unicode",
            "string",
            "音",
            S(""),
            "Unicode fallback is observed only in TypeScript for an empty input.",
        ),
        (
            "11-empty-escaped",
            "string",
            'line\n"quoted"',
            S(""),
            "Escaped fallback text must survive both harnesses.",
        ),
        (
            "12-zero-timeout",
            "number",
            3000,
            N(0),
            "A zero timeout is interpreted as absent by logical OR.",
        ),
        (
            "13-zero-offset",
            "number",
            -0.5,
            N(0),
            "A zero offset differs from the negative fractional fallback.",
        ),
        (
            "14-nan-zero-default",
            "number",
            0,
            N("NaN"),
            "A zero fallback still changes NaN under logical OR.",
        ),
    ]
    for name, domain, fallback, witness, description in regressions:
        case(name, "regression", domain, fallback, witness=witness, description=description)
    for name, domain, fallback, witness in [
        ("15-nullish-overfiltered-number", "number", 9, N(0)),
        ("16-nullish-overfiltered-bool", "boolean", True, B(False)),
        ("17-nullish-overfiltered-string", "string", "default", S("")),
    ]:
        case(
            name,
            "regression",
            domain,
            fallback,
            op="??",
            filtered=True,
            witness=witness,
            description="Over-filtering a nullish fallback incorrectly drops present falsy values.",
        )
    case(
        "18-changed-missing-number",
        "regression",
        "number",
        1,
        op="??",
        rust_fallback=2,
        witness=val("null"),
        description="Different literal defaults diverge on missing numbers.",
    )
    case(
        "19-changed-missing-bool",
        "regression",
        "boolean",
        False,
        op="??",
        rust_fallback=True,
        witness=val("undefined"),
        description="Different boolean defaults diverge on undefined.",
    )
    case(
        "20-changed-missing-string",
        "regression",
        "string",
        "old",
        op="??",
        rust_fallback="new",
        witness=val("null"),
        description="Migration changes the missing string default.",
    )
    for name, domain, fallback in [
        ("01-nullish-number", "number", 10),
        ("02-nullish-bool", "boolean", True),
        ("03-nullish-string", "string", "anonymous"),
    ]:
        case(
            name,
            "control",
            domain,
            fallback,
            op="??",
            description="Nullish and Option fallback preserve present falsy primitives.",
        )
    for name, domain, fallback in [
        ("04-filter-number", "number", 10),
        ("05-filter-bool", "boolean", True),
        ("06-filter-string", "string", "anonymous"),
    ]:
        case(
            name,
            "control",
            domain,
            fallback,
            filtered=True,
            description="Explicit Option filtering reproduces primitive logical-OR truthiness.",
        )
    case(
        "07-false-default",
        "control",
        "boolean",
        False,
        description="Replacing false by false preserves the observation.",
    )
    case(
        "08-empty-default",
        "control",
        "string",
        "",
        description="Replacing an empty string by an empty string preserves the observation.",
    )
    case(
        "09-zero-restricted",
        "control",
        "number",
        0,
        allowed=[N(0), N(1), N(-1), *missing],
        description="Finite restricted inputs explicitly exclude NaN and negative zero.",
    )
    case(
        "10-positive-restricted",
        "control",
        "number",
        7,
        allowed=[N(1), N(2), N(0.5), *missing],
        description="Declared inputs are positive numbers or missing.",
    )
    case(
        "11-true-restricted",
        "control",
        "boolean",
        True,
        allowed=[B(True), *missing],
        description="Declared inputs contain no present false value.",
    )
    case(
        "12-nonempty-restricted",
        "control",
        "string",
        "fallback",
        allowed=[S("x"), S("0"), S(" "), *missing],
        description="Declared present strings are nonempty, including whitespace.",
    )
    case(
        "13-nullish-negative-zero",
        "control",
        "number",
        -0.0,
        op="??",
        description="Nullish default preserves both signed zeros and NaN when present.",
    )
    case(
        "14-nullish-false",
        "control",
        "boolean",
        False,
        op="??",
        description="False is a valid nullish fallback and present value.",
    )
    case(
        "15-nullish-unicode",
        "control",
        "string",
        "é音",
        op="??",
        description="Unicode strings map losslessly within the shared domain.",
    )
    case(
        "16-nullish-escaped",
        "control",
        "string",
        '\t"\\',
        op="??",
        description="String quoting, tabs and backslashes round-trip.",
    )
    case(
        "17-filter-zero-default",
        "control",
        "number",
        0,
        filtered=True,
        description="Filtering NaN and negative zero matters even with a zero default.",
    )
    case(
        "18-filter-negative-default",
        "control",
        "number",
        -2.5,
        filtered=True,
        description="A negative fractional fallback is preserved by explicit truthiness filtering.",
    )
    case(
        "19-filter-false-default",
        "control",
        "boolean",
        False,
        filtered=True,
        description="Filtered false values yield the same false default.",
    )
    case(
        "20-filter-empty-default",
        "control",
        "string",
        "",
        filtered=True,
        description="Filtered empty strings yield the same empty fallback.",
    )
    print("Generated 20 regressions and 20 controls")


if __name__ == "__main__":
    main()
