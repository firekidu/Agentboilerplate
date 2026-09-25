"""Delete old chat checkpoints and expired request counters; does not delete documents."""

import argparse

from langgraph.checkpoint.postgres import PostgresSaver

from app.config import Settings
from app.store import PostgresStore

parser = argparse.ArgumentParser()
parser.add_argument("--days", type=int, default=30)
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
if args.days < 1:
    parser.error("Use at least one day")
settings = Settings()
store = PostgresStore(settings.database_url.get_secret_value())
saver = PostgresSaver(store.pool)
with store.pool.connection() as conn:
    rows = conn.execute(
        "SELECT tenant_id,thread_id FROM threads WHERE updated_at < now() - (%s * interval '1 day')",
        (args.days,),
    ).fetchall()
print(f"{len(rows)} conversations older than {args.days} days")
if args.apply:
    deleted = 0
    for row in rows:
        with store.tenant_lock(row["tenant_id"]):
            # Recheck under the lock in case the customer used this thread meanwhile.
            with store.pool.connection() as conn:
                expired = conn.execute(
                    "SELECT 1 FROM threads WHERE thread_id=%s AND updated_at < now() - (%s * interval '1 day')",
                    (row["thread_id"], args.days),
                ).fetchone()
            if expired:
                saver.delete_thread(row["thread_id"])
                store.remove_thread(row["tenant_id"], row["thread_id"])
                deleted += 1
    with store.pool.connection() as conn:
        conn.execute("DELETE FROM request_budgets WHERE expires_at < now()")
    print(f"Deleted {deleted} conversations and expired counters")
else:
    print("Dry run only. Add --apply to delete.")
store.close()
