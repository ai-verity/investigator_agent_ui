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

from crewai import LLM
import litellm                          # ← ADD THIS IMPORT

litellm.modify_params = True           # ← ADD THIS LINE
# This tells LiteLLM to automatically move any mid-conversation system
# messages back to position[0], satisfying Qwen's strict ordering requirement.


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
    resolved_api_type  = api_type   or os.getenv("NIM_API_TYPE", "local")
    resolved_model     = model_name or os.getenv("MODEL_NAME", "qwen3.5-35b")

    if resolved_api_type == "local":
        base_url, api_key = _local_endpoint()
    else:
        base_url, api_key = _cloud_endpoint()

    # LiteLLM routes "openai/<model>" to any OpenAI-compatible endpoint
    # when base_url is provided.  NIM's endpoint is fully compatible.
    litellm_model = f"openai/{resolved_model}"

    return LLM(
        model       = litellm_model,
        base_url    = base_url,
        api_key     = api_key,
        temperature = temperature,
        max_tokens  = max_tokens,
    )
