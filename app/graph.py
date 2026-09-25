import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.models import ABSTENTION


class AgentState(TypedDict, total=False):
    tenant_id: str
    question: str
    search_query: str
    passages: list[dict]
    answer: str
    sources: list[dict]
    history: list[dict]
    usage: dict


def build_graph(ai, vectors, store, settings, checkpointer):
    def rewrite(state):
        return {
            "search_query": ai.rewrite(state["question"], state.get("history", [])),
            "passages": [],
            "sources": [],
            "answer": "",
            "usage": {},
        }

    def retrieve(state):
        ready = [
            d["document_id"]
            for d in store.documents(state["tenant_id"], vectors.collection)
            if d["status"] == "ready"
        ]
        # Do not call the embedding provider when the customer has no ready documents.
        passages = (
            vectors.search(state["tenant_id"], ai.embed([state["search_query"]])[0], ready)
            if ready
            else []
        )
        return {"passages": passages}

    def generate(state):
        # Only these passages are supplied. Past answers may be outdated after a document edit.
        answer, usage = ai.answer(state["search_query"], state["passages"])
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        allowed = {p["citation"] for p in state["passages"]}
        if answer.strip() == ABSTENTION or not cited or not cited.issubset(allowed):
            return {"answer": ABSTENTION, "sources": [], "usage": usage}
        sources = [
            {
                "citation": p["citation"],
                "document_id": p["document_id"],
                "filename": p["filename"],
                "page": p.get("page"),
                "chunk": p["chunk"],
                "score": round(p["score"], 4),
                "excerpt": p["text"][:500],
            }
            for p in state["passages"]
            if p["citation"] in cited
        ]
        return {"answer": answer, "sources": sources, "usage": usage}

    def abstain(state):
        return {"answer": ABSTENTION, "sources": [], "usage": {}}

    def remember(state):
        history = state.get("history", []) + [
            {"question": state["question"], "answer": state["answer"][:2400]}
        ]
        return {
            "history": history[-settings.history_turns :] if settings.history_turns else [],
            "passages": [],
        }

    graph = StateGraph(AgentState)
    for name, node in [
        ("rewrite", rewrite),
        ("retrieve", retrieve),
        ("generate", generate),
        ("abstain", abstain),
        ("remember", remember),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "rewrite")
    graph.add_edge("rewrite", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        lambda state: "generate" if state["passages"] else "abstain",
        {"generate": "generate", "abstain": "abstain"},
    )
    graph.add_edge("generate", "remember")
    graph.add_edge("abstain", "remember")
    graph.add_edge("remember", END)
    return graph.compile(checkpointer=checkpointer)
