# Reproducible evidence

Evidence files record actual execution, not expected results copied from fixture labels. The initial local environment is macOS arm64 with Python 3.13.1, Docker 29.2.1, container Node 22.23.5 and container Rust/Cargo 1.100.0. Host Cargo/rustc are absent; Rust checks use Docker. Exact tool output and image digests are in `environment.json`.

Reproduce from the repository root after README setup:

```sh
pytest --run-integration --integration-backend=docker \
  --cov=obscuretone_semantic_diff --cov-fail-under=85 \
  --cov-report=term-missing --cov-report=json:evidence/coverage.json \
  --junitxml=evidence/pytest.xml
obscuretone-diff suite fixtures --execute --json-output evidence/corpus.json
python tools/record_environment.py --backend=docker --output evidence/environment.json
ruff check .
ruff format --check .
python -m build
```

**Hosted CI passed 179 tests with zero failures/skips on each of two Python/backend combinations.** All 20 regressions were confirmed and all 20 controls matched their recorded candidates in both jobs. See [`RESULTS.md`](RESULTS.md) for coverage, exact provenance and developer-host limitations.

The first fast host run passed 135 tests and explicitly skipped 44 opt-in execution tests (`pytest-unit.txt`). Separate local Docker attempts encountered inconclusive runner failures; those failed/interrupted runs are retained alongside the successful hosted artifacts. Skipped or interrupted tests are never counted as complete execution.

Top-level corpus, JUnit and coverage files are copies of the hosted Python 3.13 Docker artifact. The top-level environment record describes the macOS host; hosted environments are in `ci/43328393792/`. `provenance.json` identifies every copied artifact and its hashes.

Reports retain original observations, source hashes, candidate identities, commands and stderr. Temporary command directories are ephemeral. Tests use synthetic functions and explicit assumptions, not production migrations. Results support only the recorded input domain. No benchmark performance or full semantic equivalence is claimed.

The initial runner development check exposed an executable-filesystem permission problem after successful Rust compilation. The container temporary mount was corrected to allow executing the generated binary while preserving `nosuid,nodev`. This was a runner setup failure, never a confirmed semantic regression. An early test launch before editable installation failed at import; installation resolved it before the execution-enabled validation was restarted.

CI uploads fresh JSON corpus reports, JUnit results, coverage and runtime provenance for each Python/backend matrix job. Committed evidence is a snapshot; CI artifacts and the workflow run linked in `RESULTS.md` establish later checks against Git revisions.
