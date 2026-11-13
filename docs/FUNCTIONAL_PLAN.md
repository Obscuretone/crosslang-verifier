# Functional verification experiment: plan and acceptance criteria

Build on the existing typed shared AST rather than replace the parser or erase type differences.

1. Add `--verify` to the two-file command. Select corresponding public functions (or one explicit function), require matching supported primitive signatures and resolved bodies, and retain source hashes and assumptions.
2. Generate deterministic primitive boundary cases. Enumerate complete boolean domains when they fit the case budget. Ask Z3 whether loop-free shared function models can return observably different values, including IEEE binary64 rounding, NaN and signed zero. Solver witnesses are candidates, never confirmed source differences.
3. Compile/run the original TypeScript and Rust with small invocation bridges using the existing bounded, isolated Node/Cargo runners. Compare indexed, typed return observations. Compiler failures and unavailable runtimes are inconclusive.
4. Report confirmed runtime differences, exhaustive finite-domain agreement, agreement proven in the supported IR model plus runtime samples, sample agreement only, or inconclusive results. Never claim arbitrary-program equivalence. Loops, recursion and remainder receive no solver proof.
5. Exercise equivalent rewrites, real regressions, a solver-targeted branch, loops, remainder, missing resolution and compilation failure. Publish actual CI output and preserve historical evidence.

Acceptance: tests check the status boundaries, real Node/Cargo integration validates independent pairs, both CI backends pass, and the repository contains reproducible evidence. A proof concerns pure deterministic return values in the stated domain/model, not termination of arbitrary code, resources, timing, effects, ABI, deployment or full language equivalence. All normalized mappings remain conditional on their documented resolution/assumptions.
