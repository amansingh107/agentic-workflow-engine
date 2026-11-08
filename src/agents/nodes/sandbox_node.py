from typing import Dict, Any
from ..state import AgentState
from ...sandbox.factory import get_sandbox


def sandbox_node(state: AgentState) -> Dict[str, Any]:
    """
    Sandbox Node:
    Executes generated code in the isolated execution environment (Docker or local sandbox)
    and records full execution telemetry in state.
    """
    code = state.get("code", "")
    sandbox = get_sandbox()

    # Execute inside isolated sandbox
    res = sandbox.execute(code)

    return {
        "execution_result": res.model_dump(),
        "status": "executed",
    }
