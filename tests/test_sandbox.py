import pytest
import asyncio
from src.sandbox.process_runner import LocalProcessSandbox
from src.sandbox.factory import get_sandbox
from src.sandbox.base import BaseSandbox, ExecutionResult


@pytest.fixture
def sandbox():
    """Provides a LocalProcessSandbox with a tight 3-second timeout for testing."""
    return LocalProcessSandbox(default_timeout=3, max_memory_bytes=64 * 1024 * 1024)  # 64MB limit for quick test


def test_successful_execution(sandbox):
    """Verifies standard clean Python execution and stdout capture."""
    code = """
x = 10
y = 20
print(f"Result: {x + y}")
"""
    result: ExecutionResult = sandbox.execute(code)
    assert result.is_success is True
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.stdout == "Result: 30"
    assert result.stderr == ""
    assert result.execution_time_seconds > 0


def test_syntax_error_handling(sandbox):
    """Verifies that invalid Python code produces a nonzero exit code and stderr."""
    code = "def broken_syntax(:"
    result: ExecutionResult = sandbox.execute(code)
    assert result.is_success is False
    assert result.exit_code != 0
    assert "SyntaxError" in result.stderr


def test_runtime_exception_handling(sandbox):
    """Verifies that unhandled runtime exceptions are cleanly reported."""
    code = """
def divide(a, b):
    return a / b

print(divide(10, 0))
"""
    result: ExecutionResult = sandbox.execute(code)
    assert result.is_success is False
    assert result.exit_code != 0
    assert "ZeroDivisionError" in result.stderr


def test_timeout_guard_kills_infinite_loop(sandbox):
    """Verifies that an infinite loop is killed forcefully by the timeout watchdog."""
    code = """
import time
print("Starting infinite loop...")
while True:
    time.sleep(0.1)
"""
    # Test with 2-second timeout guard
    result: ExecutionResult = sandbox.execute(code, timeout=2)
    assert result.is_success is False
    assert result.timed_out is True
    assert result.execution_time_seconds >= 1.8
    assert result.execution_time_seconds < 3.5
    assert "[Sandbox Guard] Execution timed out" in result.stderr


def test_memory_limit_guard(sandbox):
    """Verifies that an intentional memory bomb is terminated by memory watchdog."""
    code = """
import time
# Try to allocate 120MB (limit is 64MB)
data = bytearray(120 * 1024 * 1024)
time.sleep(0.3)
print("Allocated successfully")
"""
    result: ExecutionResult = sandbox.execute(code)
    # The process should be killed for exceeding memory or crash with MemoryError
    assert (result.memory_exceeded is True) or ("MemoryError" in result.stderr) or (result.exit_code != 0)
    assert result.is_success is False


@pytest.mark.asyncio
async def test_async_execution():
    """Verifies that async execution runs without blocking event loop."""
    sandbox = LocalProcessSandbox(default_timeout=5)
    code = "import time; time.sleep(0.5); print('Async Done')"
    result = await sandbox.execute_async(code)
    assert result.is_success is True
    assert result.stdout == "Async Done"


def test_sandbox_factory():
    """Verifies that get_sandbox() returns a valid BaseSandbox instance."""
    instance = get_sandbox()
    assert isinstance(instance, BaseSandbox)
