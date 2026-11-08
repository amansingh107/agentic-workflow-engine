import asyncio
import time
import threading
from typing import Optional
import docker
from docker.errors import DockerException, APIError

from .base import BaseSandbox, ExecutionResult
from ..config import settings


class DockerSandbox(BaseSandbox):
    """
    Production-grade isolated sandbox leveraging Docker SDK for Python.
    Enforces strict cgroups (CPU quota, memory limits), disabled networking,
    read-only rootfs, and an active 30s timeout watchdog.
    """

    def __init__(
        self,
        image: str = settings.SANDBOX_DOCKER_IMAGE,
        default_timeout: int = settings.SANDBOX_TIMEOUT_SECONDS,
        memory_limit: str = settings.SANDBOX_MEMORY_LIMIT,
        cpu_quota: int = settings.SANDBOX_CPU_QUOTA,
    ):
        self.image = image
        self.default_timeout = default_timeout
        self.memory_limit = memory_limit
        self.cpu_quota = cpu_quota
        self._client: Optional[docker.DockerClient] = None

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            try:
                # Fast timeout (1s) to prevent hanging when Docker daemon is down
                self._client = docker.from_env(timeout=1)
                self._client.ping()
            except DockerException as e:
                self._client = None
                raise RuntimeError(
                    f"Docker daemon is not accessible: {e}. "
                    "Ensure Docker Desktop is running or use LocalProcessSandbox."
                ) from e
        return self._client

    def is_available(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False

    def execute(self, code: str, timeout: Optional[int] = None) -> ExecutionResult:
        timeout = timeout or self.default_timeout
        start_time = time.time()
        client = self._get_client()

        # Command to run python script passed via -c
        cmd = ["python", "-u", "-c", code]

        container = None
        timed_out = False
        memory_exceeded = False

        try:
            # Create container with strict resource limits
            container = client.containers.create(
                image=self.image,
                command=cmd,
                # Strict CPU Limit: cpu_quota=50000, cpu_period=100000 -> 50% of 1 core
                cpu_quota=self.cpu_quota,
                cpu_period=100000,
                # Strict Memory Limit: 256MB with swap disabled
                mem_limit=self.memory_limit,
                memswap_limit=self.memory_limit,
                # Network Isolation: no external access (prevents exfiltration or SSRF)
                network_mode="none",
                # Read-only root filesystem with ephemeral tmpfs
                read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
                detach=True,
            )

            # Start container
            container.start()

            # Watchdog timer to enforce 30s timeout
            def kill_on_timeout():
                nonlocal timed_out
                try:
                    timed_out = True
                    container.kill()
                except Exception:
                    pass

            timer = threading.Timer(timeout, kill_on_timeout)
            timer.start()

            try:
                # Wait for container to finish
                wait_res = container.wait()
                timer.cancel()
                raw_exit_code = wait_res.get("StatusCode", -1)
            except Exception:
                timer.cancel()
                raw_exit_code = -1

            # Fetch logs
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            # Check if container died of OOM (Out of Memory - Linux exit code 137 or OOMKilled)
            try:
                container.reload()
                oom_killed = container.attrs.get("State", {}).get("OOMKilled", False)
                if oom_killed or raw_exit_code == 137 and not timed_out:
                    memory_exceeded = True
            except Exception:
                pass

        except APIError as e:
            return ExecutionResult(
                stdout="",
                stderr=f"Docker API Error: {str(e)}",
                exit_code=1,
                timed_out=False,
                memory_exceeded=False,
                execution_time_seconds=round(time.time() - start_time, 3),
                is_success=False,
            )
        finally:
            # Guarantee container cleanup (no orphaned zombie containers)
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        duration = round(time.time() - start_time, 3)

        if timed_out:
            raw_exit_code = -1
            stderr += f"\n[Docker Sandbox Guard] Execution timed out after {timeout} seconds (watchdog SIGKILL triggered)."
        if memory_exceeded:
            stderr += f"\n[Docker Sandbox Guard] Container exceeded memory limit ({self.memory_limit}) and was terminated (OOMKilled)."

        is_success = (raw_exit_code == 0) and not timed_out and not memory_exceeded

        return ExecutionResult(
            stdout=stdout.strip(),
            stderr=stderr.strip(),
            exit_code=raw_exit_code,
            timed_out=timed_out,
            memory_exceeded=memory_exceeded,
            execution_time_seconds=duration,
            is_success=is_success,
        )

    async def execute_async(self, code: str, timeout: Optional[int] = None) -> ExecutionResult:
        """Asynchronously executes the docker container off the main event loop."""
        return await asyncio.to_thread(self.execute, code, timeout)
