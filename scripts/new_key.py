"""Print a new key and its hash record. Append the record to API_KEYS_JSON and restart API."""

import argparse
import hashlib
import json
import re
import secrets

parser = argparse.ArgumentParser()
parser.add_argument("tenant", help="Customer identifier, e.g. acme")
parser.add_argument("--role", choices=["admin", "reader"], default="reader")
args = parser.parse_args()
if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", args.tenant):
    parser.error("Use 1-48 lower-case letters, digits, underscores or hyphens")
key = secrets.token_urlsafe(36)
print("Save this key in your password manager:", key)
print("Append this record to the existing API_KEYS_JSON list in .env:")
print(
    json.dumps(
        {
            "sha256": hashlib.sha256(key.encode()).hexdigest(),
            "tenant_id": args.tenant,
            "role": args.role,
        }
    )
)
