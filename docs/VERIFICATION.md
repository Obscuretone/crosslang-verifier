# Can AST parity verify a language port?

AST parity supplies a common representation. Functional checking needs another step: compare what corresponding functions return. This experiment adds that step without treating structural similarity as a proof.

```sh
crosslang-verifier before.ts after.rs --verify \
  --json-output verification.json --output-dir solver-queries
# For trusted sources and installed host Node 22+ / Cargo:
crosslang-verifier before.ts after.rs --verify --backend local
```

Select one function with `--function NAME`; otherwise all public functions must correspond. Plain CLI use without `--verify` still only compares ASTs and never executes source. JSON separates `ast_status`, functional `status`, solver queries/candidates, generated inputs, native observations, execution errors and assumptions. Evidence contains source and query SHA-256 hashes. `--max-cases` bounds sampling (default 128; maximum 4096); a solver witness can add one input. `--solver-timeout-ms` defaults to 5000 per function. `--timeout` bounds each native process. Missing tools, solver unknowns, protocol errors and compilation failures never become equivalence claims.

## What a result establishes

| Result | Evidence | Limit |
|---|---|---|
| `verified_finite_domain` | Both originals compile and return equal observations for every admitted input tuple | Pure deterministic functions, finite boolean/optional-boolean domains within the case budget |
| `verified_model` | Z3 finds the differing-output query UNSAT; both originals compile and agree on generated inputs | Proof of the supported **IR model**, conditional on source normalization and environment; samples do not prove those mappings |
| `confirmed_difference` | Both originals execute the reported input and return different typed values | A concrete regression candidate; application-specific acceptability remains a separate decision |
| `tested_agreement` | Native boundary samples agree | No complete verification; loops and `%` currently land here |
| `inconclusive` | Unsupported resolution/signatures, model/runtime conflict, or execution failure | Investigate the recorded reason |

Exit codes are 0 for either scoped verification result, 1 for confirmed difference, 2 otherwise. A solver SAT answer is only a candidate until the actual sources confirm it. A compilation failure defeats an UNSAT model result. All reports retain `equivalence_claim: false` because full program equivalence is outside scope.

## Supported contract

Inputs: TypeScript `number`/`boolean`/`string` mapped to Rust `f64`/`bool`/`&str`; optional inputs require `--assume-option-mapping` and use the null/undefined representations actually declared in the TS signature. Return values must be nonoptional primitives. Integer width changes, missing methods/types and external calls remain gated. The existing [parity restrictions](PARITY.md) apply to every function in the files.

The solver handles loop-free locals, assignments, branches, returns, nonrecursive same-file calls, primitive equality, boolean logic, fallback triggers and binary64 `+ - * /`/comparisons. Arithmetic uses round-to-nearest ties-to-even; NaN payloads are ignored and signed zero is distinguished. Strings use an equality-only abstract domain with distinct literal constants, so string equality/empty tests and returning selected strings are supported; ordering, indexing, concatenation and UTF-16 operations are not.

Loops and recursion receive no solver proof. In particular, SMT floating-point remainder has different semantics from JS/Rust `%`, so we deliberately reject that solver mapping. Solver paths/call depth are bounded; timeout/unsupported reports are explicit. The model is an experimental executable specification, not a certified compiler translation. No check covers timing, memory use, effects, global state, I/O, exceptions as matching results, packaging, ABI or arbitrary application functionality.

Actual original function bodies are retained. The Node project appends an export alias; Rust includes the unchanged file inside a module with a bridge that immediately encodes the return. These bridges permit invocation without rewriting bodies. The Docker runner has no network, read-only sources/root, an unprivileged user and resource bounds. Local mode is explicitly for trusted inputs and is not a sandbox.

## Reproduce the experiment

```sh
python tools/check_functional_verification.py --backend local --json-output functional.json
pytest --run-integration --integration-backend local
```

[Twenty independent synthetic pairs](../examples/verification/cases.json) cover a De Morgan rewrite, changed boolean logic, arithmetic, redundant branches, floating-point rounding, a solver-targeted rare branch, string fallbacks, optional booleans, loops, remainder, compilation failure, type mismatch, unresolved methods string equality, signed zero, NaN and same-file helper rewrites. Expected classifications live in the experiment manifest and are never supplied to the checker. The same script also checks a [shipping-cost module](../examples/port/) with two public functions, helper calls and branches, then a mutant that changes the free-shipping threshold. These examples are correctness probes, not a benchmark or evidence of general real-world port coverage. CI publishes the complete report for both runtime backends; committed results are linked from the evidence index after a measured run.

Model semantics references: [SMT-LIB floating-point theory](https://smt-lib.org/theories-FloatingPoint.shtml), [Z3 floating-point guide](https://microsoft.github.io/z3guide/docs/theories/IEEE%20Floats/), [Rust f64](https://doc.rust-lang.org/std/primitive.f64.html). The [implementation plan](FUNCTIONAL_PLAN.md) records acceptance criteria.
