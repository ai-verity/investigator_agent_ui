#!/usr/bin/env python3
"""
Optimized VLM inference for local NIM or cloud API.
Usage:
    python model_inference_optimized.py data/old_permit_modified.jpg --api-type local
    python model_inference_optimized.py data/old_permit_modified.jpg --api-type cloud

Environment variables (can be set in .env file):
    LOCAL_NIM_URL      (default: http://localhost:8000/v1)
    CLOUD_NIM_URL      (default: https://integrate.api.nvidia.com/v1)
    NVIDIA_API_KEY     (required for cloud)
    MODEL_NAME         (default: nvidia/nemotron-nano-12b-v2-vl)
"""

import base64
import json
import os
import time
import argparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

system_message = """
        You are an architectural blueprint dimension extraction engine.

        Extract only what is clearly visible in the image.
        No hallucination. No assumptions.

        Output ONLY valid JSON.
        No explanations. No markdown. No extra text.

        Rules:

        - Extract dimensions exactly as written (7'8", 34", 30' 9", 8' 6'').
        - Do NOT convert units.
        - If partially unreadable, replace missing part with "[unclear]".
        - If not visible, use null.
        - If repeated in grid, list once and mark location as "repeated".

        COMPUTATION RULE:

        If a room dimension is shown as connected segments (example: 8' 6'' and 5' 6'') on the same dimension line, you MUST:

        1. Extract each segment separately in "segment_dimensions".
        2. Compute the total.
        3. Add computed total in "room_dimensions".
        4. Set location as "computed from visible segments".

        Feet-Inch Addition Rule:
        - Add inches.
        - If inches ≥ 12, convert to feet.
        Example:
        8' 6'' + 5' 6'' = 14' 0''

        Do NOT compute if:
        - Any segment is unclear.
        - Segments are not clearly connected.
        - Total is already written.

        Follow the required JSON schema exactly.
    """

# ---------------- USER MESSAGE ----------------
user_message = """
    Extract clearly visible architectural dimensions and space labels from the residential blueprint image.

    Ignore:
    - Title block
    - Permit/project info
    - Stamps
    - Code references
    - Administrative text
    - Handwritten notes

    Focus only on:
    - Room names
    - Floor plan dimensions
    - Overall building dimensions
    - Segment dimensions
    - Room dimensions
    - Deck dimensions
    - Window labels
    - Vertical section dimensions

    Extraction Rules:
    - Do NOT merge unless computation rule applies.
    - Associate dimensions to rooms only if clearly tied.
    - Do NOT infer missing building dimensions.

    Return EXACTLY this JSON:

    {
    "overall_dimensions": [{ "value": "string", "location": "string" }],
    "segment_dimensions": [{ "value": "string", "location": "string" }],
    "room_dimensions": [{ "room_name": "string", "value": "string" }],
    "deck_dimensions": [{ "value": "string", "location": "string" }],
    "window_dimensions": [{ "value": "string", "location": "string" }],
    "vertical_section_dimensions": [{ "value": "string", "location": "string" }],
    "spaces": [{
        "name": "string",
        "type": "room | bathroom | kitchen | dining area | deck | other",
        "dimensions": "string or null"
    }],
    "other_dimensions": [{ "value": "string", "location": "string" }],
    "extraction_confidence": "high | medium | low"
    }

    Return ONLY JSON.
"""


# Helper: encode image to base64


def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# Main inference function


def run_inference(api_type, user_message, system_message=None, image_path=None):
    # Read settings from environment
    model_name = os.getenv("MODEL_NAME", "nvidia/nemotron-nano-12b-v2-vl")

    if api_type == "local":
        base_url = os.getenv("LOCAL_NIM_URL", "http://localhost:8000/v1")
        headers = {"Content-Type": "application/json"}
        api_key = None
    else:  # cloud
        base_url = os.getenv("CLOUD_NIM_URL", "https://integrate.api.nvidia.com/v1")
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise ValueError(
                "NVIDIA_API_KEY environment variable not set for cloud inference"
            )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        # Build payload
    payload = {
        "model": model_name,
        "messages": [
            #           {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                ],
            },
        ],
        "max_tokens": 5000,
        "temperature": 0.2,
    }

    if image_path:
        # Encode image
        encode_start = time.time()
        base64_image = encode_image(image_path)
        encode_time = time.time() - encode_start
        image_data = {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_message},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_message},
                        image_data,
                    ],
                },
            ],
            "max_tokens": 5000,
            "temperature": 0.2,
        }

    else:
        encode_time = -1

    url = f"{base_url.rstrip('/')}/chat/completions"

    # Use a session with connection pooling and retries
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    inference_start = time.time()
    print(inference_start)
    try:
        response = session.post(url, headers=headers, json=payload)
        print("response", response)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return
    inference_time = time.time() - inference_start

    result = response.json()
    try:
        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        output_tokens = usage.get("completion_tokens", 0)
        tps = output_tokens / inference_time if inference_time > 0 else 0

        print("\n" + "=" * 60)
        print(f"Inference using {api_type.upper()} endpoint")
        print("=" * 60)
        print(f"Image encode time:      {encode_time:.3f} s")
        print(f"Inference time (HTTP):  {inference_time:.3f} s")
        print(f"Total time:             {encode_time + inference_time:.3f} s")
        print(f"Output tokens:          {output_tokens}")
        print(f"Throughput:             {tps:.2f} tokens/s")
        print("=" * 60)
        print("RESPONSE PREVIEW:")
        print(content[:500] + ("..." if len(content) > 500 else ""))
        print("=" * 60)

        # Save full output
        if api_type == "local":
            with open("vlm_output_local.json", "w") as f:
                json.dump(content, f, indent=4)
        elif api_type == "cloud":
            with open("vlm_output_cloud.json", "w") as f:
                json.dump(content, f, indent=4)

    except (KeyError, IndexError) as e:
        print("Unexpected response format:", e)
        print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimized VLM inference")
    # from backend.routers.applications import router as applications_router
    from dotenv import load_dotenv

    # 1. LOAD THE .ENV FILE FIRST
    # This makes sure os.environ is populated before anything else happens.
    load_dotenv()

    parser.add_argument(
        "--api-type",
        choices=["local", "cloud"],
        default="local",
        help="Use local NIM or cloud API (default: local)",
    )
    parser.add_argument("--user_msg", help="Path to the input image")
    parser.add_argument("--sys_msg", help="System prompt", nargs="?", default=None)
    parser.add_argument(
        "--image_path", help="Path to the image", nargs="?", default=None
    )
    args = parser.parse_args()
    run_inference(args.api_type, args.user_msg)
