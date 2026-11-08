import asyncio
import os
import sys
import tempfile
import time
import subprocess
import threading
from typing import Optional
import psutil

from .base import BaseSandbox, ExecutionResult
from ..config import settings


class LocalProcessSandbox(BaseSandbox):
    """
    Sandboxed execution engine running code in an isolated subprocess with
    strict CPU/memory monitoring and timeout guards.
    Acts as the development fallback when Docker daemon is not active.
    """

    def __init__(
        self,
        default_timeout: int = settings.SANDBOX_TIMEOUT_SECONDS,
        max_memory_bytes: int = settings.SANDBOX_MEMORY_LIMIT_BYTES,
    ):
        self.default_timeout = default_timeout
        self.max_memory_bytes = max_memory_bytes

    def execute(self, code: str, timeout: Optional[int] = None) -> ExecutionResult:
        timeout = timeout or self.default_timeout
        start_time = time.time()
        
        # Write code to a secure temporary file
        with tempfile.TemporaryDirectory() as temp_dir:
            script_path = os.path.join(temp_dir, "script.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            # Prepare process execution
            # -u flag enables unbuffered stdout/stderr
            cmd = [sys.executable, "-u", script_path]
            
            proc = subprocess.Popen(
                cmd,
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            timed_out = False
            memory_exceeded = False
            stop_monitor = threading.Event()

            # Background thread to monitor memory consumption
            def monitor_resources():
                nonlocal memory_exceeded
                try:
                    p = psutil.Process(proc.pid)
                    while not stop_monitor.is_set() and proc.poll() is None:
                        try:
                            rss = p.memory_info().rss
                            for child in p.children(recursive=True):
                                rss += child.memory_info().rss
                            if rss > self.max_memory_bytes:
                                memory_exceeded = True
                                # Terminate process tree
                                for child in p.children(recursive=True):
                                    child.kill()
                                p.kill()
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            break
                        time.sleep(0.01)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            monitor_thread = threading.Thread(target=monitor_resources, daemon=True)
            monitor_thread.start()

            stdout, stderr = "", ""
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                # Kill process tree gracefully then hard
                try:
                    parent = psutil.Process(proc.pid)
                    for child in parent.children(recursive=True):
                        child.kill()
                    parent.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc.kill()
                try:
                    stdout, stderr = proc.communicate(timeout=1.0)
                except Exception:
                    pass
            finally:
                stop_monitor.set()
                monitor_thread.join(timeout=0.5)

            duration = round(time.time() - start_time, 3)
            exit_code = proc.returncode if proc.returncode is not None else -1

            if timed_out:
                stderr = (stderr or "") + f"\n[Sandbox Guard] Execution timed out after {timeout} seconds."
            if memory_exceeded:
                stderr = (stderr or "") + f"\n[Sandbox Guard] Memory limit exceeded ({self.max_memory_bytes // (1024*1024)}MB threshold)."

            is_success = (exit_code == 0) and not timed_out and not memory_exceeded

            return ExecutionResult(
                stdout=stdout.strip() if stdout else "",
                stderr=stderr.strip() if stderr else "",
                exit_code=exit_code,
                timed_out=timed_out,
                memory_exceeded=memory_exceeded,
                execution_time_seconds=duration,
                is_success=is_success,
            )

    async def execute_async(self, code: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Runs the execution off the main event loop asynchronously."""
        return await asyncio.to_thread(self.execute, code, timeout)
