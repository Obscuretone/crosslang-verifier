# Pair manifests and supported subset

A manifest explicitly pairs two standalone functions; the CLI does not guess migration alignments. Start by copying one of the 40 committed fixture directories. Each source must be at most 64 KiB; a manifest at most 128 KiB.

```json
{
  "schema_version": 1,
  "id": "example",
  "typescript": {"path": "source.ts", "function": "evaluate", "sha256": "SHA256_OF_UTF8_SOURCE"},
  "rust": {"path": "source.rs", "function": "evaluate", "sha256": "SHA256_OF_UTF8_SOURCE"},
  "assumptions": {
    "typescript_type": "number|null|undefined",
    "rust_type": "std::option::Option<f64>",
    "rust_method": "std::option::Option::unwrap_or",
    "input_mapping": "nullish-to-none;present-to-some",
    "domain": "number",
    "note": "Review justification for the primitive and standard library identities."
  }
}
```

Paths resolve relative to the manifest. Source hashes use UTF-8 text as read by Python with universal newline handling; fixtures use LF. Re-review assumptions whenever source changes, then compute new hashes (for LF sources, `shasum -a 256 source.ts source.rs`). Whitespace is removed in type declarations for assumption matching. The manifest hash itself is included in reports.

An optional `expected` label (`regression` or `control`) is for suite validation, not input to the semantic rule or observation comparison. The corpus also stores `description` and `witness`; these are test metadata. No runner reads the expected label.

Supported TypeScript: one named exported, synchronous non-generic function with one explicitly typed parameter, a primitive return annotation, and one return expression of the form `x || literal` or `x ?? literal`. Parentheses around the whole return expression and comments are supported. Types: `number`, `boolean`, `string`, each optionally unioned with `null` and/or `undefined`.

Supported Rust: one standalone function with one explicitly typed `Option<f64>`, `Option<bool>`, or `Option<&str>` parameter (also `std::option::Option<...>`), a matching primitive return annotation, and one tail/return expression `x.unwrap_or(literal)`. Use `pub fn` so the execution harness can invoke it. The normalizer intentionally allows a private function to be parsed, but execution will report its compiler error as inconclusive. No imports, type aliases, extra declarations, shadowing definitions, generics or module nesting are supported.

The following pure Rust receiver forms are also recognized, with an additional explicit assumption `"rust_filter_method": "std::option::Option::filter"`:

```rust
x.filter(|v| *v != 0.0 && !v.is_nan()).unwrap_or(10.0)
x.filter(|v| *v).unwrap_or(true)
x.filter(|v| !v.is_empty()).unwrap_or("anonymous")
```

Closure spelling is deliberately fixed (`v`) except for whitespace. Other closures are unsupported. Fallbacks must be booleans, finite decimal/exponent number literals, or double-quoted JSON-compatible strings. Both languages must return the same primitive kind. No fallback calls, dynamic defaults, allocations, integers/BigInt, objects, arrays, Result methods, effects, exceptions or panic equivalence are modeled. Lone UTF-16 surrogates are outside the shared Rust-string domain.

The generator tries primitive falsy values, ordinary values, null/undefined when declared, and both fallback literals. The numeric domain uses `f64`; it includes signed zero, NaN and infinities. String candidates include whitespace, Unicode, quotes, backslashes and newlines. Booleans include true and false. Generation is deterministic and deduplicated.

`assumptions.allowed_inputs` can restrict the domain to 1–64 explicit wire values. In that mode **only those values are candidates**; the report must be interpreted within that finite domain. Example:

```json
"allowed_inputs": [
  {"kind": "number", "value": "1"},
  {"kind": "number", "value": "2"},
  {"kind": "null", "value": null}
]
```

Numbers use strings to preserve special values. Tags are `"NaN"`, `"Infinity"`, `"-Infinity"`, and `"-0"`. Booleans use JSON booleans, strings use JSON strings, and missing kinds use `null` as their wire payload. Bare JSON numbers are rejected. Negative-zero wire input must use `"-0"`.

Runner defaults: 30 seconds per subprocess, 1 MiB combined output per subprocess; Docker limits one CPU, 512 MiB memory, 64 processes, and a 256 MiB temporary filesystem. Compilation is offline with a fixed dependency-free Cargo project. Timeouts and failures make the whole comparison inconclusive even if some observations were emitted. Use a larger `--timeout` if startup/compilation on your host needs it.
