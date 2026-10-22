"""LLM provider factory."""

from app.providers.llm.base import BaseLLMProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


def get_llm_provider(name: str) -> BaseLLMProvider:
    if name == "local":
        from app.providers.llm.local_ollama import LocalOllamaProvider
        return LocalOllamaProvider()
    if name == "openai":
        from app.providers.llm.openai_provider import OpenAIProvider
        return OpenAIProvider()
    if name == "anthropic":
        from app.providers.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    if name == "mock":
        from app.providers.llm.mock_provider import MockLLMProvider
        return MockLLMProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}")
