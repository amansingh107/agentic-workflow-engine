import re
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import AgentState
from ..llm import get_llm


CODER_SYSTEM_PROMPT = """You are a Senior Python Developer and ML Systems Engineer.
Write clean, robust, and self-contained Python code to accomplish the requested task or step.
Requirements:
1. Always wrap the complete runnable script inside a single ```python ... ``` markdown block.
2. Output results using print() statements so outputs can be captured.
3. If an error occurred in previous attempts, carefully analyze the traceback and fix the root cause.
4. Do not include external conversational filler."""


def extract_python_code(text: str) -> str:
    """Extracts code from markdown code block or returns clean text."""
    pattern = r"```(?:python)?\s*(.*?)\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def coder_node(state: AgentState) -> Dict[str, Any]:
    """
    Coder Node:
    Synthesizes executable Python code. In self-healing loops, analyzes error feedback
    from previous attempts to generate corrected code.
    """
    llm = get_llm()
    task = state.get("task", "")
    plan = state.get("plan", [])
    step_idx = state.get("current_step_index", 0)
    current_step = plan[step_idx] if step_idx < len(plan) else task
    error_feedback = state.get("error_feedback")

    prompt = f"Goal: {task}\nCurrent Step: {current_step}\n"
    if error_feedback:
        prompt += f"\nCRITICAL: Previous execution failed with the following traceback/feedback. Please fix the error:\n{error_feedback}\n"
    prompt += "\nWrite Python code to solve this step."

    messages = [
        SystemMessage(content=CODER_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    response = llm.invoke(messages)
    raw_content = response.content
    code = extract_python_code(raw_content)

    return {
        "code": code,
        "status": "code_generated",
        "messages": state.get("messages", []) + [{"role": "coder", "content": raw_content}],
    }
