"""Multi-provider LLM abstraction — Ollama, OpenAI, Anthropic, Groq.

Used by Resume Matcher and other AI features in DEX Studio.
Optionally uses DataEngineX LLM when available.
"""

from __future__ import annotations

import structlog

__all__ = ["LLMConfig", "LLMProvider", "PROVIDER_MODELS", "PROVIDER_LABELS", "DEFAULT_OLLAMA_MODEL"]

logger = structlog.get_logger()

# Try to import DataEngineX LLM for integration
try:
    from dataenginex.ml.llm import ChatMessage as DexChatMessage
    from dataenginex.ml.llm import get_llm_provider as _dex_llm_provider

    DEX_LLM_AVAILABLE = True
except ImportError:
    DEX_LLM_AVAILABLE = False
    _dex_llm_provider = None
    DexChatMessage = None
    logger.warning("dataenginex LLM not available, using local provider")

DEFAULT_OLLAMA_MODEL = "llama3.2"

# Curated model lists per provider
PROVIDER_MODELS: dict[str, list[str]] = {
    "ollama": [
        DEFAULT_OLLAMA_MODEL,
        "llama3.1",
        "llama3.1:70b",
        "mistral",
        "gemma2",
        "qwen2.5-coder",
        "phi4",
    ],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": ["claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-6"],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    "openai_compat": ["custom"],
}

PROVIDER_LABELS: dict[str, str] = {
    "ollama": "Ollama (Local)",
    "openai": "OpenAI",
    "anthropic": "Anthropic (Claude)",
    "groq": "Groq (Fast)",
    "openai_compat": "OpenAI-compatible",
}


class LLMConfig:
    """LLM provider configuration — mutable, passed per-request."""

    __slots__ = ("provider", "model", "api_key", "base_url", "timeout")

    def __init__(
        self,
        provider: str = "ollama",
        model: str = DEFAULT_OLLAMA_MODEL,
        api_key: str | None = None,
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    @classmethod
    def from_studio_config(cls, cfg: object) -> LLMConfig:
        """Build from a StudioConfig (avoids circular imports)."""
        return cls(
            provider=getattr(cfg, "llm_provider", "ollama"),
            model=getattr(cfg, "llm_model", DEFAULT_OLLAMA_MODEL),
            api_key=getattr(cfg, "llm_api_key", None),
            base_url=getattr(cfg, "llm_base_url", "http://localhost:11434"),
        )


class LLMProvider:
    """Unified async chat interface across multiple LLM providers."""

    @staticmethod
    def is_online(config: LLMConfig) -> tuple[bool, str]:
        """Synchronous reachability check. Returns (reachable, status_message)."""
        import httpx

        try:
            with httpx.Client(timeout=5) as client:
                if config.provider == "ollama":
                    resp = client.get(f"{config.base_url}/api/tags")
                    return resp.status_code == 200, "online"
                elif config.provider in ("openai", "groq", "openai_compat"):
                    base = _api_base(config)
                    headers: dict[str, str] = {}
                    if config.api_key:
                        headers["Authorization"] = f"Bearer {config.api_key}"
                    resp = client.get(f"{base}/models", headers=headers)
                    return resp.status_code < 400, f"HTTP {resp.status_code}"
                elif config.provider == "anthropic":
                    # No free health endpoint; key presence is the signal
                    status = "key_configured" if config.api_key else "no_api_key"
                    return bool(config.api_key), status
                else:
                    return False, f"Unknown provider: {config.provider}"
        except Exception as exc:
            return False, str(exc)[:80]

    @staticmethod
    async def chat(config: LLMConfig, messages: list[dict[str, str]]) -> str:
        """Send messages and return response text. Raises on error."""
        if config.provider == "ollama":
            return await LLMProvider._ollama(config, messages)
        elif config.provider in ("openai", "groq", "openai_compat"):
            return await LLMProvider._openai_compat(config, messages)
        elif config.provider == "anthropic":
            return await LLMProvider._anthropic(config, messages)
        else:
            raise ValueError(f"Unsupported provider: {config.provider}")

    # ------------------------------------------------------------------ #
    #  Provider implementations                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def _ollama(config: LLMConfig, messages: list[dict[str, str]]) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=config.timeout) as client:
            resp = await client.post(
                f"{config.base_url}/api/chat",
                json={
                    "model": config.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": 2048},
                },
            )
            resp.raise_for_status()
            return str(resp.json().get("message", {}).get("content", "")).strip()

    @staticmethod
    async def _openai_compat(config: LLMConfig, messages: list[dict[str, str]]) -> str:
        import httpx

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        async with httpx.AsyncClient(timeout=config.timeout) as client:
            resp = await client.post(
                f"{_api_base(config)}/chat/completions",
                headers=headers,
                json={
                    "model": config.model,
                    "messages": messages,
                    "max_tokens": 2048,
                },
            )
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            if choices:
                return str(choices[0].get("message", {}).get("content", "")).strip()
            return ""

    @staticmethod
    async def _anthropic(config: LLMConfig, messages: list[dict[str, str]]) -> str:
        import httpx

        if not config.api_key:
            raise ValueError("Anthropic API key required — set it in System > Settings.")
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        conv = [m for m in messages if m["role"] != "system"]
        body: dict[str, object] = {
            "model": config.model,
            "max_tokens": 2048,
            "messages": conv,
        }
        if system_parts:
            body["system"] = "\n".join(system_parts)
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=config.timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            content = resp.json().get("content", [])
            if content and isinstance(content, list):
                return str(content[0].get("text", "")).strip()
            return ""


def _api_base(config: LLMConfig) -> str:
    if config.provider == "openai":
        return "https://api.openai.com/v1"
    if config.provider == "groq":
        return "https://api.groq.com/openai/v1"
    return config.base_url  # openai_compat
