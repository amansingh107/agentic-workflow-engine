from typing import Literal, Optional, Any
from langgraph.graph import StateGraph, START, END
from .state import AgentState
from .nodes import (
    planner_node,
    coder_node,
    guardrail_node,
    approval_gate_node,
    sandbox_node,
    critic_node,
)
from ..persistence.checkpointer import get_checkpointer


def route_after_approval(state: AgentState) -> Literal["sandbox", "coder", "end_rejected"]:
    """
    Routes execution after Human-in-the-Loop review:
    - If approved -> sandbox
    - If rejected with feedback -> coder (for correction)
    - If rejected without feedback -> end_rejected
    """
    is_approved = state.get("is_approved", False)
    status = state.get("status", "")

    if is_approved:
        return "sandbox"
    elif status == "rejected_by_human" and state.get("error_feedback"):
        return "coder"
    return "end_rejected"


def route_critic(state: AgentState) -> Literal["coder", "end"]:
    """
    Controls the cyclic feedback loop based on execution telemetry:
    - If execution failed and retries remain -> loop back to Coder with traceback.
    - If step succeeded and more steps remain -> proceed to Coder with next step.
    - If completed or max retries exceeded -> terminate at END.
    """
    status = state.get("status", "")
    if status in ["retrying_code", "step_succeeded"]:
        return "coder"
    return "end"


def build_workflow_graph(checkpointer: Optional[Any] = None):
    """
    Constructs and compiles the cyclic multi-agent StateGraph with
    PostgreSQL/Memory checkpointing and Human-in-the-Loop approval gates.
    """
    if checkpointer is None:
        checkpointer = get_checkpointer()

    workflow = StateGraph(AgentState)

    # Register Nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("approval_gate", approval_gate_node)
    workflow.add_node("sandbox", sandbox_node)
    workflow.add_node("critic", critic_node)

    # Build Edges
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "coder")
    workflow.add_edge("coder", "guardrail")
    workflow.add_edge("guardrail", "approval_gate")

    # Dynamic routing after approval gate
    workflow.add_conditional_edges(
        "approval_gate",
        route_after_approval,
        {
            "sandbox": "sandbox",
            "coder": "coder",
            "end_rejected": END,
        },
    )

    workflow.add_edge("sandbox", "critic")

    # Dynamic routing after critic evaluation (Cyclic loop)
    workflow.add_conditional_edges(
        "critic",
        route_critic,
        {
            "coder": "coder",  # Cyclic self-healing edge
            "end": END,
        },
    )

    return workflow.compile(checkpointer=checkpointer)
