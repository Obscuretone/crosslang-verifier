# Renamed package and checked LinkedIn reproduction

[CI run 43342968789](https://github.com/Obscuretone/crosslang-verifier/actions/runs/43342968789) completed successfully against commit [`7cef634`](https://github.com/Obscuretone/crosslang-verifier/commit/7cef634638be84014bee585f3a922f954c03185c) on November 12, 2026 (America/Toronto; artifact timestamps use UTC).

| Environment | Tests passed | Failed / skipped | Statement coverage | 40-case corpus | LinkedIn demo |
| --- | ---: | ---: | ---: | --- | --- |
| Ubuntu, Python 3.11, trusted local Node/Cargo | 184 | 0 / 0 | 94.2% | 40 expected passes | All four checks passed |
| Ubuntu, Python 3.13, isolated Docker Node/Cargo | 184 | 0 / 0 | 95.0% | 40 expected passes | All four checks passed |

Both jobs built the renamed wheel and source archive, checked the new `crosslang-verifier` command, the compatibility `obscuretone-diff` command and `python -m crosslang_verifier`, verified fixture regeneration, and passed lint/format checks. The package metadata identifies `crosslang-verifier`, retains ObscureTone attribution and the MIT license, and uses the positioning “Find behavioral differences in cross-language rewrites.” No PyPI upload was performed.

## What the checked script actually observed

[`tools/check_linkedin_example.py`](../../tools/check_linkedin_example.py) executes independently written TypeScript and Rust examples inspired by the linked discussion and verified against GitHub's primary migration report. Its checked domain is exactly undefined, null, empty string and `timeout`.

- The original TypeScript returns `Unknown error` for the empty string; the regressed Rust returns the empty string. That input is the only recorded counterexample in the demonstration domain.
- Missing inputs produce the fallback on both sides under the explicit nullish-to-None mapping. The ordinary string is preserved on both sides.
- The preserving Rust control explicitly filters empty strings and matches all four recorded TypeScript outputs.
- Both backends returned `status: passed` with all four named checks true. Each report contains the actual source hashes, assumptions, input identities, runner observations, commands and the checked script's SHA-256.

The authoritative raw records are [`43342968789/evidence-py3.11-local/linkedin-example.json`](43342968789/evidence-py3.11-local/linkedin-example.json) and [`43342968789/evidence-py3.13-docker/linkedin-example.json`](43342968789/evidence-py3.13-docker/linkedin-example.json). These are minimal reproductions, not an audit of GitHub's production source, and they do not prove full semantic equivalence.

## Preservation and provenance

The repository was renamed in place; its numeric GitHub repository ID remains `1455935537`. All **147 historical files** under the original evidence/corpus paths, plus the license and original plan, were checked against their Git object hashes at baseline `fd825887c1052d73260b8a420ee073ce7e883d8a`. Every file matched. The original evidence was neither rewritten nor relabeled as new results.

[`43342968789/provenance.json`](43342968789/provenance.json) identifies the tested commit, original baseline, CI artifact IDs/archive hashes, per-file hashes and observed test/coverage totals. The fresh CI artifact directories preserve both complete corpus reports, JUnit, coverage, tool versions/image digests, renamed package metadata and console output. The script hashes in both hosted demo reports were independently checked against the committed script bytes.

## Developer-host checks and limits

Fresh local installation and all three entry points worked. The fast local test suite passed **139 tests**, with **45 execution tests explicitly skipped**. Lint/format and wheel/source builds passed. Local attempts to execute the new demo were inconclusive: first the Docker socket was absent; a later attempt lost the Docker daemon mid-run (EOF followed by an absent socket). Those statuses are preserved in [`developer-host/`](developer-host/), not counted as passes. Full real execution evidence comes from the two successful hosted jobs above.

No benchmark performance claim or full-equivalence claim is made. Agreement describes the recorded candidates and explicit assumptions only.
