# Run a commercial pilot

Sell a clearly bounded outcome first: for example, helping an internal support team find answers in an approved policy library. The first pilot should have a small number of trusted users, known documents, measurable acceptance questions and a named human escalation contact. Do not sell this starter as an autonomous business operator or promise error-free answers.

## Choose the first service boundary

The shipped API supports B2B integrations and an operator learning workspace. It does not provide customer signup, password recovery, payment processing, per-user permissions or an audit-ready administration portal. Keep tenant API keys on a trusted server when integrating a public website; do not embed a shared customer key in browser JavaScript. Add a backend session layer with an established identity provider before opening self-service public accounts.

All keys for one tenant can read that tenant's documents, and conversation access is separated by tenant, not individual user. Use separate tenants or separate deployments when two teams must not share information. A customer admin key can remove documents and clear the customer's conversations. The Qdrant key is an infrastructure key; never give it to customers.

For an early agency project, a separate deployment per customer can make operations and data separation easier to explain. It increases server and maintenance costs. Shared deployment is possible through the included tenant filters, but application-level filtering is not a replacement for an independent security review or database-level isolation for sensitive workloads.

## Onboard a customer

1. Agree the use case, document owners, user group, support hours and a limited pilot period.
2. Create an identifier such as `acme`, then generate its admin and reader keys:

```bash
python3 scripts/new_key.py acme --role admin
python3 scripts/new_key.py acme --role reader
```

3. Append the two printed **hash records** to the existing `API_KEYS_JSON` array in `.env`. Keep other customers' records. Store raw keys in an approved password manager and deliver them using an appropriate secure channel.
4. Recreate the API with the production Compose command. A plain process restart does not necessarily pick up changed container environment variables.
5. Load approved, current documents. Record which versions were accepted and who owns future updates.
6. Run agreed questions, unanswerable questions and separation checks using the customer's keys.
7. Keep a human fallback for missing, contradictory or important answers. Review errors with the customer during the pilot.

To rotate a key, add a new hash for the same tenant, recreate the API, switch the client to the new key, then remove the old hash and recreate again. To revoke access immediately, remove that hash and recreate the API. Revoking a key does not erase the customer's data.

## Establish answer quality

Build a customer-specific evaluation set before changing models or chunking. Start with 30 to 50 realistic questions: direct facts, paraphrases, follow-ups, conflicting documents, out-of-scope questions and deliberate instruction text inside a document. Include expected evidence, not just expected wording.

Measure whether the right passage appears in retrieval, whether the answer is supported by it, whether unsupported questions are refused, how often a human must intervene, latency and cost. Review source citations manually. A regex check can reject a made-up citation number, but it cannot prove that a real citation supports the generated claim.

The included four-case script is a smoke test, not an accuracy benchmark. Use a dedicated test tenant containing only the fictional example policy, enable live AI and run:

```bash
uv run python scripts/evaluate.py --url https://agent.yourdomain.com
```

It prompts for the reader key without putting it in shell history. Live evaluations cost money. Record model IDs, prompt version, chunk settings and document versions with your results. Set a customer-agreed acceptance threshold rather than claiming a percentage from the fake demo tests.

## Price from measured cost and support work

Your monthly cost includes hosting, backups, monitoring, model input/output tokens, document embedding, payment fees and your operating time. Follow-up questions can make an additional model call to rewrite the query. Re-ingesting documents costs embedding tokens again. Retried requests can cost money even when the customer sees an error.

Use current provider prices when making a quote. A useful calculation is:

Monthly variable model cost = input tokens / 1 million × input price + output tokens / 1 million × output price + embedding tokens / 1 million × embedding price.

Add fixed infrastructure and support costs. If your measured all-in monthly cost for one customer were GBP 80, a 60 percent gross-margin target would imply GBP 200 revenue because 80 / (1 - 0.60) = 200. This is an arithmetic example, not a recommended price or a supplier quote; it excludes any taxes not already in the cost base.

A pilot offer can separate an initial setup fee, a recurring service fee, included request/document allowances and a published overage or review process. Define what counts as a request and which changes are out of scope. The built-in rate quotas are rough request controls, not monetary budgets or a billing ledger. Apply provider-side limits and monitor actual spend.

## Protect customer data and agreements

Map where documents, extracted passages and questions travel. Live embeddings send extracted chunks to the AI provider; answer generation sends the question and retrieved passages; follow-up rewriting sends recent questions and answers. Hosting in London does not by itself keep every processing step in the UK. Confirm provider retention, training-use terms, region options and subprocessors for your actual account.

For UK customers, determine your controller/processor roles, establish suitable contracts and document retention, deletion, incident notification and transfer arrangements. Consult the ICO's current guidance and obtain appropriate professional advice for the actual service. The repository is not a compliance certificate. Agree the use of source documents; access to a file does not automatically grant rights to resell or disclose its contents.

Keep an incident contact and a procedure for lost API keys, cross-customer exposure, wrong answers and service outages. Match contractual availability and response-time promises to what you can operate. A single unattended VPS is not a basis for promising enterprise high availability.

## Complete these gates before a paid launch

- A live model passes the agreed evaluation set and sources are reviewed by a person.
- Tenant separation, role checks, key rotation and document deletion are demonstrated.
- The full container stack is built and tested on the target host; dependency and image scans are reviewed.
- A completed backup is restored to a separate machine and recovery time is recorded.
- The HTTPS domain, provider budget, uptime alerts, disk alerts and backup alerts work.
- The customer accepts the scope, human escalation, data handling, retention and support terms.
- A named operator can update, roll back and respond to an outage without relying on this chat being open.

Document uploads are for trusted administrators. File-size limits and container memory limits do not make PDF parsing safe for arbitrary anonymous uploads; use isolated parsing workers and further inspection before broadening that scope. Likewise, prompt instructions do not eliminate prompt injection. The graph's lack of external write tools reduces consequences but does not guarantee answer correctness.

## Add capabilities when the pilot demands them

Introduce a reranker or hybrid retrieval when evaluation shows the right passages are consistently missed. Add asynchronous ingestion and object storage when files or upload times exceed the current synchronous workflow. Add an identity provider and per-user ACLs when users need individual access. Add a durable approval mechanism before allowing an agent to send messages, edit systems, place orders or make payments. Add Langfuse or a similar tracing system when you need model-level diagnostics, with an explicit policy for what customer content it records.

These are engineering changes with tests and operating costs. They are not already implemented simply because LangGraph supports them.
