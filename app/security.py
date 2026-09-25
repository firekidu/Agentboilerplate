import hashlib
import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    role: str


def authenticate(request: Request, key: str | None = Depends(header)) -> Principal:
    if key is None or len(key) < 32:
        raise HTTPException(401, "Missing or invalid API key")
    digest = hashlib.sha256((key or "").encode()).hexdigest()
    for record in request.app.state.runtime.settings.api_keys_json:
        if hmac.compare_digest(digest, record.sha256):
            return Principal(record.tenant_id, record.role)
    raise HTTPException(401, "Missing or invalid API key")


def require_admin(principal: Principal = Depends(authenticate)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(403, "An admin key is required for document changes")
    return principal


def internal_thread(tenant: str, collection: str, public_id: str) -> str:
    # The client can choose a UUID, but never the tenant portion of the namespace.
    return hashlib.sha256(f"{tenant}:{collection}:{public_id}".encode()).hexdigest()
