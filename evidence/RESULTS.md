# Validation results

Initial validation on November 12, 2026 (macOS arm64, Python 3.13.1):

- Fast pytest run: **135 passed, 44 explicitly skipped** (execution was not enabled).
- Ruff lint and formatting: passed.
- Editable installation, CLI entry point and wheel/source archive builds: passed.
- Fixture generation: reproduced all 40 committed cases without a diff.
- First full Docker CLI corpus run, 30-second subprocess limit: **34 expectations passed**, comprising **20 controls with no observed difference** and **14 confirmed regressions**. Six cases were inconclusive (mostly container timeout failures; one process permission error). Full evidence is retained in `corpus-initial-30s.json`.

The initial execution-enabled pytest run also encountered container startup/compilation timeouts on this host and was interrupted to avoid repeating failures under the same short timeout. Its output is retained separately. A longer timeout is configured for execution tests. Final execution results and hosted CI results will be appended after they complete.

These results are evidence for a bounded synthetic corpus under explicit assumptions. They are not a performance benchmark or proof of semantic equivalence. Cargo/rustc are unavailable on the host; real Rust execution uses the isolated Cargo container.
