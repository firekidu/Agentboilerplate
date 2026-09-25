"""Run with plain Python 3, before Docker. Refuses to overwrite existing credentials."""

import hashlib
import json
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(".env already exists. Edit it; setup never overwrites it.")
admin = secrets.token_urlsafe(36)
reader = secrets.token_urlsafe(36)
password = secrets.token_hex(24)
admin_password = secrets.token_hex(24)
records = [
    {"sha256": hashlib.sha256(key.encode()).hexdigest(), "tenant_id": "demo", "role": role}
    for key, role in [(admin, "admin"), (reader, "reader")]
]
values = {
    "ENVIRONMENT": "development",
    "AI_BACKEND": "fake",
    "OPENAI_API_KEY": "",
    "CHAT_MODEL": "gpt-4.1-mini",
    "EMBEDDING_MODEL": "text-embedding-3-small",
    "EMBEDDING_DIMENSIONS": "1536",
    "POSTGRES_PASSWORD": admin_password,
    "APP_DB_PASSWORD": password,
    "DATABASE_URL": f"postgresql://rag:{password}@postgres:5432/rag",
    "QDRANT_URL": "http://qdrant:6333",
    "QDRANT_API_KEY": secrets.token_urlsafe(36),
    "QDRANT_COLLECTION": "knowledge",
    "API_KEYS_JSON": "'" + json.dumps(records, separators=(",", ":")) + "'",
    "METRICS_KEY": secrets.token_urlsafe(36),
    "DOMAIN": "agent.example.com",
    "ACME_EMAIL": "you@example.com",
    "SCORE_THRESHOLD": "0.30",
}
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as handle:
    handle.write("# Keep this file private. Never commit it to Git.\n")
    handle.writelines(f"{key}={value}\n" for key, value in values.items())
print("Created .env. Save these API keys in your password manager; the app stores only hashes.")
print("ADMIN KEY (upload, delete and chat):", admin)
print("READER KEY (chat and read only):", reader)
print("Next: docker compose up -d --build")
