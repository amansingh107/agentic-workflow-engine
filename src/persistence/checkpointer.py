import logging
from typing import Optional, Any
from langgraph.checkpoint.memory import MemorySaver
from ..config import settings

logger = logging.getLogger(__name__)

# Global singleton checkpointer instance
_GLOBAL_CHECKPOINTER: Optional[Any] = None


def get_checkpointer(force_postgres: bool = False) -> Any:
    """
    Returns the configured checkpointer.
    Attempts PostgreSQL connection via PostgresSaver.
    Falls back gracefully to MemorySaver for testing and development environments.
    """
    global _GLOBAL_CHECKPOINTER
    if _GLOBAL_CHECKPOINTER is not None:
        return _GLOBAL_CHECKPOINTER

    if force_postgres or not settings.FORCE_LOCAL_SANDBOX:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg_pool import ConnectionPool

            # Connection string for psycopg v3
            conn_info = (
                f"host={settings.POSTGRES_HOST} "
                f"port={settings.POSTGRES_PORT} "
                f"dbname={settings.POSTGRES_DB} "
                f"user={settings.POSTGRES_USER} "
                f"password={settings.POSTGRES_PASSWORD}"
            )
            pool = ConnectionPool(conninfo=conn_info, max_size=10, timeout=2.0)
            checkpointer = PostgresSaver(pool)
            checkpointer.setup()
            logger.info("Successfully connected and initialized PostgreSQL checkpointer.")
            _GLOBAL_CHECKPOINTER = checkpointer
            return _GLOBAL_CHECKPOINTER
        except Exception as e:
            logger.warning(
                f"Could not connect to PostgreSQL ({e}). "
                "Falling back to MemorySaver for workflow state checkpointing."
            )

    _GLOBAL_CHECKPOINTER = MemorySaver()
    return _GLOBAL_CHECKPOINTER


def reset_checkpointer():
    """Helper to reset checkpointer singleton (primarily for test isolation)."""
    global _GLOBAL_CHECKPOINTER
    _GLOBAL_CHECKPOINTER = None
