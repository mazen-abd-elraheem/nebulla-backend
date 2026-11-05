"""
LLM provider factory — local Ollama is the strict main provider and resilient fallback anchor.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.llm.base import BaseLLMProvider

logger = get_logger(__name__)


def get_llm_provider(name: Optional[str] = None) -> BaseLLMProvider:
    """
    Returns an LLM provider instance.
    Defaults strictly to LocalOllamaProvider ('local' / 'ollama') if name is omitted,
    empty, or unrecognized.
    """
    chosen = name or getattr(settings, "LLM_PROVIDER", "local")
    target = str(chosen).strip().lower()

    if target in ("local", "ollama", "local_ollama", "local-ollama", "default"):
        from app.providers.llm.local_ollama import LocalOllamaProvider
        return LocalOllamaProvider()

    if target in ("huggingface", "hf", "nile"):
        from app.providers.llm.huggingface_provider import HuggingFaceProvider
        return HuggingFaceProvider()

    if target == "openai":
        from app.providers.llm.openai_provider import OpenAIProvider
        return OpenAIProvider()

    if target == "anthropic":
        from app.providers.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider()

    if target == "mock":
        from app.providers.llm.mock_provider import MockLLMProvider
        return MockLLMProvider()

    # Resilient anchor: fallback to LocalOllamaProvider rather than failing
    logger.warning(f"Unknown LLM provider {name!r}, falling back safely to LocalOllamaProvider.")
    from app.providers.llm.local_ollama import LocalOllamaProvider
    return LocalOllamaProvider()
