# ObscureTone Semantic Diff

**Hear the behavior that syntax hides.**

[![CI](https://github.com/Obscuretone/obscuretone-semantic-diff/actions/workflows/ci.yml/badge.svg)](https://github.com/Obscuretone/obscuretone-semantic-diff/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

A Python CLI for finding **bounded, reproducible semantic regressions in TypeScript-to-Rust migrations**. Tree-sitter parses both languages; language adapters normalize supported code into a shared IR; a resolution gate and extensible rules generate candidates; isolated Node and Cargo runners check the actual implementations.

This MVP checks primitive truthiness and fallback behavior. **It never claims full semantic equivalence.** No-difference results describe only the recorded candidates under the declared assumptions.

```typescript
// TypeScript                         // Rust
return x || 10;                       // x.unwrap_or(10.0)
```

For a present `0`, TypeScript returns `10` while Rust returns `0`. The same mismatch can involve `false`, `""`, `-0`, and `NaN`. Nullish `??` is different: it preserves present falsy values. Rust `unwrap_or` evaluates its argument eagerly; this MVP permits literal defaults only and does not analyze side effects.

## Run it

Requirements: Python 3.11+, Docker for isolated execution, and downloaded Node/Rust images. Supported hosts are Linux and macOS. Parsing and static reports need neither Node nor Rust installed on the host.

```sh
git clone https://github.com/Obscuretone/obscuretone-semantic-diff.git
cd obscuretone-semantic-diff
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]' -c requirements-dev.lock
docker pull node:22-bookworm-slim
docker pull rust:1-slim-bookworm

# Static prediction only; never labeled a confirmed difference.
obscuretone-diff compare fixtures/regressions/01-zero-count/manifest.json

# Execute the original functions. Exit 1 means a confirmed difference.
obscuretone-diff compare fixtures/regressions/01-zero-count/manifest.json \
  --execute --json-output evidence/example.json

# A suite exits 0 when every labeled fixture meets its expectation.
obscuretone-diff suite fixtures --execute --json-output evidence/corpus.json
```

Use `--format json` for machine-readable stdout. The module entry point also works: `python -m obscuretone_semantic_diff`. Docker images are never downloaded implicitly during a probe. Override image tags with `--node-image` / `--rust-image`; use digest-pinned images for reproducibility.

For **trusted code only**, `--execute --backend local` uses installed Node 22.18+ and Cargo/Rust in fresh temporary projects. This backend runs with your host permissions. It is not a security sandbox.

## Evidence and interpretation

| Status | Meaning |
| --- | --- |
| `unsupported` | Parsing, supported syntax, resolution, mapping, or rule eligibility failed. No semantic conclusion. |
| `static_warning` | A resolved rule predicts a candidate mismatch; implementations have not been run. |
| `static_checked` | No candidate mismatch predicted; implementations have not been run. |
| `confirmed_difference` | Both implementations ran successfully and produced different normalized outputs for a recorded input. |
| `no_difference_observed` | Both implementations ran and matched on the recorded candidates only. |
| `inconclusive` | A runtime, compiler, timeout, output, or runner-protocol failure prevented comparison. |

Compare exit codes: `0` static check/warning or no observed difference, `1` confirmed difference, `2` unsupported/inconclusive/input error. Static warnings deliberately do not fail CI. Suite exit codes: `0` expectations met (or static-only checks complete), `1` executed expectation mismatch, `2` unsupported/inconclusive/input error. A static suite does **not** count expectations as passed.

Each JSON report contains source and manifest SHA-256 hashes, source spans, declared assumptions, resolution provenance, candidate inputs, commands, stdout/stderr, observations and counterexamples. Numeric tags preserve `NaN`, infinities and signed zero; null and undefined remain distinct inputs and are explicitly mapped to Rust `None`. Numeric equality follows normalized binary64 values, with NaNs equal for comparison and `-0` distinct from `+0`.

The committed [evidence](evidence/README.md) records actual checks, tool versions, limitations and reproducible reports. There are **20 synthetic known regressions and 20 preserving controls** with per-case descriptions and designated regression witnesses. They are a focused correctness corpus, not a production benchmark or a measure of general detection accuracy.

## Resolution is mandatory

The MVP resolver uses **explicit fixture assumptions**, not a TypeScript type checker or rust-analyzer. A parsed annotation or a method named `unwrap_or` alone cannot authorize a semantic rule. A manifest must assert the primitive TypeScript type, Rust `Option` type, standard library method identity, input mapping and justification. These assertions are checked against supported annotations and bound to reviewed source hashes. Assertions remain the author's responsibility; compiler verification is reported as `false`.

Read [the manifest and supported syntax guide](docs/USAGE.md) to add your own pair. The intentionally narrow adapter accepts standalone, single-parameter functions and literal fallbacks. Unsupported expressions are reported, never silently approximated.

## Development

```sh
# Fast unit/static checks; execution tests are explicitly skipped.
pytest -q

# All tests, including real isolated Node and Cargo executions.
pytest --run-integration --integration-backend=docker \
  --cov=obscuretone_semantic_diff --cov-report=term-missing \
  --cov-report=json:evidence/coverage.json --junitxml=evidence/pytest.xml

ruff check .
ruff format --check .
python -m build
```

CI runs all tests on Python 3.11 with local trusted fixture execution and Python 3.13 with Docker isolation, and uploads reports as artifacts. See [architecture](docs/ARCHITECTURE.md), [implementation plan and acceptance criteria](docs/IMPLEMENTATION_PLAN.md), [security boundaries](docs/SECURITY.md), [report contract](docs/REPORT_FORMAT.md), and [contributing](CONTRIBUTING.md).

The context object injects adapters, resolution, candidates, rules and runners. Services are aliased to local variables at function entry. Protocols and a versioned report model provide extension points for more languages, compiler-backed resolution, SARIF reporters and GitHub Action integrations. Those integrations are future work, not advertised as shipped.

MIT licensed. Built under the **ObscureTone** name.
