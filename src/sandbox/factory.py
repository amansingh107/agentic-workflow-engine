import logging
from .base import BaseSandbox
from .process_runner import LocalProcessSandbox
from .docker_runner import DockerSandbox
from ..config import settings

logger = logging.getLogger(__name__)


def get_sandbox() -> BaseSandbox:
    """
    Factory function that instantiates the appropriate sandbox.
    Prefers DockerSandbox when Docker daemon is accessible.
    Falls back to LocalProcessSandbox in local development environments.
    """
    if settings.FORCE_LOCAL_SANDBOX:
        logger.info("LocalProcessSandbox selected via FORCE_LOCAL_SANDBOX setting.")
        return LocalProcessSandbox()

    docker_sandbox = DockerSandbox()
    if docker_sandbox.is_available():
        logger.info("Docker daemon verified. Using DockerSandbox.")
        return docker_sandbox

    logger.warning(
        "Docker daemon is not running or accessible. "
        "Falling back to LocalProcessSandbox with resource and timeout guards."
    )
    return LocalProcessSandbox()
