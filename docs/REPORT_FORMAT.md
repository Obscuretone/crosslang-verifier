# JSON contract, version 1.0

`compare --format json` returns a pair report. `suite --format json` returns an envelope with `schema_version`, `tool_version`, `generated_at`, `reports`, `expectations`, `summary`, and `equivalence_claim: false`. Input failures return `schema_version` and `error`, with exit code 2.

A pair report includes:

| Field | Meaning |
| --- | --- |
| `schema_version` | String `1.0`; consumers should reject unknown major versions. |
| `pair_id`, `status` | Pair identity and one of the six README statuses. |
| `sources` | TypeScript/Rust source SHA-256 hashes. |
| `manifest_sha256`, `assumptions` | Exact declaration provenance and scope. |
| `resolution` | Domain, Rust inner type, optional finite inputs and resolver evidence; null before resolution. |
| `ir` | Normalized expressions with language, trigger, fallback, spans and hashes. |
| `assessments` | Rule ID, message and static-warning boolean. |
| `candidates` | Ordered, tagged input values. |
| `executions` | Per-language status, backend, isolation description, command arrays, stdout, stderr, observations, error. |
| `differences` | Candidate index, input, TypeScript output and Rust output. Populated only after complete successful runs. |
| `limitations` | Human-readable scope and error explanations. |
| `equivalence_claim` | Always false. |

Wire values are objects with `kind` and `value`; see USAGE. Execution stdout uses JSON lines `{ "id": 0, "output": { "kind": "number", "value": "10" } }`. IDs must exactly match candidate order and output kind must match the declared primitive domain. Extra/missing/noisy output is a protocol error. Executions remain error statuses if compilation/execution fails; partial stdout is retained for diagnosis but never compared.

Source spans use one-based lines and one-based UTF-8 byte columns, with exclusive end positions, matching Tree-sitter coordinates. JSON uses standard finite JSON values only: numeric specials live in string payloads. JSON reports contain no fabricated timings or benchmark metrics.

Suite expectations have `passed: null` without execution or a missing expected label. Static-only suite success means analysis completed; inspect expected-passed/failed counts to distinguish actual execution. Future SARIF integration can map rule IDs and source spans and preserve runner evidence in result properties. The current CLI does not emit SARIF or GitHub annotations.
