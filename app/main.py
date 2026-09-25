import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from app.config import Settings
from app.runtime import Runtime, create_runtime
from app.schemas import ChatRequest, ChatResponse, DocumentResponse
from app.security import Principal, authenticate, internal_thread, require_admin

logger = logging.getLogger("nimble")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False
STATIC = Path(__file__).parent / "static"


class RequestGuard:
    """Cap the body before multipart parsing; never log body, query string or credentials."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = scope["app"].state.runtime.settings.max_file_bytes + 65536
        if scope["path"] == "/v1/chat":
            limit = 16384
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                return await JSONResponse({"detail": "Request body too large"}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(injected: Runtime | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        runtime = injected or create_runtime(Settings())
        application.state.runtime = runtime
        try:
            yield
        finally:
            if injected is None:
                runtime.close()

    application = FastAPI(title="Nimble RAG Agent", version="0.1.0", lifespan=lifespan)
    registry = CollectorRegistry()
    requests = Counter("rag_requests_total", "API requests", ["route", "status"], registry=registry)
    latency = Histogram("rag_request_seconds", "API request duration", ["route"], registry=registry)
    tokens = Counter(
        "rag_answer_tokens_total",
        "Answer generation tokens only, not a billing meter",
        registry=registry,
    )
    application.add_middleware(RequestGuard)

    @application.middleware("http")
    async def observe(request, call_next):
        request_id = str(uuid4())
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Provider exception strings can contain private text. Log type, never str(exc).
            logger.error(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request_id,
                        "error_type": type(exc).__name__,
                    }
                )
            )
            response = JSONResponse(
                {
                    "detail": "A dependency failed; retry or contact the operator",
                    "request_id": request_id,
                },
                status_code=503,
            )
        route = getattr(request.scope.get("route"), "path", "other")
        elapsed = time.monotonic() - start
        requests.labels(route, str(response.status_code)).inc()
        latency.labels(route).observe(elapsed)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path == "/":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; frame-ancestors 'none'; base-uri 'none'"
            )
        logger.info(
            json.dumps(
                {
                    "event": "request_complete",
                    "request_id": request_id,
                    "route": route,
                    "status": response.status_code,
                    "milliseconds": round(elapsed * 1000),
                }
            )
        )
        return response

    def runtime(request: Request) -> Runtime:
        return request.app.state.runtime

    @application.get("/health/live")
    def live():
        return {"status": "alive"}

    @application.get("/health/ready")
    def ready(rt: Runtime = Depends(runtime)):
        rt.store.healthy()
        rt.vectors.healthy()
        return {"status": "ready", "mode": rt.settings.ai_backend}

    @application.get("/metrics", include_in_schema=False)
    def metrics(request: Request, rt: Runtime = Depends(runtime)):
        key = request.headers.get("X-Metrics-Key", "")
        if not hmac.compare_digest(key, rt.settings.metrics_key.get_secret_value()):
            raise HTTPException(401, "Missing or invalid metrics key")
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    @application.get("/v1/documents", response_model=list[DocumentResponse])
    def documents(principal: Principal = Depends(authenticate), rt: Runtime = Depends(runtime)):
        rt.store.consume(principal.tenant_id, "list-minute", 60, 60)
        return rt.store.documents(principal.tenant_id, rt.vectors.collection)

    @application.post("/v1/documents", response_model=DocumentResponse)
    def upload(
        file: UploadFile,
        principal: Principal = Depends(require_admin),
        rt: Runtime = Depends(runtime),
    ):
        rt.store.consume(principal.tenant_id, "upload-day", rt.settings.uploads_per_day, 86400)
        try:
            data = file.file.read(rt.settings.max_file_bytes + 1)
            return rt.ingest(principal.tenant_id, file.filename or "document.txt", data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            file.file.close()

    @application.delete("/v1/documents/{document_id}", status_code=204)
    def delete_document(
        document_id: UUID,
        principal: Principal = Depends(require_admin),
        rt: Runtime = Depends(runtime),
    ):
        rt.store.consume(principal.tenant_id, "delete-minute", 20, 60)
        rt.delete_document(principal.tenant_id, str(document_id))
        return Response(status_code=204)

    @application.post("/v1/chat", response_model=ChatResponse)
    def chat(
        body: ChatRequest,
        principal: Principal = Depends(authenticate),
        rt: Runtime = Depends(runtime),
    ):
        if not body.question.strip():
            raise HTTPException(422, "Question cannot be blank")
        rt.store.consume(principal.tenant_id, "chat-minute", rt.settings.chat_per_minute, 60)
        rt.store.consume(principal.tenant_id, "chat-day", rt.settings.chat_per_day, 86400)
        public_id = body.thread_id or uuid4()
        thread = internal_thread(principal.tenant_id, rt.vectors.collection, str(public_id))
        with rt.store.tenant_lock(principal.tenant_id):
            rt.store.register_thread(principal.tenant_id, thread)
            result = rt.graph.invoke(
                {"question": body.question.strip(), "tenant_id": principal.tenant_id},
                {"configurable": {"thread_id": thread}, "recursion_limit": 10},
            )
        tokens.inc(result.get("usage", {}).get("total_tokens", 0))
        return ChatResponse(
            thread_id=public_id,
            answer=result["answer"],
            sources=result["sources"],
            mode=rt.settings.ai_backend,
        )

    @application.delete("/v1/threads/{thread_id}", status_code=204)
    def delete_thread(
        thread_id: UUID,
        principal: Principal = Depends(authenticate),
        rt: Runtime = Depends(runtime),
    ):
        rt.store.consume(principal.tenant_id, "delete-minute", 20, 60)
        thread = internal_thread(principal.tenant_id, rt.vectors.collection, str(thread_id))
        with rt.store.tenant_lock(principal.tenant_id):
            rt.checkpointer.delete_thread(thread)
            rt.store.remove_thread(principal.tenant_id, thread)
        return Response(status_code=204)

    @application.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    application.mount("/assets", StaticFiles(directory=STATIC), name="assets")
    return application


app = create_app()
