"""
blueprint_service.py
====================
Visual reasoning on uploaded blueprints using NVIDIA NIM Gemma 3 27B IT.

Model:   google/gemma-3-27b-it   (multimodal, vision-capable)
Endpoint: https://integrate.api.nvidia.com/v1   (OpenAI-compat)

Flow
────
1. Receive raw blueprint bytes (PDF or image)
2. If PDF → convert first page to PNG via PyMuPDF (fitz)
3. Encode to base64
4. Send to Gemma 3 27B IT with a structured audit prompt
5. Parse JSON findings from model response
6. Persist to blueprint_analysis table
7. Return structured BlueprintAnalysisResult

Austin IRC checks the model is asked to perform
────────────────────────────────────────────────
• Ceiling height ≥ 7 ft habitable rooms (IRC R305.1)
• Stair/deck railing height ≥ 36 in (IRC R312.1.2)
• Egress window clear opening ≥ 5.7 sq ft (IRC R310.2)
• Minimum room width 7 ft (IRC R304.3)
• Hallway width ≥ 36 in (IRC R311.6)
• Stair width ≥ 36 in (IRC R311.7.1)
• Any visible dimension annotation flagged against minimums
"""

import base64
import io
import json
import os
import re
from dataclasses import dataclass

import openai

from backend.models.database import (
    get_blueprint_bytes,
    save_blueprint_analysis,
    get_blueprint_analysis,
)

from backend.tools.nim_llm import create_nim_llm
from backend.austin import *


# ─────────────────────────────────────────────
#  Shared LLM  (all agents use same NIM model)
# ─────────────────────────────────────────────


def _llm():
    return create_nim_llm()

UPLOAD_ROOT = "uploads"

def _get_blueprint_path(app_id: int) -> tuple[bytes, str]:
    """
    Read the first file found in uploads/{app_id}/blueprint/.
    Returns (raw_bytes, mime_type).
    Raises RuntimeError if folder is empty or missing.
    """
    blueprint_dir = os.path.join(UPLOAD_ROOT, str(app_id), "blueprint")
    if not os.path.isdir(blueprint_dir):
        raise RuntimeError(f"No blueprint folder found for app_id={app_id}.")

    files = [
        f for f in os.listdir(blueprint_dir)
        if not f.startswith(".")
    ]
    if not files:
        raise RuntimeError(f"Blueprint folder is empty for app_id={app_id}.")

    filepath = os.path.join(blueprint_dir, files[0])
    ext = os.path.splitext(files[0])[1].lower()
    mime_map = {
        ".pdf":  "application/pdf",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    mime = mime_map.get(ext, "image/png")

    with open(filepath, "rb") as f:
        return f.read(), mime

# ── PDF → PNG conversion ───────────────────────────────────────────────────────

def _pdf_first_page_to_png(pdf_bytes: bytes) -> bytes:
    """
    Rasterise the first page of a PDF to PNG bytes.
    Requires: pip install PyMuPDF
    Falls back gracefully if PyMuPDF is not installed.
    """
    try:
        import fitz  # PyMuPDF
        doc  = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        mat  = fitz.Matrix(2.0, 2.0)   # 2× zoom → ~144 DPI, legible for LLM
        pix  = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    except ImportError:
        raise RuntimeError(
            "PyMuPDF is required for PDF blueprints. "
            "Install with: pip install PyMuPDF"
        )


def _to_base64_png(raw_bytes: bytes, mime: str) -> tuple[str, str]:
    """
    Returns (base64_string, 'image/png').
    Converts PDF to PNG first if needed.
    """
    if mime == "application/pdf":
        img_bytes = _pdf_first_page_to_png(raw_bytes)
    elif mime in ("image/jpeg", "image/jpg"):
        # Convert JPEG → PNG for consistency (Gemma handles both, but PNG is lossless)
        try:
            from PIL import Image
            buf = io.BytesIO()
            Image.open(io.BytesIO(raw_bytes)).save(buf, format="PNG")
            img_bytes = buf.getvalue()
        except ImportError:
            img_bytes = raw_bytes   # fallback: send as-is
            mime      = "image/jpeg"
            return base64.b64encode(img_bytes).decode(), mime
    else:
        img_bytes = raw_bytes   # already PNG

    return base64.b64encode(img_bytes).decode(), "image/png"


# ── Prompt ─────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a certified ICC Building Inspector and licensed Texas architect
performing visual plan review for the Austin Development Services Department.
You have 20 years of experience auditing residential blueprints against the
2021 IRC as adopted by Austin, Texas.

Your task is to analyse the provided blueprint image and identify any
dimension annotations, measurements, labels, or visual indicators that
relate to building code compliance.

You must respond ONLY with a JSON object — no markdown, no preamble, no explanation.

JSON schema:
{
  "overall_assessment": "<2-3 sentence summary of the blueprint's compliance posture>",
  "dimensions_found": [
    {
      "element": "<architectural element, e.g. 'Master bedroom ceiling'>",
      "measured_value": "<value as shown on blueprint, e.g. '6\\'10\\"'>",
      "code_minimum": "<applicable IRC minimum, e.g. '7\\'-0\\" (IRC R305.1)'>",
      "status": "<one of: pass | warning | violation | not_visible>",
      "detail": "<one sentence explanation>"
    }
  ],
  "items_not_visible": ["<list of required elements not annotated or readable in this image>"],
  "recommendation": "<one sentence overall recommendation>"
}

If a required dimension is not legible or not shown, set status to 'not_visible' and
add the element to items_not_visible. Do NOT invent measurements that are not visible.
"""

_USER_PROMPT = """Please analyse this Austin, TX residential building permit blueprint.

Check for these code-required dimensions and annotations:
1. Ceiling height in all habitable rooms — minimum 7 ft (IRC R305.1)
2. Stair and deck railing height — minimum 36 in (IRC R312.1.2)
3. Egress window annotations — net clear area minimum 5.7 sq ft (IRC R310.2)
4. Room widths — minimum 7 ft (IRC R304.3)
5. Hallway widths — minimum 36 in (IRC R311.6)
6. Stair width — minimum 36 in (IRC R311.7.1)
7. Any other dimension annotations visible in the drawing

Report every dimension you can read from the blueprint.
Remember: respond ONLY with the JSON object."""


# ── Main analysis function ─────────────────────────────────────────────────────

@dataclass
class BlueprintAnalysisResult:
    app_id:             int
    overall_assessment: str
    dimensions_found:   list[dict]
    items_not_visible:  list[str]
    recommendation:     str
    raw_response:       str
    from_cache:         bool = False


def analyse_blueprint(app_id: int, force_refresh: bool = False) -> BlueprintAnalysisResult:
    """
    Run Gemma 3 27B IT visual analysis on the stored blueprint.
    Results are cached in blueprint_analysis table — subsequent calls return cache
    unless force_refresh=True.

    Raises RuntimeError if no blueprint is stored or NIM key is missing.
    """
    # ── Check cache ───────────────────────────────────────────────────────────
    if not force_refresh:
        cached = get_blueprint_analysis(app_id)
        if cached:
            findings = cached["findings"]
            return BlueprintAnalysisResult(
                app_id             = app_id,
                overall_assessment = findings.get("overall_assessment", ""),
                dimensions_found   = findings.get("dimensions_found", []),
                items_not_visible  = findings.get("items_not_visible", []),
                recommendation     = findings.get("recommendation", ""),
                raw_response       = cached["raw_response"],
                from_cache         = True,
            )

    # ── Fetch blueprint bytes ─────────────────────────────────────────────────
    #raw_bytes, mime = get_blueprint_bytes(app_id)
    raw_bytes, mime = _get_blueprint_path(app_id)
    if not raw_bytes:
        raise RuntimeError(
            f"No blueprint found for app_id={app_id}. "
            "Ensure the file was uploaded and stored correctly."
        )

    # ── Convert to base64 PNG ─────────────────────────────────────────────────
    b64_image, img_mime = _to_base64_png(raw_bytes, mime)

    # ── Call NVIDIA NIM Gemma 3 27B IT ────────────────────────────────────────
    client = openai.OpenAI(base_url=NIM_BASE_URL, api_key=_nim_api_key())

    response = client.chat.completions.create(
        model=GEMMA_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img_mime};base64,{b64_image}",
                        },
                    },
                    {"type": "text", "text": _USER_PROMPT},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=2048,
    )

    raw_text = response.choices[0].message.content.strip()

    # ── Parse JSON ────────────────────────────────────────────────────────────
    findings = _parse_analysis(raw_text)

    # ── Persist ───────────────────────────────────────────────────────────────
    save_blueprint_analysis(app_id, raw_text, findings)

    return BlueprintAnalysisResult(
        app_id             = app_id,
        overall_assessment = findings.get("overall_assessment", ""),
        dimensions_found   = findings.get("dimensions_found", []),
        items_not_visible  = findings.get("items_not_visible", []),
        recommendation     = findings.get("recommendation", ""),
        raw_response       = raw_text,
        from_cache         = False,
    )


def _parse_analysis(raw: str) -> dict:
    """Robustly extract JSON from the model response."""
    text = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object via regex
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Last resort: return raw text wrapped in a generic finding
    return {
        "overall_assessment": "Blueprint received. Manual parse required.",
        "dimensions_found": [{
            "element":        "Full blueprint",
            "measured_value": "See raw response",
            "code_minimum":   "N/A",
            "status":         "not_visible",
            "detail":         raw[:300],
        }],
        "items_not_visible": [],
        "recommendation": "Manual review required — model response was not parseable JSON.",
    }


# ── Convenience: blueprint findings as AgentFinding-compatible dicts ───────────

def blueprint_findings_to_agent_findings(result: BlueprintAnalysisResult) -> list[dict]:
    """
    Convert BlueprintAnalysisResult.dimensions_found into the same dict shape
    as AgentFinding so the review crew can include them in the findings table.
    """
    severity_map = {
        "pass":        "pass",
        "warning":     "warning",
        "violation":   "violation",
        "not_visible": "warning",
    }
    out = []
    for d in result.dimensions_found:
        out.append({
            "agent":    "Blueprint Vision",
            "finding":  f"{d.get('element', 'Element')}: {d.get('measured_value', 'N/A')}",
            "severity": severity_map.get(d.get("status", "warning"), "warning"),
            "detail":   d.get("detail", ""),
        })
    return out
