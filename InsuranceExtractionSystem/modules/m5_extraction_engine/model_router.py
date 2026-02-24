"""
M5: Model Router — config 기반 LLM Provider 선택 + 폴백
"""
from typing import Optional

from config.settings import settings
from .providers.base import BaseLLMProvider
from .providers.gemini_provider import GeminiProvider
from .providers.openai_provider import OpenAIProvider
from .providers.claude_provider import ClaudeProvider


_providers: dict[str, BaseLLMProvider] = {}


def get_provider(name: str, api_key: str = None) -> BaseLLMProvider:
    """Provider 인스턴스를 가져오거나 생성합니다."""
    if name in _providers:
        return _providers[name]

    key_map = {
        "gemini": api_key or settings.gemini_api_key,
        "openai": api_key or settings.openai_api_key,
        "claude": api_key or settings.anthropic_api_key,
    }
    provider_map = {
        "gemini": GeminiProvider,
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
    }

    api = key_map.get(name)
    cls = provider_map.get(name)
    if not cls:
        raise ValueError(f"Unknown provider: {name}. Available: {list(provider_map.keys())}")
    if not api:
        raise ValueError(f"API key not configured for {name}")

    provider = cls(api_key=api)
    _providers[name] = provider
    return provider


def get_primary_provider(api_key: str = None) -> BaseLLMProvider:
    """설정에 지정된 Primary Provider 반환"""
    return get_provider(settings.primary_provider, api_key)


def get_secondary_provider(api_key: str = None) -> BaseLLMProvider:
    """설정에 지정된 Secondary Provider 반환 (Ensemble용)"""
    return get_provider(settings.secondary_provider, api_key)


def configure_provider(name: str, api_key: str) -> BaseLLMProvider:
    """런타임에 Provider를 (재)설정합니다."""
    provider_map = {
        "gemini": GeminiProvider,
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
    }
    cls = provider_map.get(name)
    if not cls:
        raise ValueError(f"Unknown provider: {name}")

    provider = cls(api_key=api_key)
    _providers[name] = provider
    return provider


def list_configured_providers() -> list[dict]:
    """현재 설정된 Provider 목록"""
    return [
        {"name": name, "model": p.get_model_name(), "provider_type": p.provider_name}
        for name, p in _providers.items()
    ]
