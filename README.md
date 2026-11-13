# crosslang-verifier

Compare TypeScript and Rust through the **same typed AST**, rather than comparing their different parser trees.

```sh
pip install -e .
crosslang-verifier before.ts after.rs --output-dir asts
```

Python 3.11+. No manifest or execution environment needed for this command.

- **PARITY** (`0`): both files normalize to the same shared AST within the supported subset.
- **DIFFERENT** (`1`): their mapped operations, values, types or control flow differ.
- **UNRESOLVED** (`2`): unsupported code or missing resolution prevents a parity decision.

It writes `left.ast.json`, `right.ast.json` and `diff.txt`, plus the original parser trees as `left.syntax.json` and `right.syntax.json`.

## What works

Typed standalone functions; renamed parameters and local variables; arithmetic, comparisons and boolean logic; local bindings and assignments; `if/else`, `while`, returns and Rust tail returns; calls to functions declared in the same files. TypeScript `number`, `boolean` and `string` map to Rust `f64`, `bool` and `&str`. Integer widths remain distinct.

[Working example](examples/parity/): differently written TypeScript and Rust normalize to identical ASTs. Changing the multiplier produces `DIFFERENT`; an unresolved method produces `UNRESOLVED`.

```sh
crosslang-verifier examples/parity/equivalent.ts examples/parity/equivalent.rs
```

## Does this verify a port's functionality?

For a small supported subset, **yes, with a stated scope**. Add `--verify` to compile and run both original files:

```sh
crosslang-verifier before.ts after.rs --verify --json-output verification.json
```

Node/Cargo runner images must be installed for the default isolated Docker backend. `--backend local` runs trusted files on your host.

- **VERIFIED_FINITE_DOMAIN** (`0`): all declared boolean input combinations ran and agreed.
- **VERIFIED_MODEL** (`0`): the loop-free shared IR has no counterexample in its supported model, and native samples agreed. The source-to-model mapping remains an assumption.
- **CONFIRMED_DIFFERENCE** (`1`): actual Node/Rust results differ; the report includes the input.
- **TESTED_AGREEMENT** or **INCONCLUSIVE** (`2`): samples agreed without a proof, or verification could not finish.

Try the [shipping-cost port](examples/port/):

```sh
crosslang-verifier examples/port/before.ts examples/port/after.rs --verify
```

Different ASTs can still compute the same result. Matching ASTs can still fail compilation. [Experiments and exact limits](docs/VERIFICATION.md) explain what each result means.

## Fallbacks and limits

For standard Rust Option methods and a TypeScript null/undefined-to-None mapping, explicitly assert that contract with `--assume-option-mapping`. Then `??` and `unwrap_or` can match, while `||` and an unfiltered `unwrap_or` have different fallback triggers. The report records the assumption. Unknown methods never silently become standard-library calls.

This is **supported-subset AST parity**, not proof that arbitrary programs behave identically. Imports, classes, generics, async code, external calls and other unsupported constructs return `UNRESOLVED`. The local type resolver is deliberately small; it is not a full compiler.

[Supported mappings and limits](docs/PARITY.md) · [Tests and CI](https://github.com/Obscuretone/crosslang-verifier/actions/workflows/ci.yml)

Raw syntax dumps remain available with `--raw`. The original behavioral `compare`/`suite` commands and [historical evidence](evidence/README.md) are preserved; see [advanced usage](docs/ADVANCED.md).

MIT licensed. By **ObscureTone**.
