# Security and scope

This version is a learning and commercial-pilot starter. Use trusted admin uploads and non-sensitive data until you complete a deployment review. It has no independent security audit.

Implemented controls include tenant identity derived from hashed keys, tenant filters on Qdrant retrieval and deletion, ready-document filtering, namespaced checkpoints, admin/reader roles, request quotas, body limits, a non-superuser application database role, a non-root API container, private database ports and an HTTPS proxy configuration. No write-capable model tools are exposed.

Known limitations include synchronous PDF parsing, no individual user ACLs, no durable audit event ledger, no automatic monetary budget enforcement, no infrastructure high availability, no built-in model content tracing, no automatic dependency scan and a version-one startup schema rather than a general migration system. A document can contain adversarial instructions; prompts and valid citation numbers do not prove that the answer is correct.

Report suspected vulnerabilities privately to the repository owner using an agreed private channel. Do not include raw credentials, customer documents or a public proof containing private data. Rotate any exposed key and preserve the minimum information needed to investigate.
