"""Small live acceptance smoke test. Upload examples/refund-policy.md to an empty test tenant first."""

import argparse
import getpass
import json
from pathlib import Path

import httpx

from app.models import ABSTENTION

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8000")
parser.add_argument("--cases", default="evals/cases.json")
args = parser.parse_args()
key = getpass.getpass("Test tenant READER API key: ")
cases = json.loads(Path(args.cases).read_text())
passed = 0
with httpx.Client(base_url=args.url, headers={"X-API-Key": key}, timeout=180) as client:
    for case in cases:
        response = client.post("/v1/chat", json={"question": case["question"]})
        response.raise_for_status()
        data = response.json()
        if data["mode"] == "fake":
            raise SystemExit("Use AI_BACKEND=openai: fake mode does not evaluate AI answer quality")
        ok = all(word.lower() in data["answer"].lower() for word in case.get("must_contain", []))
        ok = ok and (bool(data["sources"]) if case.get("must_cite") else True)
        ok = ok and (data["answer"] == ABSTENTION if case.get("must_abstain") else True)
        passed += int(ok)
        print(("PASS" if ok else "FAIL") + " " + case["question"])
print(
    f"{passed}/{len(cases)} smoke cases passed. Human review and a larger customer test set are still required."
)
raise SystemExit(0 if passed == len(cases) else 1)
