"""Restore into an empty, isolated Qdrant instance. Never overwrites a collection."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import httpx
from qdrant_client import QdrantClient

from app.config import Settings

parser = argparse.ArgumentParser()
parser.add_argument("directory")
args = parser.parse_args()
folder = Path(args.directory).resolve()
settings = Settings()
url = settings.qdrant_url.rstrip("/")
key = settings.qdrant_api_key.get_secret_value()
client = QdrantClient(url=url, api_key=key, timeout=300, check_compatibility=False)
if client.get_collections().collections:
    raise SystemExit("Refusing restore: target Qdrant is not empty. Use a new recovery host.")
records = json.loads((folder / "qdrant-manifest.json").read_text())
for record in records:
    path = (folder / record["file"]).resolve()
    if path.parent != folder:
        raise SystemExit("Invalid snapshot path")
    with path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != record["sha256"]:
            raise SystemExit("Snapshot checksum mismatch")
with httpx.Client(headers={"api-key": key}, timeout=300) as http:
    for record in records:
        with (folder / record["file"]).open("rb") as handle:
            response = http.post(
                f"{url}/collections/{quote(record['collection'], safe='')}/snapshots/upload",
                params={"priority": "snapshot"},
                files={"snapshot": (record["file"], handle)},
            )
            response.raise_for_status()
client.close()
print(f"Restored {len(records)} collections. Restore PostgreSQL from the SAME backup set.")
