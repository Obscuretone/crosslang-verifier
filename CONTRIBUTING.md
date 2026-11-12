# Contributing

Install with `pip install -e '.[dev]' -c requirements-dev.lock`. Follow README checks and add focused cases for behavioral changes. Execution tests require `--run-integration` and Node/Cargo or the two Docker images; skipped integration tests are not evidence of execution.

Keep semantics conservative: unsupported syntax must remain unsupported until resolution, normalization, candidate generation and execution mapping are justified. Never infer standard library identity from a method spelling. Add a reviewed fixture or compiler-backed resolution evidence before enabling a rule. Test a known regression and a preserving control for each new behavior.

Use Python for backend/CLI code. Inject services through `Context` and alias each service used by a context-consuming function at entry. Keep language-specific details in adapters/resolvers/runners and use the shared report DTOs. Preserve the distinction between static warnings and successful execution evidence.

The synthetic corpus is generated with `python tools/generate_fixtures.py`; commit the readable TypeScript, Rust and manifest files too. Generator edits must reproduce the committed corpus. Updating a source hash means reviewing its explicit assumptions again.

Do not claim full semantic equivalence, general detection rates or performance results from this corpus. Report actual commands, versions, passed/failed/skipped counts and limitations. CI uploads evidence artifacts and checks both local trusted execution and Docker execution.
