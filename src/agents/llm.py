import os
from typing import Any, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from ..config import settings


class MockLLM(BaseChatModel):
    """
    Deterministic Mock LLM for offline testing and verification.
    Provides predictable planning, code generation, and critique responses.
    """

    def _generate(self, messages: list[BaseMessage], stop: Optional[list[str]] = None, **kwargs: Any) -> ChatResult:
        last_message = messages[-1].content if messages else ""
        
        # Planner response
        if "Decompose" in last_message or "planner" in last_message.lower():
            content = (
                "1. Load and inspect data structure\n"
                "2. Perform data cleaning and transformation\n"
                "3. Compute statistical summary and metrics\n"
            )
        # Coder response when fixing an error
        elif "fix" in last_message.lower() or "error" in last_message.lower() or "traceback" in last_message.lower():
            content = (
                "```python\n"
                "# Corrected implementation\n"
                "def solve():\n"
                "    data = [10, 20, 30, 40, 50]\n"
                "    mean_val = sum(data) / len(data)\n"
                "    print(f'Computed Mean: {mean_val}')\n"
                "solve()\n"
                "```"
            )
        # Default Coder response
        elif "write python code" in last_message.lower() or "code" in last_message.lower():
            content = (
                "```python\n"
                "# Generated solution\n"
                "data = [10, 20, 30, 40, 50]\n"
                "mean_val = sum(data) / len(data)\n"
                "print(f'Computed Mean: {mean_val}')\n"
                "```"
            )
        # Critic response
        elif "evaluate" in last_message.lower() or "critic" in last_message.lower():
            content = "The execution succeeded with zero errors and produced valid output."
        else:
            content = "Task processed successfully."

        generation = ChatGeneration(message=AIMessage(content=content))
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        return "mock-llm"


def get_llm() -> BaseChatModel:
    """
    Factory to retrieve configured LLM.
    Supports Google Gemini, OpenAI, or Mock fallback.
    """
    provider = settings.LLM_PROVIDER.lower()
    
    # Google Gemini
    if provider == "gemini" and (settings.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY")):
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = settings.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY")
        return ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL or "gemini-2.0-flash",
            google_api_key=api_key,
            temperature=0.1,
        )
    
    # OpenAI
    if provider == "openai" and (settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.LLM_MODEL or "gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"),
            temperature=0.1,
        )

    # Deterministic Mock LLM (default when no API key configured)
    return MockLLM()
