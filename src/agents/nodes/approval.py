from typing import Dict, Any
from langgraph.types import interrupt
from ..state import AgentState


def approval_gate_node(state: AgentState) -> Dict[str, Any]:
    """
    Human-in-the-Loop Approval Gate:
    If elevated risk or dangerous operation was flagged, suspends graph execution
    using LangGraph interrupt() and yields control back to caller/API.
    Resumes seamlessly when human approval/rejection command is provided.
    """
    requires_approval = state.get("requires_approval", False)
    is_approved = state.get("is_approved", False)

    if requires_approval and not is_approved:
        # Pause thread and persist checkpoint in checkpointer (PostgreSQL/Memory)
        decision = interrupt({
            "action": "APPROVAL_REQUIRED",
            "task": state.get("task"),
            "code": state.get("code"),
            "risk_score": state.get("risk_score"),
            "risk_reasons": state.get("risk_reasons"),
            "message": "Elevated security risk or sensitive operation detected. Human approval required.",
        })

        # Process human reviewer's resume decision
        if isinstance(decision, dict):
            approved = decision.get("approved", False)
            feedback = decision.get("feedback")
            modified_code = decision.get("modified_code")
        else:
            approved = bool(decision)
            feedback = None
            modified_code = None

        updates: Dict[str, Any] = {
            "is_approved": approved,
            "requires_approval": False,  # Evaluated
            "status": "approved_by_human" if approved else "rejected_by_human",
        }

        if modified_code:
            updates["code"] = modified_code
        if not approved and feedback:
            updates["error_feedback"] = f"Human reviewer rejected code: {feedback}"

        return updates

    return {
        "is_approved": True,
        "status": "auto_approved",
    }
