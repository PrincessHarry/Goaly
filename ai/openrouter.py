from __future__ import annotations

import os
from typing import Any, Dict, Optional


class OpenRouterConfig:
    """
    Minimal OpenRouter (OpenAI-compatible) configuration.

    Env vars:
      - OPENROUTER_API_KEY (required in production)
      - OPENROUTER_BASE_URL (optional; default: https://openrouter.ai/api/v1)
      - OPENROUTER_MODEL_TEXT (optional; default: google/gemini-2.0-flash)
      - OPENROUTER_MODEL_VISION (optional; default: google/gemini-2.0-flash)
      - OPENROUTER_SITE_URL (optional; sent as HTTP-Referer)
      - OPENROUTER_APP_NAME (optional; sent as X-Title)
      - AI_TEMPERATURE (optional float; default 0.4)
      - AI_MAX_TOKENS (optional int; default 800)
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()

        # Default to OpenRouter Gemini models as requested.
        default_model = "google/gemini-2.0-flash"
        self.model_text = os.getenv("OPENROUTER_MODEL_TEXT", default_model).strip()
        self.model_vision = os.getenv("OPENROUTER_MODEL_VISION", default_model).strip()

        self.site_url = os.getenv("OPENROUTER_SITE_URL", "").strip()
        self.app_name = os.getenv("OPENROUTER_APP_NAME", "Goaly").strip()

        self.temperature = float(os.getenv("AI_TEMPERATURE", "0.4"))
        self.max_tokens = int(os.getenv("AI_MAX_TOKENS", "800"))


def get_openai_client():
    """
    Returns an OpenAI SDK client configured for OpenRouter.

    We keep this import local so the app can start even if deps
    haven't been installed yet during hackathon iteration.
    """

    from openai import OpenAI  # type: ignore

    cfg = OpenRouterConfig()
    return OpenAI(
        base_url=cfg.base_url,
        api_key=cfg.api_key or "missing-openrouter-api-key",
        default_headers=_openrouter_headers(cfg),
    )


def _openrouter_headers(cfg: OpenRouterConfig) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if cfg.site_url:
        headers["HTTP-Referer"] = cfg.site_url
    if cfg.app_name:
        headers["X-Title"] = cfg.app_name
    return headers


def require_openrouter_api_key() -> None:
    if not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. "
            "Set it in your environment (.env) to enable AI features."
        )


def chat_completion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    response_format: Optional[dict[str, Any]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    extra: Optional[dict[str, Any]] = None,
) -> str:
    """
    Thin wrapper around chat.completions.create returning the content string.
    """
    client = get_openai_client()
    cfg = OpenRouterConfig()

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": cfg.temperature if temperature is None else temperature,
        "max_tokens": cfg.max_tokens if max_tokens is None else max_tokens,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format
    if extra:
        kwargs.update(extra)

    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    return (choice.message.content or "").strip()

