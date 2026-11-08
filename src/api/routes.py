import uuid
import asyncio
import json
import os
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from langgraph.types import Command

from ..agents.graph import build_workflow_graph
from ..agents.state import AgentState
from ..persistence.checkpointer import get_checkpointer
from ..sandbox.factory import get_sandbox
from .events import event_bus

router = APIRouter(prefix="/api/v1", tags=["Workflows"])

# Global compiled graph instance
workflow_app = build_workflow_graph()


class WorkflowCreateRequest(BaseModel):
    task: str = Field(..., description="High-level engineering or data task for the agentic engine.")
    thread_id: Optional[str] = Field(default=None, description="Optional custom thread UUID.")
    max_iterations: int = Field(default=3, description="Maximum self-healing retry iterations.")


class WorkflowResumeRequest(BaseModel):
    approved: bool = Field(..., description="Whether to approve or reject the paused operation.")
    feedback: Optional[str] = Field(default=None, description="Optional feedback string if rejected.")
    modified_code: Optional[str] = Field(default=None, description="Optional edited code to substitute.")


class WorkflowStatusResponse(BaseModel):
    thread_id: str
    status: str
    is_paused: bool
    requires_approval: bool
    approval_payload: Optional[Dict[str, Any]] = None
    code: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    final_summary: Optional[str] = None


async def run_workflow_stream(thread_id: str, initial_state: Optional[AgentState] = None, resume_command: Optional[Command] = None):
    """
    Executes or resumes graph stream, publishing node transitions to the event bus.
    """
    config = {"configurable": {"thread_id": thread_id}}

    try:
        input_data = resume_command if resume_command is not None else initial_state
        
        # Stream graph execution events
        for chunk in workflow_app.stream(input_data, config=config, stream_mode="updates"):
            for node_name, node_update in chunk.items():
                await event_bus.publish_event(
                    thread_id=thread_id,
                    event_type=f"node_{node_name}",
                    data={"node": node_name, "update": node_update},
                )
        
        # Check if paused at an interrupt gate
        snapshot = workflow_app.get_state(config)
        if snapshot.tasks and snapshot.tasks[0].interrupts:
            interrupt_val = snapshot.tasks[0].interrupts[0].value
            await event_bus.publish_event(
                thread_id=thread_id,
                event_type="interrupted_for_approval",
                data=interrupt_val,
            )
        else:
            final_status = snapshot.values.get("status", "completed")
            await event_bus.publish_event(
                thread_id=thread_id,
                event_type="workflow_finished",
                data={"status": final_status, "values": snapshot.values},
            )
    except Exception as e:
        await event_bus.publish_event(
            thread_id=thread_id,
            event_type="error",
            data={"error": str(e)},
        )


@router.post("/workflows", response_model=Dict[str, Any])
async def start_workflow(req: WorkflowCreateRequest, background_tasks: BackgroundTasks):
    """
    Initiates a new autonomous agentic workflow session.
    Returns thread_id immediately while graph runs asynchronously in background.
    """
    thread_id = req.thread_id or str(uuid.uuid4())
    initial_state: AgentState = {
        "task": req.task,
        "plan": [],
        "current_step_index": 0,
        "code": "",
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": req.max_iterations,
        "error_feedback": None,
        "risk_score": 0.0,
        "risk_reasons": [],
        "requires_approval": False,
        "is_approved": False,
        "status": "initiated",
        "final_summary": None,
        "messages": [],
    }

    # Run workflow asynchronously off the main request thread
    background_tasks.add_task(run_workflow_stream, thread_id, initial_state, None)

    return {
        "thread_id": thread_id,
        "status": "initiated",
        "message": "Workflow started successfully.",
    }


@router.get("/workflows/{thread_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(thread_id: str):
    """
    Retrieves current state snapshot and interrupt payload for a thread.
    """
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = workflow_app.get_state(config)

    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Workflow thread '{thread_id}' not found.")

    is_paused = bool(snapshot.tasks and snapshot.tasks[0].interrupts)
    approval_payload = None
    if is_paused:
        approval_payload = snapshot.tasks[0].interrupts[0].value

    values = snapshot.values
    return WorkflowStatusResponse(
        thread_id=thread_id,
        status=values.get("status", "unknown"),
        is_paused=is_paused,
        requires_approval=is_paused,
        approval_payload=approval_payload,
        code=values.get("code"),
        execution_result=values.get("execution_result"),
        final_summary=values.get("final_summary"),
    )


@router.post("/workflows/{thread_id}/resume", response_model=Dict[str, Any])
async def resume_workflow(thread_id: str, req: WorkflowResumeRequest, background_tasks: BackgroundTasks):
    """
    Resumes a paused thread with a Human-in-the-Loop approval or rejection decision.
    """
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = workflow_app.get_state(config)

    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Workflow thread '{thread_id}' not found.")

    if not (snapshot.tasks and snapshot.tasks[0].interrupts):
        raise HTTPException(
            status_code=400,
            detail=f"Workflow thread '{thread_id}' is not currently paused awaiting approval.",
        )

    resume_payload = {
        "approved": req.approved,
        "feedback": req.feedback,
        "modified_code": req.modified_code,
    }
    cmd = Command(resume=resume_payload)

    background_tasks.add_task(run_workflow_stream, thread_id, None, cmd)

    return {
        "thread_id": thread_id,
        "status": "resuming",
        "approved": req.approved,
        "message": "Resume command submitted successfully.",
    }


@router.get("/workflows/{thread_id}/history", response_model=List[Dict[str, Any]])
async def get_workflow_history(thread_id: str):
    """
    Returns full chronological history of state checkpoints stored in PostgreSQL.
    """
    config = {"configurable": {"thread_id": thread_id}}
    history_entries = []

    for snapshot in workflow_app.get_state_history(config):
        history_entries.append({
            "step": snapshot.metadata.get("step") if snapshot.metadata else None,
            "source": snapshot.metadata.get("source") if snapshot.metadata else None,
            "status": snapshot.values.get("status"),
            "current_step_index": snapshot.values.get("current_step_index"),
            "iteration_count": snapshot.values.get("iteration_count"),
            "has_error": bool(snapshot.values.get("error_feedback")),
        })

    return history_entries


@router.get("/workflows/{thread_id}/stream")
async def stream_workflow_events(thread_id: str):
    """
    Server-Sent Events (SSE) endpoint to stream live agent steps and sandbox output.
    """
    async def event_generator():
        async for event in event_bus.subscribe_events(thread_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """System health check verifying dependencies."""
    sandbox = get_sandbox()
    checkpointer = get_checkpointer()

    return {
        "status": "healthy",
        "sandbox_backend": type(sandbox).__name__,
        "checkpointer_backend": type(checkpointer).__name__,
    }


@router.get("/dashboard", response_class=FileResponse)
async def serve_dashboard():
    """Serves the interactive real-time workflow engine dashboard."""
    dashboard_path = os.path.join(os.path.dirname(__file__), "..", "ui", "dashboard.html")
    return FileResponse(dashboard_path)

