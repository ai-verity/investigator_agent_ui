"""
tools/nim_llm.py
────────────────
NVIDIA NIM LLM factory using CrewAI's native LLM class.

CrewAI wraps LiteLLM internally. NIM exposes an OpenAI-compatible
/v1/chat/completions endpoint, so we pass it through LiteLLM's
openai provider with a custom base_url — zero LangChain required.

Supported models (set MODEL_NAME in .env):
  Text/chat  : meta/llama-3.3-70b-instruct  (default)
               meta/llama-3.1-405b-instruct
               mistralai/mixtral-8x7b-instruct-v0.1
               nvidia/nemotron-4-340b-instruct

  Vision     : nvidia/nemotron-nano-12b-v2-vl  (used by ImageAnalyzerTool)

API modes (set NIM_API_TYPE in .env):
  cloud      : NVIDIA hosted — requires NVIDIA_API_KEY
  local      : self-hosted NIM container — no key needed
"""

from __future__ import annotations

import os
from typing import Optional

import litellm
from crewai import LLM


# ── litellm patches ──────────────────────────────────────────────
# 1. Qwen requires all system messages at the start of the
#    conversation.  CrewAI can place them mid-conversation.
# 2. Qwen 3.x "thinking" mode is disabled via extra_body so the
#    model returns direct answers (~60 tok/s on DGX Spark) instead
#    of emitting a lengthy <think>…</think> reasoning block first.

_litellm_patched = False


def _reorder_system_messages(messages: list[dict]) -> list[dict]:
    """Move all system messages to a single block at position 0."""
    if not messages:
        return messages

    system_parts: list[str] = []
    non_system: list[dict] = []

    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if content:
                system_parts.append(content)
        else:
            non_system.append(msg)

    if not system_parts:
        return messages

    merged_system = {"role": "system", "content": "\n\n".join(system_parts)}
    return [merged_system] + non_system


def _apply_litellm_patch() -> None:
    """Monkey-patch litellm.completion (once) to reorder messages
    and disable Qwen thinking mode for faster inference."""
    global _litellm_patched
    if _litellm_patched:
        return
    _litellm_patched = True

    _orig = litellm.completion

    def _patched_completion(*args, **kwargs):
        if "messages" in kwargs and kwargs["messages"]:
            kwargs["messages"] = _reorder_system_messages(kwargs["messages"])

        extra = kwargs.get("extra_body") or {}
        extra["chat_template_kwargs"] = {"enable_thinking": False}
        kwargs["extra_body"] = extra

        return _orig(*args, **kwargs)

    litellm.completion = _patched_completion


# ── endpoint helpers ─────────────────────────────────────────────

def _cloud_endpoint() -> tuple[str, str]:
    """Return (base_url, api_key) for NVIDIA cloud NIM."""
    base_url = os.getenv("CLOUD_NIM_URL", "https://integrate.api.nvidia.com/v1")
    api_key  = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        raise ValueError(
            "NVIDIA_API_KEY is not set. "
            "Export it or add it to your .env file before running."
        )
    return base_url.rstrip("/"), api_key


def _local_endpoint() -> tuple[str, str]:
    """Return (base_url, api_key) for a locally running NIM container."""
    base_url = os.getenv("LOCAL_NIM_URL", "http://localhost:8000/v1")
    return base_url.rstrip("/"), "not-needed"   # local NIM ignores the key


# ── public factory ───────────────────────────────────────────────

def create_nim_llm(
    api_type: Optional[str]   = None,
    model_name: Optional[str] = None,
    temperature: float        = 0.2,
    max_tokens: int           = 5000,
) -> LLM:
    """
    Return a CrewAI LLM instance pointed at the NIM endpoint.

    Parameters
    ----------
    api_type    : "cloud" | "local"  (overrides NIM_API_TYPE env var)
    model_name  : NIM model slug     (overrides MODEL_NAME env var)
    temperature : sampling temperature
    max_tokens  : max completion tokens

    Example
    -------
    >>> llm = create_nim_llm()                              # uses .env
    >>> llm = create_nim_llm(api_type="local")             # local NIM container
    >>> llm = create_nim_llm(model_name="meta/llama-3.1-405b-instruct")
    """
    _apply_litellm_patch()

    resolved_api_type  = api_type   or os.getenv("NIM_API_TYPE", "local")
    resolved_model     = model_name or os.getenv("MODEL_NAME", "qwen3.5-35b")

    if resolved_api_type == "local":
        base_url, api_key = _local_endpoint()
    else:
        base_url, api_key = _cloud_endpoint()

    litellm_model = f"openai/{resolved_model}"

    return LLM(
        model       = litellm_model,
        base_url    = base_url,
        api_key     = api_key,
        temperature = temperature,
        max_tokens  = max_tokens,
    )
