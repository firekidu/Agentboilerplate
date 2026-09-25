"""Run inside a one-off API container while the API service is stopped."""

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
folder = Path(args.directory)
folder.mkdir(parents=True, exist_ok=True)
settings = Settings()
url = settings.qdrant_url.rstrip("/")
key = settings.qdrant_api_key.get_secret_value()
client = QdrantClient(url=url, api_key=key, timeout=300, check_compatibility=False)
records = []
with httpx.Client(headers={"api-key": key}, timeout=300) as http:
    for collection in client.get_collections().collections:
        # This instance is dedicated to this repository. Back up all embedding versions.
        snapshot = client.create_snapshot(collection.name)
        path = folder / (collection.name + ".snapshot")
        endpoint = f"{url}/collections/{quote(collection.name, safe='')}/snapshots/{quote(snapshot.name, safe='')}"
        hasher = hashlib.sha256()
        with http.stream("GET", endpoint) as response:
            response.raise_for_status()
            with path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    hasher.update(chunk)
                    handle.write(chunk)
        records.append(
            {"collection": collection.name, "file": path.name, "sha256": hasher.hexdigest()}
        )
        client.delete_snapshot(collection.name, snapshot.name)
(folder / "qdrant-manifest.json").write_text(json.dumps(records, indent=2))
client.close()
print(f"Saved {len(records)} collection snapshots")
