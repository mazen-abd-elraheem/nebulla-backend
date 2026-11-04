"""LLM Provider package — Ollama local engine, factory, and base interfaces."""

from app.providers.llm.base import BaseLLMProvider, DEFAULT_SYSTEM_PROMPT, LLMProviderError
from app.providers.llm.factory import get_llm_provider
from app.providers.llm.local_ollama import LocalOllamaProvider

__all__ = [
    "BaseLLMProvider",
    "DEFAULT_SYSTEM_PROMPT",
    "LLMProviderError",
    "LocalOllamaProvider",
    "get_llm_provider",
]
