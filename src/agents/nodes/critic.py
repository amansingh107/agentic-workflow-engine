from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import AgentState
from ..llm import get_llm


CRITIC_SYSTEM_PROMPT = """You are a Principal Software Quality Engineer and Lead Evaluator.
Review the code and its execution result (stdout and stderr).
Assess whether the goal was met or if runtime errors, timeouts, or logic defects occurred.
Provide a concise, direct analysis."""


def critic_node(state: AgentState) -> Dict[str, Any]:
    """
    Critic / Evaluator Node:
    Inspects stdout, stderr, and exit codes from the sandbox execution.
    Controls the self-healing cyclic feedback loop.
    """
    exec_res = state.get("execution_result") or {}
    is_success = exec_res.get("is_success", False)
    stderr = exec_res.get("stderr", "")
    stdout = exec_res.get("stdout", "")
    current_iter = state.get("iteration_count", 0)
    max_iters = state.get("max_iterations", 3)
    plan = state.get("plan", [])
    step_idx = state.get("current_step_index", 0)

    # 1. Execution Failure (Crash, Syntax Error, Timeout, Memory Exhaustion)
    if not is_success:
        new_iter = current_iter + 1
        feedback = f"Execution Failed.\nStderr / Traceback:\n{stderr}\nStdout:\n{stdout}"
        
        if new_iter >= max_iters:
            return {
                "iteration_count": new_iter,
                "error_feedback": feedback,
                "status": "failed",
                "final_summary": f"Workflow failed after exceeding max retry iterations ({max_iters}). Last error: {stderr}",
            }
        
        return {
            "iteration_count": new_iter,
            "error_feedback": feedback,
            "status": "retrying_code",
        }

    # 2. Execution Succeeded
    next_step_idx = step_idx + 1
    has_more_steps = next_step_idx < len(plan)

    if has_more_steps:
        return {
            "current_step_index": next_step_idx,
            "error_feedback": None,
            "status": "step_succeeded",
        }
    else:
        # All steps completed!
        summary = f"All plan steps executed successfully.\nFinal Output:\n{stdout}"
        return {
            "error_feedback": None,
            "status": "completed",
            "final_summary": summary,
        }
