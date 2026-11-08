from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Optional


class ExecutionResult(BaseModel):
    """Encapsulates the output and telemetry of a sandboxed code execution."""
    stdout: str = Field(default="", description="Standard output from execution")
    stderr: str = Field(default="", description="Standard error / tracebacks")
    exit_code: int = Field(default=0, description="Exit code (0 = success)")
    timed_out: bool = Field(default=False, description="True if execution exceeded timeout guard")
    memory_exceeded: bool = Field(default=False, description="True if process was killed due to memory limit")
    execution_time_seconds: float = Field(default=0.0, description="Execution duration in seconds")
    is_success: bool = Field(default=False, description="True if exit_code == 0 and not timed out and not memory_exceeded")


class BaseSandbox(ABC):
    """Abstract interface for all code execution sandboxes."""

    @abstractmethod
    def execute(self, code: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Synchronously execute Python code inside the sandbox."""
        pass

    @abstractmethod
    async def execute_async(self, code: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Asynchronously execute Python code inside the sandbox without blocking event loop."""
        pass
