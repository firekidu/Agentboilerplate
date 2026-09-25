# Operate and recover the service

The operator's job is to know whether the service works, restore it when it breaks, and keep customer data and costs controlled. This guide assumes the repository is on a VPS or EC2 instance and Docker commands are run with sudo where required.

## Know where data lives

| Data | Location | What a restart does |
|---|---|---|
| Extracted text, embeddings, filenames and page numbers | Qdrant named volume | Preserved |
| Document status, tenant IDs and request counters | PostgreSQL named volume | Preserved |
| Questions, answers, history and intermediate graph state | PostgreSQL checkpoints | Preserved |
| API and provider credentials | Private `.env` and your password manager | Re-read when containers are recreated |
| Original uploaded PDF or text file | Not retained by this application | Keep an authorised source copy separately if required |
| TLS certificates | Caddy data volume | Preserved |

The original upload is read for ingestion and discarded after parsing. The extracted text is still customer data. A vector database does not anonymise it. A single document may appear in Qdrant, chat checkpoints, your backup copies and the AI provider's processing systems.

`docker compose stop` stops the processes. `docker compose down` also removes containers and the Compose network, but normally retains named volumes. **Do not run `docker compose down -v` on a service with data you need**: the `-v` flag deletes named volumes. CI uses it only for disposable test data.

## Inspect health and requests

`/health/live` means the web process responds. `/health/ready` checks PostgreSQL and Qdrant. Neither guarantees that the AI provider has credits or that its model works. Keep a known harmless document and a test question for an end-to-end check.

The API logs one JSON request record with a generated request ID, route, status and duration. Failure logs expose the exception type, not the provider error text. Ask customers for the request ID when diagnosing failures. Do not turn on full prompt logging without a deliberate data-handling decision.

`/metrics` uses a separate `X-Metrics-Key`, not a tenant API key. It reports request counts, latency and answer-generation token counts. Those token counts exclude embedding and rewrite calls and are **not a billing meter**. Use provider usage reports for reconciliation. The public Caddy proxy blocks metrics; scrape it from the internal network or use an SSH tunnel. Prometheus and Grafana servers are not included in this small baseline.

Useful starting alerts are readiness failures, repeated 5xx responses, disk space above a chosen threshold, out-of-memory restarts, backup failure and unusual provider spend. Choose thresholds from the pilot's actual traffic. An external uptime monitor should be able to tell you when the whole server is unreachable.

## Make a consistent backup

PostgreSQL and Qdrant store related parts of one application. The script pauses the API, dumps PostgreSQL, snapshots each Qdrant collection and restarts the API. Expect a short maintenance interruption. Schedule backups at a time your pilot customers understand.

On the server, from the repository folder:

```bash
sudo bash scripts/backup.sh
sudo ls -l backups
```

A completed set contains `postgres.dump`, its checksum, collection `.snapshot` files, `qdrant-manifest.json`, the code revision or version, and a `COMPLETE` marker. If any stage fails, the API is restarted by a shell trap and the incomplete set must not be treated as usable. The lock prevents simultaneous backup runs on the same host.

Copy completed sets to encrypted storage on another machine or a private object-storage bucket. The script does **not** encrypt or upload them automatically. Protect `.env` separately in a secrets vault; it is intentionally absent from the backup. Keep the matching code release and original authorised source documents according to the agreed retention policy. Snapshots from this script are for a single-node Qdrant instance, not a distributed cluster recovery procedure.

An example schedule after a successful manual backup is a daily root cron job. Replace the path with the real repository path; `sudo crontab -e` edits root's schedule:

```cron
0 2 * * * cd /home/ubuntu/nimble-rag-agent && bash scripts/backup.sh >> /var/log/nimble-backup.log 2>&1
```

Cron uses the server's timezone. Configure log rotation, backup age/size limits and failure alerting; a cron entry alone does not tell you when a backup failed. Retaining every backup indefinitely will eventually fill the disk.

## Practise restoration on a fresh host

Use an isolated recovery machine. Do not overwrite a running production database while learning. Restore the code release recorded in the backup and the same Qdrant major/minor version used to make it. Use the documented Qdrant compatibility requirements before changing versions.

1. Install the project and Docker on a fresh server. Restore the private configuration securely, or generate new credentials and deliberately preserve the original model, dimensions, chunk settings, collection prefix and tenant key records. Keep public inbound access closed during the test.
2. Copy one completed backup set into `backups/RESTORE_SET` inside this repository. Use the real folder name instead of `RESTORE_SET` in every command below.
3. Start **only the databases**:

```bash
sudo docker compose up -d postgres qdrant
sudo docker compose ps
```

Wait until PostgreSQL is healthy. The API must not be started yet, because it would initialise tables and the active Qdrant collection.

4. Verify the PostgreSQL dump checksum:

```bash
cd backups/RESTORE_SET
sha256sum -c postgres.sha256
cd ../..
```

5. Restore the database into the empty target. This command stops on an error and does not delete existing tables:

```bash
sudo docker compose exec -T postgres pg_restore -U rag -d rag --no-owner --no-privileges --exit-on-error < backups/RESTORE_SET/postgres.dump
```

6. Build the API image without starting it, then restore Qdrant:

```bash
sudo docker compose build api
sudo docker compose run --rm --no-deps --user 0:0 -v "$PWD/backups/RESTORE_SET:/backup:ro" api python -m scripts.qdrant_restore /backup
```

The restore helper checks each snapshot checksum and refuses to run if the target Qdrant already contains collections. It restores every collection in the manifest; it never deletes a collection for you. The one-off root user here is needed only to read root-owned backup files in the recovery container. The normal API still runs as an unprivileged user.

7. Start the API locally with `sudo docker compose up -d api`. Use the SSH tunnel to test document listing, a known answer, customer isolation and a saved conversation. Compare document and collection counts with your backup inventory. Delete a throwaway document and confirm retrieval stops using it.
8. Record how long recovery took and whether any data was missing. Only after the recovery check should you plan a controlled DNS switch and production proxy startup.

If restoration fails partway, diagnose it and prepare another clean recovery instance. Do not repeatedly overwrite partly restored data with guessed commands. The acceptance test is a working recovered application, not just a successful file download.

## Set retention and handle deletion

The project does not automatically expire chat history until you schedule the retention command. Preview a 30-day rule:

```bash
sudo docker compose exec -T api python -m scripts.retention --days 30
```

After confirming that period with your customer, apply it:

```bash
sudo docker compose exec -T api python -m scripts.retention --days 30 --apply
```

Schedule the apply command daily and monitor failures. It removes old conversations and expired request counters. If a tenant is busy, retry in a quiet period. It does not remove documents. Current per-thread history is bounded for model context, but historical checkpoints still require retention cleanup.

Deleting a document through the API removes its active-collection vectors, its metadata record, and **all conversations for that customer**, including conversations created under older embedding configurations. This conservative policy avoids retaining source text in old answers. Tell customers about that behaviour before using the delete button.

Changing the embedding model or chunking settings creates a separate collection. The old collection and its metadata remain for controlled rollback; they are not visible through the new active-collection document list. Before a model migration, export an inventory, delete obsolete documents while the old configuration is active, verify deletion, and only then switch. For a full customer erasure, process every embedding version and the relevant backup lifecycle. Do not promise that the active delete endpoint removes historical backup copies or provider-held data.

## Update code and roll back

Keep a staging copy with non-sensitive data. For each release, record the current Git commit or `VERSION`, make a completed backup, run the tests, build the new image, and repeat the acceptance questions in staging. The lock files make Python dependencies repeatable; changing `pyproject.toml` requires regenerating and testing both lock files.

For a Git checkout, fetch the approved release and check out its tag or commit. For an uploaded archive, extract the approved release in a new folder, transfer `.env` securely, and keep the previous release directory. The explicit Compose project name `nimble-rag` keeps the named volumes consistent. Do not run both releases simultaneously against the same databases.

```bash
sudo docker compose -f compose.yaml -f compose.prod.yaml up -d --build
curl -f http://127.0.0.1:8000/health/ready
```

If only application code changed and the schema is compatible, return to the previous release and rebuild. If a future change migrates the data schema, use the migration's rollback procedure or restore the verified pre-change backup. Startup schema initialisation in version 0.1.0 is not a general migration system. Add Alembic or explicit numbered migrations before changing existing tables.

The Python dependency versions are locked. The base Python and PostgreSQL image tags still move; record and pin tested image digests for a commercial release, then update those pins deliberately to receive security fixes. Do not deploy `latest` images automatically and hope rollback will work.

## Common faults

| Symptom | First checks |
|---|---|
| API fails immediately | Run setup, check required `.env` values and container logs; production refuses fake mode |
| PostgreSQL authentication fails after editing a password | An existing volume keeps the old database password; changing `.env` alone does not rotate it |
| Qdrant is unreachable | Check its container and internal URL; `localhost` inside the API points to the API container |
| No documents after changing model | A new embedding collection is active; re-ingest the source files |
| Upload remains indexing | Embedding or vector write failed; retry the same file, or delete it with an admin key |
| HTTP 401 or 403 | Check the raw API key and whether its stored role permits this action |
| HTTP 409 | Another operation for that customer is active, or the document limit is reached; read the message |
| HTTP 429 | The minute or daily customer allowance is exhausted; failed attempts also consume allowance |
| HTTP 503 | Use the request ID and server exception type; check databases, provider credits and model access |
| PDF has no text | It is probably a scan; run OCR before uploading |
| HTTPS certificate fails | Check DNS, IPv4/IPv6 records, inbound 80/443, Caddy logs and existing port owners |
| Incorrect but cited answer | Inspect the retrieved excerpt; improve documents, retrieval and evaluation rather than only the prompt |

For an incident, stop adding traffic, identify whether the issue is the API, a database or the provider, preserve useful logs, restore service from a known release, and communicate the customer impact. Record a short cause-and-fix note after recovery.
