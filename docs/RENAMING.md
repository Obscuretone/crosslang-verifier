# crosslang-verifier identity and evidence

On November 12, 2026, Evan approved renaming the project to **crosslang-verifier** with the positioning **Find behavioral differences in cross-language rewrites.**

The existing GitHub repository was renamed in place, preserving its Git history, issues, Actions runs and evidence. The primary distribution/command is `crosslang-verifier`, the Python module is `crosslang_verifier`, and `obscuretone-diff` remains a compatibility command. Existing Python integrations must update the old `obscuretone_semantic_diff` import path. ObscureTone author/copyright attribution, the MIT license and stable rule ID `OT-FALLBACK-001` remain unchanged.

No package was uploaded to PyPI as part of this repository rename. The implementation still checks the documented TypeScript-to-Rust primitive fallback subset; the broader name does not imply additional language support or proof of full semantic equivalence.

Historical files under `evidence/`, the original implementation plan and all 40 corpus fixtures are preserved byte for byte from commit `fd825887c1052d73260b8a420ee073ce7e883d8a`. Their original names, command arrays, source hashes, environment versions and run links describe actual runs under the original identity. They are not rewritten to make them appear to have tested the renamed package.

The named [LinkedIn error-fallback example](../examples/linkedin-error-fallback/) is separate from that fixed 40-fixture corpus. The checked Python script executes the original TypeScript against both a regressed and a preserving Rust implementation, checks the empty-string witness and records fresh runner evidence. CI includes this check on both backends and uploads its JSON report with the full corpus, test results, coverage, runtime provenance and renamed package metadata.

The first rename-preview environment returned empty reads for some nonempty files, so the approved change was applied in a fresh checkout without overwriting that affected checkout. Fresh-package installation and fast tests succeeded. The first local script attempt was inconclusive because the Docker daemon socket was absent; a missing runner never counts as a semantic difference or successful demo. Final renamed validation results are recorded separately from the original evidence.
