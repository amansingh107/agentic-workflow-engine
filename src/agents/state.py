from typing import TypedDict, List, Optional, Dict, Any


class AgentState(TypedDict):
    """
    Shared memory schema passed across all nodes in the LangGraph cyclic workflow.
    """
    # User Task Specification
    task: str
    
    # Planning & Step Tracking
    plan: List[str]
    current_step_index: int
    
    # Code Generation & Execution
    code: str
    execution_result: Optional[Dict[str, Any]]
    
    # Self-Healing Cyclic State
    iteration_count: int
    max_iterations: int
    error_feedback: Optional[str]
    
    # Security & Human-in-the-Loop Flags
    risk_score: float
    risk_reasons: List[str]
    requires_approval: bool
    is_approved: bool
    
    # Workflow Status & Summary
    status: str  # planning, coding, awaiting_approval, executing, evaluating, completed, failed
    final_summary: Optional[str]
    messages: List[Dict[str, str]]
