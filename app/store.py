import hashlib
import threading
import time
from contextlib import contextmanager

from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_versions (version integer PRIMARY KEY);
INSERT INTO schema_versions VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS documents (
  tenant_id text NOT NULL, collection text NOT NULL, document_id text NOT NULL,
  filename text NOT NULL, status text NOT NULL, chunks integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, collection, document_id)
);
CREATE TABLE IF NOT EXISTS threads (
  tenant_id text NOT NULL, thread_id text PRIMARY KEY,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS threads_tenant ON threads(tenant_id);
CREATE TABLE IF NOT EXISTS request_budgets (
  tenant_id text NOT NULL, scope text NOT NULL, bucket bigint NOT NULL,
  used integer NOT NULL, expires_at timestamptz NOT NULL,
  PRIMARY KEY (tenant_id, scope, bucket)
);
"""


class PostgresStore:
    def __init__(self, url: str):
        self.pool = ConnectionPool(
            url,
            min_size=2,
            max_size=10,
            timeout=5,
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
        )
        self.pool.wait(timeout=20)

    def setup(self):
        with self.pool.connection() as conn:
            conn.execute(SCHEMA, prepare=False)

    @contextmanager
    def tenant_lock(self, tenant: str):
        # Nonblocking PostgreSQL advisory locks also work across API processes.
        lock_id = int.from_bytes(hashlib.sha256(tenant.encode()).digest()[:8], "big", signed=True)
        with self.pool.connection() as conn:
            acquired = conn.execute("SELECT pg_try_advisory_lock(%s) AS ok", (lock_id,)).fetchone()
            if not acquired["ok"]:
                raise HTTPException(
                    409, "Another operation is running for this customer; retry shortly"
                )
            try:
                yield
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))

    def consume(self, tenant: str, scope: str, limit: int, seconds: int):
        bucket = int(time.time()) // seconds
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO request_budgets VALUES (%s,%s,%s,1,to_timestamp(%s))
                ON CONFLICT (tenant_id,scope,bucket) DO UPDATE
                SET used=request_budgets.used+1 RETURNING used
            """,
                (tenant, scope, bucket, (bucket + 2) * seconds),
            ).fetchone()
        if row["used"] > limit:
            raise HTTPException(
                429,
                "Request allowance reached; try in the next quota window",
                headers={"Retry-After": str(seconds - int(time.time()) % seconds)},
            )

    def documents(self, tenant: str, collection: str) -> list[dict]:
        with self.pool.connection() as conn:
            return conn.execute(
                """SELECT document_id,filename,status,chunks FROM documents
                WHERE tenant_id=%s AND collection=%s ORDER BY created_at,document_id""",
                (tenant, collection),
            ).fetchall()

    def save_document(self, tenant: str, collection: str, doc: dict):
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO documents
                (tenant_id,collection,document_id,filename,status,chunks) VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_id,collection,document_id) DO UPDATE SET
                status=EXCLUDED.status,chunks=EXCLUDED.chunks""",
                (
                    tenant,
                    collection,
                    doc["document_id"],
                    doc["filename"],
                    doc["status"],
                    doc["chunks"],
                ),
            )

    def remove_document(self, tenant: str, collection: str, document_id: str):
        with self.pool.connection() as conn:
            conn.execute(
                "DELETE FROM documents WHERE tenant_id=%s AND collection=%s AND document_id=%s",
                (tenant, collection, document_id),
            )

    def register_thread(self, tenant: str, thread: str):
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO threads (tenant_id,thread_id) VALUES (%s,%s)
                ON CONFLICT (thread_id) DO UPDATE SET updated_at=now()""",
                (tenant, thread),
            )

    def threads(self, tenant: str) -> list[str]:
        with self.pool.connection() as conn:
            return [
                r["thread_id"]
                for r in conn.execute(
                    "SELECT thread_id FROM threads WHERE tenant_id=%s", (tenant,)
                ).fetchall()
            ]

    def remove_thread(self, tenant: str, thread: str):
        with self.pool.connection() as conn:
            conn.execute(
                "DELETE FROM threads WHERE tenant_id=%s AND thread_id=%s", (tenant, thread)
            )

    def healthy(self):
        with self.pool.connection() as conn:
            conn.execute("SELECT 1")

    def close(self):
        self.pool.close()


class MemoryStore:
    """Tests only. The shipped Docker app ALWAYS uses PostgreSQL, even in fake AI mode."""

    def __init__(self):
        self.docs = {}
        self.thread_rows = {}
        self.budgets = {}
        self.locks = {}
        self.guard = threading.Lock()

    def setup(self):
        pass

    @contextmanager
    def tenant_lock(self, tenant):
        with self.guard:
            lock = self.locks.setdefault(tenant, threading.Lock())
        if not lock.acquire(blocking=False):
            raise HTTPException(
                409, "Another operation is running for this customer; retry shortly"
            )
        try:
            yield
        finally:
            lock.release()

    def consume(self, tenant, scope, limit, seconds):
        key = (tenant, scope, int(time.time()) // seconds)
        with self.guard:
            self.budgets[key] = self.budgets.get(key, 0) + 1
            if self.budgets[key] > limit:
                raise HTTPException(429, "Request allowance reached")

    def documents(self, tenant, collection):
        return [
            dict(doc) for (t, c, _), doc in self.docs.items() if t == tenant and c == collection
        ]

    def save_document(self, tenant, collection, doc):
        self.docs[(tenant, collection, doc["document_id"])] = dict(doc)

    def remove_document(self, tenant, collection, document_id):
        self.docs.pop((tenant, collection, document_id), None)

    def register_thread(self, tenant, thread):
        self.thread_rows[thread] = tenant

    def threads(self, tenant):
        return [key for key, value in self.thread_rows.items() if value == tenant]

    def remove_thread(self, tenant, thread):
        if self.thread_rows.get(thread) == tenant:
            self.thread_rows.pop(thread, None)

    def healthy(self):
        pass

    def close(self):
        pass
