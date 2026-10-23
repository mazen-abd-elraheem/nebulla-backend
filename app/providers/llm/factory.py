"""LLM provider factory."""

from app.providers.llm.base import BaseLLMProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


def get_llm_provider(name: str) -> BaseLLMProvider:
    if name in ("local", "ollama"):
        from app.providers.llm.local_ollama import LocalOllamaProvider
        return LocalOllamaProvider()
    if name in ("huggingface", "hf", "nile"):
        from app.providers.llm.huggingface_provider import HuggingFaceProvider
        return HuggingFaceProvider()
    if name == "openai":
        from app.providers.llm.openai_provider import OpenAIProvider
        return OpenAIProvider()
    if name == "anthropic":
        from app.providers.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    raise ValueError(f"Unknown LLM provider: {name!r}")
