# crosslang-verifier

Dump and compare the syntax trees of two files.

[![CI](https://github.com/Obscuretone/crosslang-verifier/actions/workflows/ci.yml/badge.svg)](https://github.com/Obscuretone/crosslang-verifier/actions/workflows/ci.yml)

```sh
crosslang-verifier original.ts rewritten.rs
```

That's the basic workflow. It prints both Tree-sitter trees and a unified syntax diff.

## Install

Python 3.11+:

```sh
git clone https://github.com/Obscuretone/crosslang-verifier.git
cd crosslang-verifier
pip install -e .
```

The two-file command uses the Tree-sitter Python dependencies. It needs no manifest, type assumptions, Node, Cargo, Docker or running server. It parses the supplied files without executing them. Supported extensions: `.ts`, `.tsx`, `.rs`; either file can be any supported type.

## Save the ASTs

```sh
crosslang-verifier original.ts rewritten.rs --output-dir asts
```

This writes `asts/left.ast.json`, `asts/right.ast.json` and `asts/diff.txt`. Each tree includes node types, child fields, token/literal text, source positions and a source hash. Operators and punctuation are retained, so differences such as `||` versus `??` do not disappear.

For both trees and their comparison in one JSON document:

```sh
crosslang-verifier original.ts rewritten.rs --format json > comparison.json
```

Exit codes: `0` for matching syntax trees, `1` for different trees, `2` for input/parse errors. The diff ignores positions and whitespace between tokens. It preserves names, literals, operators and comments. Positions use one-based lines and UTF-8 byte columns, with exclusive end positions.

These are language-specific Tree-sitter syntax trees. Different languages normally produce different trees; inspect the emitted structures and diff to compare them. Matching trees do not prove behavioral equivalence.

## Optional deeper checks

The original manifest-based `compare` and `suite` commands remain available for executing bounded TypeScript/Rust fallback checks. See [advanced usage](docs/ADVANCED.md). Historical [evidence](evidence/README.md), the [checked LinkedIn reproduction](examples/linkedin-error-fallback/), and the original 40-fixture corpus are preserved.

## Development

```sh
pip install -e '.[dev]' -c requirements-dev.lock
pytest -q
ruff check .
ruff format --check .
```

Tree parsing and two-file CLI tests run locally without a container VM. GitHub Actions also runs the optional execution suite and retains its reports. See [architecture](docs/ARCHITECTURE.md) and [contributing](CONTRIBUTING.md).

MIT licensed. Created and maintained by **ObscureTone**.
