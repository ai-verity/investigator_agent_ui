from __future__ import annotations

import os
from typing import Optional

import litellm
from crewai import LLM


# ── Monkey-patch: fix Qwen's "system message must be first" constraint ──────────

_original_completion = litellm.completion

def _qwen_safe_completion(*args, **kwargs):
    """
    Qwen models reject requests where a system message appears anywhere
    other than position 0. CrewAI's ReAct loop injects system messages
    mid-conversation, so we intercept every call and:
      1. Collect all system messages
      2. Merge them into one
      3. Place the merged system message at index 0
      4. Leave all other messages in original order
    """
    messages = kwargs.get("messages", [])
    if messages:
        sys_msgs   = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        if sys_msgs:
            merged_content = "\n\n".join(m["content"] for m in sys_msgs)
            kwargs["messages"] = [{"role": "system", "content": merged_content}] + other_msgs
    return _original_completion(*args, **kwargs)

litellm.completion = _qwen_safe_completion   # ← patch applied at import time

# ── endpoint helpers ─────────────────────────────────────────────

def _cloud_endpoint() -> tuple[str, str]:
    base_url = os.getenv("CLOUD_NIM_URL", "https://integrate.api.nvidia.com/v1")
    api_key  = os.getenv("NVIDIA_API_KEY", "")
    if not api_key:
        raise ValueError("NVIDIA_API_KEY is not set.")
    return base_url.rstrip("/"), api_key

def _local_endpoint() -> tuple[str, str]:
    base_url = os.getenv("LOCAL_NIM_URL", "http://localhost:8000/v1")
    return base_url.rstrip("/"), "not-needed"

# ── public factory ───────────────────────────────────────────────

def create_nim_llm(
    api_type: Optional[str]   = None,
    model_name: Optional[str] = None,
    temperature: float        = 0.2,
    max_tokens: int           = 5000,
) -> LLM:
    resolved_api_type = api_type    or os.getenv("NIM_API_TYPE", "local")
    resolved_model    = model_name  or os.getenv("MODEL_NAME", "qwen3.5-35b")

    if resolved_api_type == "local":
        base_url, api_key = _local_endpoint()
    else:
        base_url, api_key = _cloud_endpoint()

    return LLM(
        model       = f"openai/{resolved_model}",
        base_url    = base_url,
        api_key     = api_key,
        temperature = temperature,
        max_tokens  = max_tokens,
    )