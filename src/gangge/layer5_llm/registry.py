"""LLM registry — factory for creating LLM instances from config."""

from __future__ import annotations

import os
from pathlib import Path

from gangge.layer5_llm.base import BaseLLM
from gangge.layer5_llm.anthropic import AnthropicLLM
from gangge.layer5_llm.openai_compat import OpenAICompatLLM


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _load_env() -> None:
    """Load .env file if present."""
    try:
        from dotenv import load_dotenv

        # Search upward from cwd for .env
        cwd = Path.cwd()
        for p in [cwd, *cwd.parents]:
            if (p / ".env").exists():
                load_dotenv(p / ".env")
                break
    except ImportError:
        pass


def create_llm(provider: str | None = None) -> BaseLLM:
    """Create an LLM instance based on configuration.

    Reads from environment variables (or .env file).
    Provider priority: explicit arg > LLM_PROVIDER env > default (anthropic).
    """
    _load_env()

    provider = (provider or _env("LLM_PROVIDER") or "anthropic").lower()
    max_tokens = int(_env("MAX_TOKENS", "8192"))
    temperature = float(_env("TEMPERATURE", "0.0"))

    if provider == "anthropic":
        api_key = _env("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        model = _env("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        return AnthropicLLM(
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    elif provider == "openai":
        api_key = _env("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        model = _env("OPENAI_MODEL", "gpt-4o")
        return OpenAICompatLLM(
            base_url="https://api.openai.com/v1",
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    elif provider == "deepseek":
        api_key = _env("DEEPSEEK_API_KEY", "")
        base_url = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        model = _env("DEEPSEEK_MODEL", "deepseek-chat")
        return OpenAICompatLLM(
            base_url=base_url,
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    elif provider == "ollama":
        base_url = _env("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        model = _env("OLLAMA_MODEL", "llama3.1")
        return OpenAICompatLLM(
            base_url=base_url,
            api_key="ollama",
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Supported: anthropic, openai, deepseek, ollama"
        )
