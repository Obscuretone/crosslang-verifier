# crosslang-verifier

**Working today:** give it two files; it dumps both syntax trees and their diff. Tests and CI pass.

**Not implemented:** general cross-language AST parity. The basic command does not decide whether a TypeScript-to-Rust rewrite is correct.

## Use it

Python 3.11+:

```sh
git clone https://github.com/Obscuretone/crosslang-verifier.git
cd crosslang-verifier
pip install -e .
crosslang-verifier before.ts after.rs --output-dir asts
```

You get `left.ast.json`, `right.ast.json` and `diff.txt`. It also prints the trees and diff. Supports `.ts`, `.tsx` and `.rs`. No manifest, Node, Cargo or Docker needed for this command; it never executes the input files.

Exit codes: `0` = same syntax tree, `1` = different trees, `2` = input/parse error. A syntax difference is not a confirmed behavioral bug.

## How hard is AST parity?

Dumping trees is straightforward. Cross-language parity is the harder part: equivalent TypeScript and Rust produce different parser trees. Both must be mapped into a shared representation before their operations can be compared meaningfully.

For example:

```text
TypeScript: x || fallback          -> fallback when x is falsy
Rust:       x.unwrap_or(fallback)  -> fallback when x is None
```

Those conditions differ for a present empty string. The repository's optional fallback checker handles this narrow case and can execute a counterexample under explicit assumptions. It is not a general cross-language parity checker.

A few well-defined mappings are manageable. General rewrites require handling types, control flow and language-specific behavior; matching AST shapes alone still would not prove matching behavior.

[Tests and CI](https://github.com/Obscuretone/crosslang-verifier/actions/workflows/ci.yml) · [Optional behavioral checks](docs/ADVANCED.md) · [Preserved evidence](evidence/README.md)

MIT licensed. By **ObscureTone**.
