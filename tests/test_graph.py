import pytest
from src.agents.state import AgentState
from src.agents.nodes.guardrail import analyze_code_safety, guardrail_node
from src.agents.nodes.planner import parse_plan
from src.agents.nodes.coder import extract_python_code
from src.agents.graph import build_workflow_graph


def test_guardrail_ast_security_analysis():
    """Verifies that malicious or sensitive system calls are caught by AST analyzer."""
    # 1. Safe code
    safe_code = """
import math
def compute(x):
    return math.sqrt(x) * 2
print(compute(16))
"""
    risk_score, reasons = analyze_code_safety(safe_code)
    assert risk_score < 0.2
    assert len(reasons) == 0

    # 2. Dangerous code: os.system
    malicious_code = """
import os
os.system("rmdir /s /q test")
"""
    risk_score, reasons = analyze_code_safety(malicious_code)
    assert risk_score >= 0.7
    assert any("os" in r.lower() for r in reasons)

    # 3. Dangerous code: dynamic eval()
    eval_code = "eval('__import__(\"os\").getcwd()')"
    risk_score, reasons = analyze_code_safety(eval_code)
    assert risk_score >= 0.7
    assert any("eval" in r.lower() for r in reasons)


def test_guardrail_node_flagging():
    """Verifies guardrail node requires approval for risky code."""
    risky_state: AgentState = {
        "task": "Clean up files",
        "plan": ["Delete cache"],
        "current_step_index": 0,
        "code": "import subprocess\nsubprocess.run(['rm', '-rf', '/'])",
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "error_feedback": None,
        "risk_score": 0.0,
        "risk_reasons": [],
        "requires_approval": False,
        "is_approved": False,
        "status": "code_generated",
        "final_summary": None,
        "messages": [],
    }
    result = guardrail_node(risky_state)
    assert result["requires_approval"] is True
    assert result["risk_score"] > 0.6
    assert result["status"] == "awaiting_approval"


def test_plan_and_code_parsing_utilities():
    """Verifies text extraction from LLM markdown responses."""
    raw_plan = """1. Load CSV dataset\n2. Clean missing values\n3. Train model"""
    steps = parse_plan(raw_plan)
    assert len(steps) == 3
    assert steps[0] == "Load CSV dataset"

    raw_code = "Here is the code:\n```python\nprint('Hello')\n```\nHope it helps!"
    clean_code = extract_python_code(raw_code)
    assert clean_code == "print('Hello')"


def test_workflow_graph_successful_convergence():
    """
    Executes the compiled multi-agent StateGraph end-to-end using MockLLM.
    Verifies that state progresses from planning -> coding -> guardrail -> sandbox -> critic -> completed.
    """
    app = build_workflow_graph()

    initial_state: AgentState = {
        "task": "Compute statistical mean of array",
        "plan": [],
        "current_step_index": 0,
        "code": "",
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "error_feedback": None,
        "risk_score": 0.0,
        "risk_reasons": [],
        "requires_approval": False,
        "is_approved": True,  # Pre-approve for non-interactive test
        "status": "initiated",
        "final_summary": None,
        "messages": [],
    }

    config = {"configurable": {"thread_id": "test-convergence-001"}}
    final_state = app.invoke(initial_state, config=config)

    assert final_state["status"] == "completed"
    assert "Computed Mean: 30" in str(final_state["execution_result"]["stdout"])
    assert final_state["final_summary"] is not None
    assert final_state["iteration_count"] == 0


def test_workflow_graph_max_iteration_guard():
    """
    Verifies that when code persistently fails, the cyclic loop halts when iteration_count reaches max_iterations.
    """
    app = build_workflow_graph()

    # Initial state with broken code and max_iterations=2
    initial_state: AgentState = {
        "task": "Run broken computation",
        "plan": ["Execute faulty step"],
        "current_step_index": 0,
        "code": "raise RuntimeError('Persistent computation failure')",
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": 2,
        "error_feedback": None,
        "risk_score": 0.0,
        "risk_reasons": [],
        "requires_approval": False,
        "is_approved": True,
        "status": "initiated",
        "final_summary": None,
        "messages": [],
    }

    # Custom run starting directly after planner to test retry ceiling
    from src.agents.nodes import sandbox_node, critic_node
    
    # 1st failure
    s1 = sandbox_node(initial_state)
    initial_state.update(s1)
    c1 = critic_node(initial_state)
    initial_state.update(c1)
    assert initial_state["status"] == "retrying_code"
    assert initial_state["iteration_count"] == 1

    # 2nd failure (hits max_iterations=2)
    s2 = sandbox_node(initial_state)
    initial_state.update(s2)
    c2 = critic_node(initial_state)
    initial_state.update(c2)
    assert initial_state["status"] == "failed"
    assert initial_state["iteration_count"] == 2
    assert "Workflow failed after exceeding max retry iterations" in initial_state["final_summary"]
