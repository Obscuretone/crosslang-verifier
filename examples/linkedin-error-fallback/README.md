# Empty error fallback: independent reproduction

This example was motivated by [Luca Cavallin's LinkedIn discussion](https://lnkd.in/p/gcqsjx2n) and checked against the underlying [GitHub migration report](https://github.blog/ai-and-ml/generative-ai/migrating-the-github-copilot-runtime-to-rust-using-copilot/). The historical research chat identified the LinkedIn author; direct retrieval of the LinkedIn short link was unavailable during this implementation. The technical behavior is documented by GitHub's primary report.

The TypeScript expression `event.error || "Unknown error"` replaces an empty string. An `Option::unwrap_or` port preserves a present empty string. Our standalone functions take that error value as their single parameter; these are independently written minimal examples, not GitHub's production code.

| Input | TypeScript logical OR | Rust unwrap_or | Rust with explicit empty-string filter |
| --- | --- | --- | --- |
| undefined | Unknown error | Unknown error (None) | Unknown error (None) |
| null | Unknown error | Unknown error (None) | Unknown error (None) |
| empty string | Unknown error | empty string | Unknown error |
| timeout | timeout | timeout | timeout |

Both manifests declare the primitive string types, standard Option method identity, nullish-to-None mapping, and an explicit four-input domain. Source SHA-256 hashes bind those reviewed declarations to the original, migrated and preserving functions. This example does not imply equivalence beyond those inputs.

From the repository root after installing the project and downloading the README's Docker images:

```sh
python tools/check_linkedin_example.py --backend docker \
  --json-output demo-evidence/linkedin-example.json
```

The script executes both the regressed and preserving Rust implementations against the original TypeScript. It checks the exact empty-string witness and the preserving observations. Exit `0` means all expected demonstration checks passed; `1` means an expectation failed; `2` means execution/input verification was inconclusive. This differs deliberately from the CLI's compare exit `1` for a confirmed regression: this script is a checked demonstration with an expected regression.

Use `--format json` for a complete evidence envelope. `--backend local` is available for trusted sources with installed Node/Cargo, and has host permissions. No success is inferred from a static warning, a missing runtime, or a partial output stream.
