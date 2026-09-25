"""Optional paid lesson: a genuine model-selected tool loop, separate from the RAG API."""

import os

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition


@tool
def minutes_to_seconds(minutes: float) -> float:
    """Convert a duration in minutes into seconds. Accept values from 0 to 100000."""
    if not 0 <= minutes <= 100000:
        raise ValueError("Minutes must be between 0 and 100000")
    return minutes * 60


tools = [minutes_to_seconds]
model = ChatOpenAI(
    model=os.environ.get("CHAT_MODEL", "gpt-4.1-mini"), max_tokens=300, timeout=45, max_retries=1
).bind_tools(tools)


def agent(state: MessagesState):
    return {"messages": [model.invoke(state["messages"])]}


builder = StateGraph(MessagesState)
builder.add_node("agent", agent)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
builder.add_edge("tools", "agent")
result = builder.compile().invoke(
    {"messages": [HumanMessage(content="Use the tool to convert 12.5 minutes into seconds.")]},
    {"recursion_limit": 8},
)
print(result["messages"][-1].content)
