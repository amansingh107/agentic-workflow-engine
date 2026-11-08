import pytest
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from src.agents.state import AgentState
from src.agents.graph import build_workflow_graph


def test_checkpointing_state_persistence_and_history():
    """
    Verifies that LangGraph checkpointing persists state at every node boundary
    and allows inspection of state snapshots and chronological history.
    """
    checkpointer = MemorySaver()
    app = build_workflow_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "thread-persistence-001"}}

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
        "is_approved": False,
        "status": "initiated",
        "final_summary": None,
        "messages": [],
    }

    # Execute workflow
    final_state = app.invoke(initial_state, config=config)
    assert final_state["status"] == "completed"

    # Verify state snapshot is durably saved under thread_id
    current_snapshot = app.get_state(config)
    assert current_snapshot.values["status"] == "completed"
    assert "Computed Mean: 30" in str(current_snapshot.values["execution_result"]["stdout"])

    # Verify chronological history is preserved
    history = list(app.get_state_history(config))
    assert len(history) > 3  # Multiple checkpoints persisted across steps


def test_hitl_interrupt_pauses_on_security_risk():
    """
    Verifies that code with elevated risk triggers an interrupt, suspending
    workflow execution and exposing the approval payload to the caller.
    """
    checkpointer = MemorySaver()
    app = build_workflow_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "thread-hitl-002"}}

    # Task that will generate high-risk code requiring approval
    # We will simulate this by passing risky code directly to test the gate
    risky_state: AgentState = {
        "task": "Perform maintenance tasks",
        "plan": ["Execute command"],
        "current_step_index": 0,
        "code": "import os\nos.system('echo Risky Operation')",
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "error_feedback": None,
        "risk_score": 0.0,
        "risk_reasons": [],
        "requires_approval": False,
        "is_approved": False,
        "status": "initiated",
        "final_summary": None,
        "messages": [],
    }

    # Execute from guardrail node
    # Note: planner & coder will overwrite code unless we pass it, so let's start the app
    # When coder generates clean code it won't pause, so let's test the gate directly or through graph
    # Let's verify through graph with a custom node or state update
    # First, let's create a thread at coder output
    app.update_state(
        config,
        {
            "task": "Risky admin task",
            "code": "import os\nos.system('echo Delete')",
            "plan": ["Run command"],
            "current_step_index": 0,
            "iteration_count": 0,
            "max_iterations": 3,
            "messages": [],
        },
        as_node="coder",
    )

    # Invoke from the current state (next node is guardrail -> approval_gate)
    app.invoke(None, config=config)

    # Verify thread is paused at the approval_gate interrupt
    state_snapshot = app.get_state(config)
    assert len(state_snapshot.tasks) > 0
    task_interrupts = state_snapshot.tasks[0].interrupts
    assert len(task_interrupts) > 0
    interrupt_payload = task_interrupts[0].value
    assert interrupt_payload["action"] == "APPROVAL_REQUIRED"
    assert interrupt_payload["risk_score"] >= 0.7


def test_hitl_resume_with_approval():
    """
    Verifies that a suspended thread resumes execution and proceeds to the sandbox
    when human approval is granted via Command(resume={'approved': True}).
    """
    checkpointer = MemorySaver()
    app = build_workflow_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "thread-hitl-resume-003"}}

    # Stage state at coder with risky code
    app.update_state(
        config,
        {
            "task": "Risky task",
            "code": "print('Approved Sensitive Script Executed')",
            "plan": ["Run script"],
            "current_step_index": 0,
            "requires_approval": True,
            "is_approved": False,
            "iteration_count": 0,
            "max_iterations": 3,
            "messages": [],
        },
        as_node="guardrail",
    )

    # Next node is approval_gate -> will interrupt
    app.invoke(None, config=config)

    # Verify paused
    snapshot = app.get_state(config)
    assert len(snapshot.tasks[0].interrupts) > 0

    # Resume with APPROVAL
    resumed_state = app.invoke(Command(resume={"approved": True}), config=config)

    # Thread should have executed code in sandbox and completed!
    assert resumed_state["is_approved"] is True
    assert resumed_state["status"] == "completed"
    assert "Approved Sensitive Script Executed" in str(resumed_state["execution_result"]["stdout"])


def test_hitl_resume_with_rejection():
    """
    Verifies that when human rejects code without feedback, workflow halts at end_rejected.
    """
    checkpointer = MemorySaver()
    app = build_workflow_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "thread-hitl-reject-004"}}

    app.update_state(
        config,
        {
            "task": "Dangerous task",
            "code": "import os; os.system('echo malicious')",
            "plan": ["Run script"],
            "current_step_index": 0,
            "requires_approval": True,
            "is_approved": False,
            "iteration_count": 0,
            "max_iterations": 3,
            "messages": [],
        },
        as_node="guardrail",
    )

    app.invoke(None, config=config)

    # Resume with REJECTION (no feedback)
    resumed_state = app.invoke(Command(resume={"approved": False}), config=config)
    assert resumed_state["is_approved"] is False
    assert resumed_state["status"] == "rejected_by_human"
