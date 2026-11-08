import re
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import AgentState
from ..llm import get_llm


PLANNER_SYSTEM_PROMPT = """You are an Expert AI Systems Architect and Lead Data Engineer.
Your role is to break down a user's computational or data engineering request into 2 to 4 concise, executable steps.
Output each step on a new line prefixed with a number (e.g., '1. Step one').
Do not include conversational pleasantries."""


def parse_plan(text: str) -> List[str]:
    """Extracts numbered steps from LLM response."""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    steps = []
    for line in lines:
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        if cleaned:
            steps.append(cleaned)
    return steps if steps else [text.strip()]


def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    Planner Node:
    Deconstructs user task into an actionable sequence of execution steps.
    """
    llm = get_llm()
    task = state.get("task", "")

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=f"Decompose this task into sequential executable steps:\n{task}"),
    ]

    response = llm.invoke(messages)
    steps = parse_plan(response.content)

    return {
        "plan": steps,
        "current_step_index": 0,
        "iteration_count": 0,
        "status": "planning_completed",
        "messages": state.get("messages", []) + [{"role": "planner", "content": response.content}],
    }
