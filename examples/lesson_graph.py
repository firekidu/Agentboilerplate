"""Your first graph. No server, database, API key or paid model is required."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    answer: str


def answer(state: State):
    return {"answer": "You asked: " + state["question"]}


builder = StateGraph(State)
builder.add_node("answer", answer)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)
graph = builder.compile()
print(graph.invoke({"question": "How does a graph work?"}))
