from uuid import uuid4

from app.models import ABSTENTION
from app.security import internal_thread
from tests.conftest import KEY_A, KEY_B, KEY_READER


def upload(
    client,
    text="Refunds are available within 30 days of delivery.",
    key=KEY_A,
    filename="policy.md",
):
    return client.post(
        "/v1/documents", headers={"X-API-Key": key}, files={"file": (filename, text.encode())}
    )


def ask(client, question="What is the refund period?", key=KEY_A, thread_id=None):
    return client.post(
        "/v1/chat", headers={"X-API-Key": key}, json={"question": question, "thread_id": thread_id}
    )


def test_upload_retrieve_citation(client):
    document = upload(client)
    assert document.status_code == 200, document.text
    response = ask(client)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "30 days" in data["answer"]
    assert "[1]" in data["answer"]
    assert data["sources"][0]["document_id"] == document.json()["document_id"]


def test_no_document_abstains_without_llm(client, runtime):
    runtime.ai.answer = lambda *args: (_ for _ in ()).throw(AssertionError("Must not call model"))
    assert ask(client).json()["answer"] == ABSTENTION


def test_tenant_isolation_and_thread_namespace(client, runtime):
    upload(client)
    shared_uuid = str(uuid4())
    a = ask(client, thread_id=shared_uuid).json()
    b = ask(client, key=KEY_B, thread_id=shared_uuid).json()
    assert a["sources"] and not b["sources"]
    assert b["answer"] == ABSTENTION
    assert client.get("/v1/documents", headers={"X-API-Key": KEY_B}).json() == []
    assert runtime.store.threads("a") != runtime.store.threads("b")


def test_cannot_spoof_tenant(client):
    response = client.post(
        "/v1/chat", headers={"X-API-Key": KEY_B}, json={"question": "Refund?", "tenant_id": "a"}
    )
    assert response.status_code == 422


def test_auth_and_reader_permissions(client):
    assert client.get("/v1/documents").status_code == 401
    assert upload(client, key=KEY_READER).status_code == 403
    doc = upload(client).json()
    assert (
        client.delete(
            f"/v1/documents/{doc['document_id']}", headers={"X-API-Key": KEY_READER}
        ).status_code
        == 403
    )
    assert ask(client, key=KEY_READER).status_code == 200


def test_duplicate_upload_does_not_embed_again(client, runtime):
    first = upload(client).json()
    runtime.ai.embed = lambda *args: (_ for _ in ()).throw(AssertionError("duplicate re-embedded"))
    again = upload(client).json()
    assert first["document_id"] == again["document_id"]
    assert again["duplicate"] is True


def test_other_tenant_cannot_delete(client):
    doc = upload(client).json()
    assert (
        client.delete(
            f"/v1/documents/{doc['document_id']}", headers={"X-API-Key": KEY_B}
        ).status_code
        == 404
    )
    assert ask(client).json()["sources"]


def test_delete_removes_vectors_and_all_tenant_checkpoints(client, runtime):
    doc = upload(client).json()
    thread_id = ask(client).json()["thread_id"]
    internal = internal_thread("a", runtime.vectors.collection, thread_id)
    assert runtime.checkpointer.get_tuple({"configurable": {"thread_id": internal}})
    assert (
        client.delete(
            f"/v1/documents/{doc['document_id']}", headers={"X-API-Key": KEY_A}
        ).status_code
        == 204
    )
    assert runtime.checkpointer.get_tuple({"configurable": {"thread_id": internal}}) is None
    assert ask(client, thread_id=thread_id).json()["answer"] == ABSTENTION
    assert runtime.vectors.client.count(runtime.vectors.collection).count == 0


def test_failed_ingestion_not_retrievable_and_retry_recovers(client, runtime):
    original = runtime.vectors.insert

    def partial_then_fail(*args):
        original(*args)
        raise RuntimeError("simulated worker crash after vector write")

    runtime.vectors.insert = partial_then_fail
    assert upload(client).status_code == 503
    assert ask(client).json()["answer"] == ABSTENTION
    runtime.vectors.insert = original
    assert upload(client).status_code == 200
    assert ask(client).json()["sources"]


def test_fabricated_citation_is_rejected(client, runtime):
    upload(client)
    runtime.ai.answer = lambda *args: ("Refunds take 200 days [999]", {})
    assert ask(client).json()["answer"] == ABSTENTION


def test_chat_quota_is_per_tenant(client, runtime):
    runtime.settings.chat_per_minute = 1
    assert ask(client).status_code == 200
    assert ask(client).status_code == 429
    assert ask(client, key=KEY_B).status_code == 200


def test_thread_history_is_bounded_and_deleted(client, runtime):
    runtime.settings.history_turns = 2
    upload(client)
    thread = str(uuid4())
    for _ in range(4):
        assert ask(client, thread_id=thread).status_code == 200
    internal = internal_thread("a", runtime.vectors.collection, thread)
    state = runtime.graph.get_state({"configurable": {"thread_id": internal}}).values
    assert len(state["history"]) == 2
    assert client.delete(f"/v1/threads/{thread}", headers={"X-API-Key": KEY_A}).status_code == 204
    assert runtime.checkpointer.get_tuple({"configurable": {"thread_id": internal}}) is None


def test_pdf_and_file_validation(client):
    assert upload(client, filename="malware.exe").status_code == 422
    assert upload(client, filename="pretend.pdf").status_code == 422
    assert upload(client, text="").status_code == 422
    assert ask(client, question="   ").status_code == 422


def test_large_body_is_rejected_before_parsing(client):
    response = client.post(
        "/v1/chat",
        headers={"X-API-Key": KEY_A, "Content-Type": "application/json"},
        content=b"x" * 20000,
    )
    assert response.status_code == 413


def test_tenant_busy_returns_conflict(client, runtime):
    with runtime.store.tenant_lock("a"):
        assert ask(client).status_code == 409


def test_metrics_not_exposed_with_tenant_key(client):
    assert client.get("/metrics", headers={"X-API-Key": KEY_A}).status_code == 401
    assert client.get("/metrics", headers={"X-Metrics-Key": "m" * 40}).status_code == 200


def test_browser_workspace_and_readiness(client):
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/health/ready").json()["mode"] == "fake"


def test_pdf_page_citation(client):
    # Small, valid text PDF with no external fixtures or network calls.
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 500 700] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = b"BT /F1 12 Tf 40 600 Td (Refund period is 30 days.) Tj ET"
    objects += [
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets:
        data += f"{offset:010d} 00000 n \n".encode()
    data += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    response = client.post(
        "/v1/documents", headers={"X-API-Key": KEY_A}, files={"file": ("refund.pdf", data)}
    )
    assert response.status_code == 200, response.text
    assert ask(client).json()["sources"][0]["page"] == 1
