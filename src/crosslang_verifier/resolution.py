"""Explicit assumptions are the MVP resolver; no compiler resolution is claimed."""

from __future__ import annotations

from .models import FallbackIR, InputError, Pair, Resolution, Value


class AssumptionResolver:
    def resolve(self, pair: Pair, ts: FallbackIR, rust: FallbackIR) -> Resolution:
        assumptions = pair.assumptions
        required = {
            "typescript_type",
            "rust_type",
            "rust_method",
            "input_mapping",
            "domain",
            "note",
        }
        if not required.issubset(assumptions):
            raise InputError("Resolution unavailable: explicit fixture assumptions are required")
        if assumptions["typescript_type"] != ts.parameter_type:
            raise InputError("Declared TypeScript type does not match the parsed annotation")
        if assumptions["rust_type"] != rust.parameter_type:
            raise InputError("Declared Rust type does not match the parsed annotation")
        if assumptions["rust_method"] != "std::option::Option::unwrap_or":
            raise InputError("Method resolution unavailable: require standard Option::unwrap_or")
        if assumptions["input_mapping"] != "nullish-to-none;present-to-some":
            raise InputError("Unsupported input mapping")
        if not isinstance(assumptions["note"], str) or not assumptions["note"].strip():
            raise InputError("Assumptions must explain why the mapping is justified")
        domain = assumptions["domain"]
        inner_types = {"number": "f64", "boolean": "bool", "string": "&str"}
        if not isinstance(domain, str) or domain not in inner_types:
            raise InputError("Only number, boolean and string domains are supported")
        inner = inner_types[domain]
        if rust.parameter_type not in {f"Option<{inner}>", f"std::option::Option<{inner}>"}:
            raise InputError("Rust receiver must have the declared primitive Option type")
        ts_types = set(ts.parameter_type.split("|"))
        if domain not in ts_types or not ts_types.issubset({domain, "null", "undefined"}):
            raise InputError("TypeScript type must be a primitive with optional null/undefined")
        if ts.fallback.kind != domain or rust.fallback.kind != domain:
            raise InputError("Fallback literals must match the shared primitive domain")
        if rust.trigger == "filtered_falsy":
            if assumptions.get("rust_filter_method") != "std::option::Option::filter":
                raise InputError("The filter method requires explicit standard Option resolution")
        values = assumptions.get("allowed_inputs")
        allowed = None
        if values is not None:
            if not isinstance(values, list) or not 1 <= len(values) <= 64:
                raise InputError("allowed_inputs must contain between 1 and 64 wire values")
            try:
                allowed = tuple(dict.fromkeys(Value(**v) for v in values))
            except TypeError as exc:
                raise InputError("Invalid allowed_inputs wire values") from exc
            if any(v.kind not in ts_types for v in allowed):
                raise InputError("allowed_inputs contains a value outside the declared type")
        return Resolution(
            domain,
            inner,
            {
                "provider": "explicit_fixture_assumptions",
                "compiler_verified": False,
                "method": assumptions["rust_method"],
                "source_hashes_validated": True,
                "note": assumptions["note"],
            },
            allowed,
        )
