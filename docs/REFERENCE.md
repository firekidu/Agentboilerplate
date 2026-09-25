# Relationship to the reference project

Reference: https://github.com/wassim249/fastapi-langgraph-agent-production-ready-template

Reviewed on 24 September 2026 at commit `36c7e2b87bc2e60ee230348e857e6c9d9570a46e`.

The reference targets experienced developers. This repository implements a smaller system so a beginner can trace a request from the browser through FastAPI, LangGraph, Qdrant and PostgreSQL. The original repository has not been changed. This is not a fork, and it does not claim feature parity.

| Reference component | This repository | Reason |
|---|---|---|
| FastAPI service | FastAPI service and a small browser workspace | Make the API visible while learning |
| LangGraph agent | Explicit bounded RAG graph | Make retrieval and evidence handling easy to follow |
| PostgreSQL checkpointing | PostgreSQL checkpointing | Preserve conversations across restarts |
| mem0 and pgvector long-term memory | Qdrant document retrieval; no automatic personal memory | Documents and personal memories have different lifecycle rules |
| JWT users and sessions | Hashed, tenant-scoped admin and reader API keys | Smaller B2B integration surface; add OIDC before a public account portal |
| Async database/ORM and Alembic | Synchronous pooled SQL and version-one schema initialization | Fewer abstractions; add explicit migration files before changing schema |
| Valkey and fallback models | Omitted | Introduce only when measurements justify them |
| Langfuse, Prometheus, Grafana | JSON logs and protected Prometheus endpoint | Avoid deploying several observability databases on day one |
| Multiple tools and human approval patterns | No write tools; separate teaching example | Document answers are the first scope |

This project contains new application code. The reference's MIT license notice is retained in `LICENSE.reference` for attribution. Reusing upstream code in future requires preserving its notices. Provider agreements, document permissions and third-party dependency licences remain separate obligations.
