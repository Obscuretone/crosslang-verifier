# Functional verification: measured results

**Yes, the concept verifies useful restricted cases. It does not verify arbitrary language ports.**

Source revision: [`620a98869b9bbe273324de7f8e77f05dcc7d3dc6`](https://github.com/Obscuretone/crosslang-verifier/commit/620a98869b9bbe273324de7f8e77f05dcc7d3dc6).
[Successful hosted run](https://github.com/Obscuretone/crosslang-verifier/actions/runs/43439254233), November 13, 2026. Both jobs ran the original TypeScript/Rust bodies through Node/Cargo bridges, rather than Python emulations.

| Check | Python 3.11 / host runners | Python 3.13 / isolated containers |
|---|---:|---:|
| pytest passed | 316 | 316 |
| Failures / errors / skips | 0 / 0 / 0 | 0 / 0 / 0 |
| Coverage | 93.57% | 93.89% |
| Functional experiments with expected classifications | 22 / 22 | 22 / 22 |

The 22 experiments comprise 20 independent synthetic source pairs plus a shipping module and its threshold mutant. They produced the same classifications on both backends:

| Result | Cases | Meaning |
|---|---:|---|
| `verified_finite_domain` | 3 | All admitted boolean/optional-boolean tuples executed and agreed |
| `verified_model` | 6 | Supported shared IR query was UNSAT, plus actual source sample agreement |
| `confirmed_difference` | 8 | Original source return observations differed on a recorded input |
| `tested_agreement` | 2 | Loop/remainder samples agreed; no solver proof |
| `inconclusive` | 3 | Rust compilation failure, incompatible numeric types, unresolved methods |

These are correctness probes and a small demonstration module, not a benchmark or a measurement of production migration coverage. A model proof remains conditional on source normalization, assumptions and the stated floating-point/string model. No full semantic equivalence is claimed.

## What the evidence demonstrates

- A De Morgan rewrite has **different ASTs** but agrees on every one of its four boolean inputs.
- The shipping module's different branches and helper calls pass the supported IR check, with 44 actual numeric/boolean input tuples for `shipping` and all four boolean tuples for `eligible`.
- Changing its threshold from `>= 100` to `> 100` fails: input `(100, false)` returns `0` in TypeScript and `10` in Rust.
- A rare-branch regression is confirmed at solver-generated input `1234567.25`: TypeScript returns `1`, Rust returns `2`. That input was added to the boundary generator's cases.
- Adding positive zero versus returning the original value differs at negative zero. The report preserves the `-0` observation.
- Matching ASTs and an UNSAT IR query cannot hide an invalid Rust string escape: Cargo rejects it and the checker reports `inconclusive`.
- The existing 40-fixture fallback suite also passes: 20 confirmed regressions and 20 controls with no observed difference on their recorded candidates. Those controls are not equivalence proofs.

Each backend directory contains the untouched hosted functional report (including SMT-LIB queries, assumptions, source hashes, inputs, observations and commands), JUnit, coverage, environment, legacy corpus and LinkedIn-example outputs. [provenance.json](provenance.json) records artifact identities and file SHA-256 hashes. An additional offline audit matched 44 source hashes, replayed 20 solver queries, and checked 27 reported differing observations per backend. Replaying queries validates the saved solver results, not source-to-IR soundness.

`host/` records the developer environment and fast test run: 250 passed, 66 execution tests skipped. Host Cargo/rustc were unavailable; no local Docker/VM was launched for this work. The complete native checks above ran on GitHub's hosted machines. Existing historical evidence has been preserved.

Reproduce with installed runner images (or use `--backend local` for trusted sources and installed host runtimes):

```sh
pytest --run-integration --integration-backend docker
python tools/check_functional_verification.py --backend docker --json-output functional.json
crosslang-verifier examples/port/before.ts examples/port/after.rs --verify
```

See [the functional contract](../../../docs/VERIFICATION.md) for limits and exit codes.
