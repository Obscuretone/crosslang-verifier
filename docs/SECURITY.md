# Execution boundary

Static analysis reads/parses text only. `--execute` runs code; Docker is the default backend. Pull trusted images yourself; the runner uses `--pull=never`, so a missing image becomes an explicit error.

Each Node/Cargo subprocess gets a fresh unprivileged container, no network, no capabilities, no privilege escalation, a read-only root, and a read-only mount containing only the generated project. No source repository, home directory, credentials or Docker socket is mounted. Only the temporary filesystem is writable. It is executable because Cargo must run its compiled binary; it is `nosuid,nodev`. CPU, memory, process count, temporary storage, output and wall-clock time are bounded. Timed-out/output-limited Docker clients have their named containers forcibly removed.

Container isolation depends on a trusted Docker daemon, kernel, runtime and images. It is not a formal security guarantee against container escapes. For high-risk hostile inputs, use an ephemeral dedicated VM/worker as an additional boundary. Image tags may change; use image digests for repeatable evidence. CI artifacts record selected image digests or host tool versions.

The explicit `--backend local` option is for trusted source fixtures only. Local execution has a clean environment, a temporary working directory, process-group termination, output caps and timeouts; it has **no filesystem or network security boundary** and runs with host permissions. Local Cargo compilation uses no crate dependencies and the generated manifest; installed toolchains/configuration are still trusted.

Do not assert standard method identities or domains unless you have reviewed them. Hash checks prevent accidental source changes under stale assertions; they do not make a false assumption true. Reports expose that assumptions are not compiler verified.

Runtime exceptions, Rust panics and compiler errors are runner failures, not confirmed behavioral counterexamples in this MVP. The observation protocol is intended for the supported primitive return subset, not malicious output forgery. Only successful, complete streams are compared.

Report security issues privately to the repository owner through GitHub rather than posting exploit details publicly.
