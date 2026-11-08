from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application Settings and Configuration."""
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App Information
    APP_NAME: str = "Autonomous Agentic Workflow Engine"
    DEBUG: bool = False
    
    # LLM Settings
    LLM_PROVIDER: str = Field(default="gemini", description="LLM provider: gemini, openai, or mock")
    GEMINI_API_KEY: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gemini-2.0-flash"
    
    # Sandboxing & Execution Constraints
    SANDBOX_TIMEOUT_SECONDS: int = 30
    SANDBOX_MEMORY_LIMIT: str = "256m"
    SANDBOX_MEMORY_LIMIT_BYTES: int = 256 * 1024 * 1024  # 256 MB
    SANDBOX_CPU_QUOTA: int = 50000  # 50% of 1 CPU core
    SANDBOX_DOCKER_IMAGE: str = "python:3.12-slim"
    FORCE_LOCAL_SANDBOX: bool = False
    
    # Persistence (PostgreSQL)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "agentic_workflow"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    
    @property
    def postgres_uri(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def async_postgres_uri(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Event Streaming (Redis)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://localhost:6379/0"


settings = Settings()
