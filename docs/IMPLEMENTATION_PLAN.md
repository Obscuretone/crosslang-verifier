# ObscureTone Semantic Diff — implementation plan

This plan precedes implementation. Scope: a Python CLI that compares explicitly paired, single-argument TypeScript and Rust functions for primitive truthiness/fallback migrations. It does not prove semantic equivalence.

## Stages

1. Establish packaging, typed shared IR, fixture schema and dependency-injected context. Require explicit source-bound assumptions; expose a resolver interface for future compiler-backed type/method resolution.
2. Parse both complete files using Tree-sitter. Normalize only a documented expression subset into shared fallback semantics. Reject parse errors, ambiguous function selection and unsupported bodies. Never identify `Option::unwrap_or` solely by spelling.
3. Add a rule registry for `||`/`??` versus resolved standard `Option::unwrap_or`, including an explicit truthiness filter control. Generate bounded primitive counterexample candidates within the declared domain.
4. Execute the actual TypeScript and Rust files through fresh Node and offline Cargo projects. Use a Docker backend by default (network disabled, read-only root, resource bounds); provide an explicitly selected local-process backend for trusted fixtures, with isolated directories and bounded subprocesses. Capture failures separately from observations.
5. Produce versioned JSON and readable console reports. Preserve assumptions, locations, source hashes, candidates, observations, command evidence and execution errors. Separate static warnings, confirmed differences, no-difference-on-candidates and unsupported inputs.
6. Commit 20 regression cases and 20 preserving controls; add unit, integration and CLI tests, CI, license, contributor and architecture documentation.
7. Run available checks, save actual results and environment versions, publish GitHub repository and inspect CI. Record limitations rather than substituting simulated results.

## Acceptance criteria

- Python package installs and console/module entry points work.
- Both language adapters use real Tree-sitter syntax trees and retain source spans.
- No semantic rule runs without validated explicit assumptions or a resolver's evidence. A same-named custom method does not resolve automatically.
- Generated candidates include the declared primitive domain's relevant falsy and missing values, and ordinary values. Unsupported values cannot silently change representation across languages.
- Confirmation requires successful execution of both original implementations with matching input identities and differing normalized outputs. Compiler, timeout, protocol and runtime errors are inconclusive, never confirmed differences.
- Exactly 20 labeled regressions and 20 labeled controls are checked against their expectations. Controls claim only that no difference was observed on the recorded candidates.
- Tests cover resolution gates, syntax limitations, rule dispatch, candidate generation, normalization, source-bound assumptions, runner failures, report/CLI behavior and the fixture corpus.
- Docker backend isolates untrusted execution; local execution is opt-in and documented as suitable only for trusted sources. Cargo uses no downloaded crate dependencies or source build scripts.
- CI tests on supported Python versions with Node and Rust, and retains evidence artifacts. JSON schema/version and protocols leave extension points for adapters, SARIF reporters and GitHub Action consumers.
- README is ObscureTone branded, includes actual commands and limitations, and makes no claim of full equivalence or invented benchmark performance.
- Every context-consuming function aliases the context services it uses to local variables at function entry.
