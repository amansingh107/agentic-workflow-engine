import pytest
import asyncio
import httpx
from src.api.app import app
from src.api.routes import workflow_app
from src.agents.state import AgentState


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_health_check_endpoint():
    """Verifies that the /api/v1/health endpoint returns 200 and dependency statuses."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "sandbox_backend" in data
        assert "checkpointer_backend" in data


@pytest.mark.asyncio
async def test_start_workflow_and_fetch_status():
    """
    Verifies that POST /api/v1/workflows creates a session and runs execution.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Start workflow
        res = await client.post("/api/v1/workflows", json={"task": "Compute mean of [10, 20, 30]"})
        assert res.status_code == 200
        data = res.json()
        assert "thread_id" in data
        thread_id = data["thread_id"]

        # Wait briefly for background execution to run
        await asyncio.sleep(1.5)

        # 2. Query status
        status_res = await client.get(f"/api/v1/workflows/{thread_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["thread_id"] == thread_id
        assert status_data["status"] in ["completed", "executing", "initiated"]


@pytest.mark.asyncio
async def test_hitl_approval_and_resume_via_api():
    """
    Simulates a paused thread requiring human approval, queries the pending state via GET,
    and resumes execution via POST /api/v1/workflows/{thread_id}/resume.
    """
    transport = httpx.ASGITransport(app=app)
    thread_id = "test-api-hitl-001"
    config = {"configurable": {"thread_id": thread_id}}

    # Stage state right before approval gate with elevated risk
    workflow_app.update_state(
        config,
        {
            "task": "Sensitive data export",
            "code": "print('Exported securely after human sign-off')",
            "plan": ["Run sensitive action"],
            "current_step_index": 0,
            "requires_approval": True,
            "is_approved": False,
            "iteration_count": 0,
            "max_iterations": 3,
            "messages": [],
        },
        as_node="guardrail",
    )

    # Trigger graph execution -> pauses at approval_gate
    workflow_app.invoke(None, config=config)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Query status - should show is_paused = True and approval_payload
        status_res = await client.get(f"/api/v1/workflows/{thread_id}")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["is_paused"] is True
        assert status_data["requires_approval"] is True
        assert status_data["approval_payload"] is not None
        assert status_data["approval_payload"]["action"] == "APPROVAL_REQUIRED"

        # 2. Resume thread with approval
        resume_res = await client.post(
            f"/api/v1/workflows/{thread_id}/resume",
            json={"approved": True},
        )
        assert resume_res.status_code == 200
        resume_data = resume_res.json()
        assert resume_data["status"] == "resuming"

        # Wait for background resumption to finish
        await asyncio.sleep(1.0)

        # 3. Verify workflow completed execution in sandbox
        final_res = await client.get(f"/api/v1/workflows/{thread_id}")
        assert final_res.status_code == 200
        final_data = final_res.json()
        assert final_data["is_paused"] is False
        assert final_data["status"] == "completed"
        assert "Exported securely after human sign-off" in str(final_data["execution_result"]["stdout"])


@pytest.mark.asyncio
async def test_workflow_history_endpoint():
    """Verifies that GET /api/v1/workflows/{thread_id}/history returns checkpoint timeline."""
    transport = httpx.ASGITransport(app=app)
    thread_id = "test-api-history-001"
    config = {"configurable": {"thread_id": thread_id}}

    workflow_app.invoke(
        {
            "task": "Basic math task",
            "plan": [],
            "current_step_index": 0,
            "code": "",
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
        },
        config=config,
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/api/v1/workflows/{thread_id}/history")
        assert res.status_code == 200
        history = res.json()
        assert isinstance(history, list)
        assert len(history) > 0


@pytest.mark.asyncio
async def test_dashboard_endpoint():
    """Verifies that the /api/v1/dashboard endpoint serves the dashboard UI."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/dashboard")
        assert res.status_code == 200
        assert "Agentic Workflow Engine" in res.text
        assert "text/html" in res.headers.get("content-type", "")
