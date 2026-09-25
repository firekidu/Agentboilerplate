# Verification record

Version 0.1.0 verified on 25 September 2026.

## Checks completed

- Installed the frozen Python environment successfully with `uv sync --frozen`.
- Ran 21 passing application checks with the Qdrant embedded client and deterministic fake AI. The PostgreSQL integration check was skipped because a suitable PostgreSQL server could not be started in the authoring environment.
- Ran the same 21 checks against the actual Qdrant 1.19.1 server over HTTP. This used an in-memory application metadata store and in-memory LangGraph checkpoint saver, so it did not verify PostgreSQL.
- Exercised upload, citation mapping, PDF page references, unsupported and oversized inputs, empty knowledge bases, customer separation, key roles, duplicate detection, partial ingestion recovery, invalid citation rejection, quotas, bounded current history, conversation deletion, document deletion, concurrent-operation rejection, health and metrics access.
- Ran the no-model teaching graph and Python lint checks. Checked the shell scripts for syntax errors.
- Created and downloaded a snapshot from Qdrant 1.19.1, verified its checksum, restored it with the supplied helper onto a clean Qdrant instance, and verified its point count. This was a Qdrant-only drill; the complete PostgreSQL/Qdrant backup procedure still requires a target-host test.
- GitHub Actions [run 36126773233](https://github.com/firekidu/Agentboilerplate/actions/runs/36126773233) passed on commit `9310dc350f85815c980aa8932e17d5ea834f1479`: all 22 tests, including real PostgreSQL checkpoint persistence, quotas and deletion; Python lint; Docker image build; and the complete local Compose stack startup and readiness check in fake AI mode. Application test coverage was 92%. The PostgreSQL test recreates the application runtime, not the database server.

## Checks still required on the target deployment

- Repeat the container checks on your target host and verify Caddy HTTPS. CI did not provision a domain or test public TLS.
- Run the live embedding and model calls using your own provider account. No paid model key was supplied during authoring.
- Perform a complete paired PostgreSQL and Qdrant backup and restoration drill.
- Test VPS or EC2 networking, DNS, TLS, alerts, spending controls and recovery on your chosen account.
- Evaluate real answer accuracy, customer workload capacity, prompt-injection behaviour and operating costs. The fake backend cannot establish those results.

The repository includes deployable configuration and operating instructions. No paid infrastructure was provisioned or launched during authoring. Do not infer that deployment, commercial readiness or model quality has been verified from unit-test success.
