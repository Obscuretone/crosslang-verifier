# Validation results

## Successful hosted validation

[GitHub Actions run 43328393792](https://github.com/Obscuretone/obscuretone-semantic-diff/actions/runs/43328393792) tested commit [`99ca92d`](https://github.com/Obscuretone/obscuretone-semantic-diff/commit/99ca92d1c11cd336bc224e99c82ad67962db9025) on November 12, 2026. Both jobs completed successfully:

| Environment | Tests passed | Failed / skipped | Statement coverage | CLI corpus |
| --- | ---: | ---: | ---: | --- |
| Ubuntu, Python 3.11, local Node/Cargo | 179 | 0 / 0 | 94.2% | 20 confirmed regressions; 20 controls matched |
| Ubuntu, Python 3.13, Docker Node/Cargo | 179 | 0 / 0 | 95.0% | 20 confirmed regressions; 20 controls matched |

Both jobs also passed lint, formatting, wheel/source builds and fixture-generator reproducibility. Each corpus run reported **40 expected passes, 0 expected failures**, with real Node and Cargo execution. The 44 integration tests include all 40 fixtures, a real compiler-error case, a runtime exception, a CLI exit/report check and the trusted local Node backend.

The original downloaded artifacts are preserved under [`ci/43328393792/`](ci/43328393792/). Top-level [`corpus.json`](corpus.json), [`pytest.xml`](pytest.xml) and [`coverage.json`](coverage.json) copy the hosted Docker results. [`example.json`](example.json) extracts the zero-count pair from that corpus. [`provenance.json`](provenance.json) links the tested commit, artifact IDs, archive digests and individual file hashes. Hosted runtime versions and image digests are in each artifact's `environment.json`; the top-level `environment.json` describes the separate developer host.

## Developer host limitations and retained attempts

Local validation on November 12, 2026 (macOS arm64, Python 3.13.1):

- Fast pytest run: **135 passed, 44 explicitly skipped** (execution was not enabled).
- Ruff lint and formatting: passed.
- Editable installation, CLI entry point and wheel/source archive builds: passed.
- Fixture generation: reproduced all 40 committed cases without a diff.
- First full Docker CLI corpus run, 30-second subprocess limit: **34 expectations passed**, comprising **20 controls with no observed difference** and **14 confirmed regressions**. Six cases were inconclusive (mostly container timeout failures; one process permission error). Full evidence is retained in `corpus-initial-30s.json`.

The first execution-enabled local pytest attempt was interrupted after **98 passed, 3 failed** because of runner timeouts/cleanup failures (`pytest-initial-30s.txt` and `.xml`). Cleanup timeout handling was then hardened before the tested GitHub commit.

A 120-second retry still produced an inconclusive runner result and was interrupted after **97 passed, 1 failed** once both hosted jobs had passed (`pytest-local-retry-120s.txt` and `.xml`). This does not establish a complete successful macOS Docker test run. The failure cause on this host is not fully diagnosed. Increasing the timeout alone did not resolve it. The tool correctly retained inconclusive statuses rather than treating incomplete observations as behavioral differences.

The original runner setup attempt compiled Rust but could not execute the binary from the default non-executable temporary mount. That mount configuration was fixed and subsequent successful local cases and both complete CI jobs executed Rust normally.

These results are evidence for a bounded synthetic corpus under explicit assumptions. They are not a performance benchmark or proof of semantic equivalence. Cargo/rustc are unavailable on the host; real Rust execution uses the isolated Cargo container.
