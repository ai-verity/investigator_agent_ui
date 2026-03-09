"""
backend/services/review_service.py
===================================
Post-submission permit review: 4-agent CrewAI crew streaming via threading.Queue.

Agents: Intake Specialist (5 tasks) → Code Enforcement → Zoning & Site Planner → Field Inspector
Each agent fires a task_callback that posts ReviewProgressEvent to a queue.
The SSE generator drains that queue and yields events to the HTTP response.
"""

import json
import os       
import queue
import re
import threading
from typing import Generator
import time                          # ← ADD
import base64                        # ← ADD
from typing import Generator

import requests                      # ← ADD
from requests.adapters import HTTPAdapter   # ← ADD
from urllib3.util.retry import Retry        # ← ADD

from crewai import Agent, Crew, Process, Task, LLM
from crewai.tasks.task_output import TaskOutput
from crewai.tools import tool
from pydantic import BaseModel

from backend.models.schemas import AgentFinding, FindingSeverity, ReviewProgressEvent
from backend.models.database import (
    save_review_findings,
    set_workflow_status,
    get_application_by_id,
)
from backend.services.blueprint_service import (
    analyse_blueprint,
    blueprint_findings_to_agent_findings,
    _SYSTEM_PROMPT as system_message,
    _USER_PROMPT as user_message,
)
from backend.tools.nim_llm import create_nim_llm
from common import get_city, get_city_or_none, CITY_ALIASES, list_cities


# ─────────────────────────────────────────────
#  Shared LLM
# ─────────────────────────────────────────────

def _llm():
    return create_nim_llm()


def _detect_city_from_address(address: str) -> str:
    """Extract city slug from a project_address string. Falls back to 'austin'."""
    addr_lower = address.lower()
    for alias, slug in sorted(CITY_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in addr_lower:
            return slug
    for slug in list_cities():
        if slug.replace("_", " ") in addr_lower:
            return slug
    return "austin"

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def run_inference(image_path, api_type="local", city_slug="austin"):
    cfg = get_city(city_slug)
    model_name = os.getenv("MODEL_NAME", "qwen3.5-35b")

    if api_type == "local":
        base_url = os.getenv("LOCAL_NIM_URL", "http://localhost:8000/v1")
        headers = {"Content-Type": "application/json"}
        api_key = None
    else:
        base_url = os.getenv("CLOUD_NIM_URL", "https://integrate.api.nvidia.com/v1")
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise ValueError("NVIDIA_API_KEY environment variable not set for cloud inference")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

    encode_start = time.time()
    base64_image = encode_image(image_path)
    encode_time = time.time() - encode_start

    tree_note = ""
    for note in (cfg.general_notes or []):
        if "tree" in note.lower():
            tree_note = note
            break

    PHOTO_SYSTEM_PROMPT = f"""
    You are a licensed field inspector performing a site photo review
    for a residential permit application in {cfg.city_name}, {cfg.state}.

    You have 20 years of experience identifying unpermitted structures, code violations,
    site hazards, and documentation gaps from site photographs.

    Output ONLY valid JSON. No explanations. No markdown. No extra text.

    Rules:
    - Only report what is clearly visible in the photo.
    - Do NOT assume or infer what is not visible.
    - If something is partially visible, note it as "partially visible".
    - Be specific about locations (front yard, backyard, left side, roof, etc.).
    """

    PHOTO_USER_PROMPT = f"""
    Analyze this site photograph of a residential property for permit compliance review
    in {cfg.city_name}, {cfg.state}.

    Observe and document everything visible including:

    STRUCTURES:
    - Main residence (condition, stories, additions visible)
    - Detached garages or carports
    - Storage sheds (size estimate, foundation type if visible)
    - Accessory dwelling units (ADUs) or guest houses
    - Pergolas, gazebos, covered patios
    - Fences and gates (height estimate, material)
    - Retaining walls
    - Pools or spas
    - Any structure that may have been added without a permit

    SITE CONDITIONS:
    - Lot boundaries and setbacks (any visible encroachments)
    - Driveways and impervious surfaces (concrete, pavers, asphalt)
    - Drainage patterns or ponding areas
    - Erosion or grading concerns

    TREES:
    - Large trees (estimate diameter). {tree_note}
    - Trees near proposed construction zone
    - Recently removed stumps

    SAFETY CONCERNS:
    - Exposed electrical (visible wiring, panels, meters)
    - Structural concerns (visible cracking, leaning, deterioration)
    - Hazardous materials indicators (old roofing, pipe insulation visible)
    - Work-in-progress without visible permits posted

    GENERAL:
    - Overall property condition (well-maintained / deteriorated)
    - Any visible permit notices or stop-work orders posted
    - Evidence of recent construction activity

    Return EXACTLY this JSON:

    {{
    "photo_summary": "<2-3 sentence overall description of what is visible>",
    "structures_observed": [
        {{
        "type": "<structure type>",
        "description": "<what you see>",
        "location": "<where on property>",
        "estimated_size": "<size if estimable, else null>",
        "permit_concern": "<any permit concern or null>",
        "visibility": "clear | partial | unclear"
        }}
    ],
    "trees_observed": [
        {{
        "location": "<where on property>",
        "estimated_diameter_inches": "<number or null if unclear>",
        "heritage_tree_risk": true,
        "notes": "<any notes>"
        }}
    ],
    "site_conditions": {{
        "impervious_surfaces_observed": "<description or null>",
        "drainage_concerns": "<description or null>",
        "setback_concerns": "<description or null>",
        "overall_condition": "well-maintained | fair | deteriorated | unclear"
    }},
    "safety_concerns": [
        {{
        "concern": "<description>",
        "severity": "low | medium | high"
        }}
    ],
    "unpermitted_work_indicators": [
        "<description of anything that appears unpermitted>"
    ],
    "extraction_confidence": "high | medium | low",
    "notes": "<any other observations not captured above>"
    }}

    Return ONLY the JSON.
    """
    # Build payload 
    payload = {
    "model": model_name,
    "messages": [
        {
            "role": "system",
            "content": PHOTO_SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": PHOTO_USER_PROMPT
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        }
    ],
    "max_tokens": 4096,
    "temperature": 0.7,
            }

    url = f"{base_url.rstrip('/')}/chat/completions"

    # Use a session with connection pooling and retries
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    inference_start = time.time()
    try:
        response = session.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return
    inference_time = time.time() - inference_start

    result = response.json()
    try:
        #content = result["choices"][0]["message"]["content"]
        print("\nFULL RAW RESPONSE:\n")
        print(json.dumps(result, indent=2))

        content = result["choices"][0]["message"].get("content")
        usage = result.get("usage", {})
        output_tokens = usage.get("completion_tokens", 0)
        tps = output_tokens / inference_time if inference_time > 0 else 0

        print("\n" + "="*60)
        print(f"Inference using {api_type.upper()} endpoint")
        print("="*60)
        print(f"Image encode time:      {encode_time:.3f} s")
        print(f"Inference time (HTTP):  {inference_time:.3f} s")
        print(f"Total time:             {encode_time + inference_time:.3f} s")
        print(f"Output tokens:          {output_tokens}")
        print(f"Throughput:             {tps:.2f} tokens/s")
        print("="*60)
        print("RESPONSE PREVIEW:")
        print(content[:500] + ("..." if len(content) > 500 else ""))
        print("="*60)
        return content
        # Save full output
        # if api_type == "local":
        #     with open("vlm_output_local.json", "w") as f:
        #         json.dump(content, f, indent=4)
        # elif api_type == "cloud":
        #     with open("vlm_output_cloud.json", "w") as f:
        #         json.dump(content, f, indent=4)

    except (KeyError, IndexError) as e:
        print("Unexpected response format:", e)
        print(result)
# ── Dummy tool input schema ────────────────────────────────────────────────────

class PermitHistoryAgentInput(BaseModel):
    street_address: str
    city: str
    state: str
    zip_code: str
    unit_number: str | None
    owner_permit_docs: list[str]


# ── Dummy tools ────────────────────────────────────────────────────────────────

@tool("get_zoning_info")
def get_zoning_info(street_address: str) -> str:
    """
    Look up the zoning classification for a given street address.
    Returns the zoning district and any applicable overlays.
    """
    return json.dumps({
        "street_address": street_address,
        "zoning_district": "Residential",
        "overlay": "Residential",
        "max_impervious_cover_pct": 45,
        "max_height_ft": 35,
        "min_front_setback_ft": 25,
        "min_rear_setback_ft": 10,
        "min_side_setback_ft": 5,
        "far": 0.4,
        "source": "Zoning lookup (dummy data)",
    })


@tool("get_permit_history")
def get_permit_history(street_address: str) -> str:
    """
    Retrieve the permit history for a given street address.
    Returns a list of past permits with type, status, and dates.
    """
    return json.dumps({
        "street_address": street_address,
        "permit_history": [
            {
                "permit_number": "2018-012345",
                "permit_type": "New Construction",
                "description": "New single-family residential construction — 2,400 sq ft, 2 story",
                "status": "Finaled",
                "issued_date": "2018-03-15",
                "finaled_date": "2019-07-22",
                "contractor": "Austin Premier Builders LLC",
                "valuation_usd": 320000,
            },
            {
                "permit_number": "2020-045678",
                "permit_type": "Electrical",
                "description": "Panel upgrade — 100A to 200A service upgrade",
                "status": "Finaled",
                "issued_date": "2020-06-01",
                "finaled_date": "2020-06-18",
                "contractor": "Lone Star Electric Co.",
                "valuation_usd": 4500,
            },
            {
                "permit_number": "2022-089012",
                "permit_type": "Plumbing",
                "description": "Water heater replacement — tankless unit installation",
                "status": "Finaled",
                "issued_date": "2022-02-10",
                "finaled_date": "2022-02-14",
                "contractor": "Capitol Plumbing Services",
                "valuation_usd": 3200,
            },
            {
                "permit_number": "2023-112233",
                "permit_type": "Accessory Structure",
                "description": "Detached garage — 600 sq ft, slab foundation",
                "status": "Expired",
                "issued_date": "2023-04-01",
                "finaled_date": None,
                "contractor": "Owner-Builder",
                "valuation_usd": 45000,
            },
        ],
        "source": "Permit history lookup (dummy data)",
    })


# ── Agent metadata — 8 tasks total ────────────────────────────────────────────

AGENT_META = [
    {"key": "blueprint",      "name": "Intake: Blueprint Analysis", "icon": "🖼️",  "desc": "Intake agent running AI vision analysis on uploaded blueprint drawings."},
    {"key": "photos",         "name": "Intake: Photo Review",       "icon": "📷",  "desc": "Intake agent reviewing submitted site photos for compliance."},
    {"key": "zoning_lookup",  "name": "Intake: Zoning Lookup",      "icon": "🗂️",  "desc": "Intake agent fetching zoning classification for the project address."},
    {"key": "permit_history", "name": "Intake: Permit History",     "icon": "📜",  "desc": "Intake agent retrieving past permit records for this address."},
    {"key": "intake",         "name": "Intake: Document Check",     "icon": "📋",  "desc": "Intake agent verifying document completeness against DSD IHB150 requirements."},
    {"key": "code",           "name": "Code Enforcement",           "icon": "📐",  "desc": "Cross-referencing blueprint measurements against IRC 2021."},
    {"key": "planner",        "name": "Zoning & Site Planner",      "icon": "🗺️",  "desc": "Auditing site data against local zoning rules."},
    {"key": "inspector",      "name": "Field Inspector",             "icon": "🔍",  "desc": "Reviewing site photos for unpermitted structures and safety hazards."},
]

_FINDING_JSON_SCHEMA = """\
Return ONLY a JSON object — no markdown, no explanation. Schema:
{
  "summary": "<one sentence overall assessment>",
  "findings": [
    {
      "finding": "<short label, max 6 words>",
      "severity": "<one of: pass | warning | violation | critical | follow-up>",
      "detail": "<one sentence explaining the issue and the applicable code>"
    }
  ]
}
If everything is compliant: findings: [{"finding": "All checks passed", "severity": "pass", "detail": "<what was verified>"}]
"""

_SEVERITY_MAP = {
    "pass":      FindingSeverity.PASS,
    "warning":   FindingSeverity.WARNING,
    "violation": FindingSeverity.VIOLATION,
    "critical":  FindingSeverity.CRITICAL,
    "follow-up": FindingSeverity.FOLLOWUP,
    "followup":  FindingSeverity.FOLLOWUP,
}

_AGENT_DISPLAY = {
    "blueprint":      "Intake (Blueprint)",
    "photos":         "Intake (Photos)",
    "zoning_lookup":  "Intake (Zoning)",
    "permit_history": "Intake (Permit History)",
    "intake":         "Intake",
    "code":           "Code",
    "planner":        "Planner",
    "inspector":      "Inspector",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_findings(raw: str, agent_key: str) -> list[AgentFinding]:
    try:
        text = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(text)
        return [
            AgentFinding(
                agent    = _AGENT_DISPLAY.get(agent_key, agent_key.title()),
                finding  = f.get("finding", "Unknown"),
                severity = _SEVERITY_MAP.get(
                    f.get("severity", "warning").lower().replace(" ", "-"),
                    FindingSeverity.WARNING,
                ),
                detail   = f.get("detail", ""),
            )
            for f in data.get("findings", [])
        ]
    except Exception:
        return [AgentFinding(
            agent    = _AGENT_DISPLAY.get(agent_key, agent_key.title()),
            finding  = "Review complete (parse error)",
            severity = FindingSeverity.WARNING,
            detail   = raw[:200],
        )]


def _score_findings(findings: list[AgentFinding]) -> int:
    deductions = {
        FindingSeverity.CRITICAL:  25,
        FindingSeverity.VIOLATION: 15,
        FindingSeverity.FOLLOWUP:  8,
        FindingSeverity.WARNING:   4,
        FindingSeverity.PASS:      0,
    }
    return max(0, 100 - sum(deductions.get(f.severity, 0) for f in findings))


def _load_app_data(app_id: int) -> dict:
    row = get_application_by_id(app_id)
    if not row:
        raise RuntimeError(f"Application {app_id} not found in database.")
     # Convert sqlite3.Row to dict so .get() works safely
    row = dict(row)
    data = {
        "address":            row.get("project_address")       or "Unknown address",
        "scope_of_work":      row.get("sow_text")              or "No scope of work provided.",
        "owner":              row.get("owner_name")            or "",
        "application_type":   row.get("application_type")      or "",
        "zoning_type":        row.get("zoning_type")           or "SF-3",
        "square_footage":     row.get("project_size_sqft")     or "unknown sqft",
        "zoning_and_overlay": row.get("zoning_type")           or "SF-3",
        "impervious_cover":   row.get("impervious_cover")      or "unknown",
    }
    data["city"] = _detect_city_from_address(data["address"])
    return data


def _fetch_blueprint_context(app_id: int, city: str = "austin") -> str:
    """
    Run vision analysis ahead of crew kickoff and return a formatted
    string to embed in the intake agent's blueprint task description.
    """
    try:
        result = analyse_blueprint(app_id, city=city)
        findings_text = "\n".join(
            f"  - [{d['status'].upper()}] {d['element']}: "
            f"measured={d['measured_value']}, minimum={d['code_minimum']} — {d['detail']}"
            for d in result.dimensions_found
        )
        return (
            f"Overall assessment: {result.overall_assessment}\n"
            f"Dimension findings:\n{findings_text or '  (none detected)'}\n"
            f"Items not visible: {', '.join(result.items_not_visible) or 'none'}\n"
            f"Recommendation: {result.recommendation}"
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return f"Blueprint analysis unavailable: {exc}"

UPLOAD_ROOT = "uploads"

def _get_photo_paths(app_id: int) -> list[str]:
    """
    Return all photo file paths under uploads/{app_id}/photos/.
    Returns empty list if folder is missing or empty.
    """
    photo_dir = os.path.join(UPLOAD_ROOT, str(app_id), "photos")
    if not os.path.isdir(photo_dir):
        return []
    return [
        os.path.join(photo_dir, f)
        for f in sorted(os.listdir(photo_dir))
        if not f.startswith(".")
    ]
# ── Crew builder ───────────────────────────────────────────────────────────────

def _build_crew_and_tasks(
    app_id: int,
    app_data: dict,
    blueprint_context: str,
    photo_paths: list[str],  
    llm: LLM,
    city_slug: str = "austin",
) -> tuple[Crew, list[str]]:

    cfg     = get_city(city_slug)
    codes   = cfg.adopted_codes
    sow     = app_data.get("scope_of_work", "")
    address = app_data.get("address", "unknown")
    sq_ft   = app_data.get("square_footage", "unknown sqft")
    zoning  = app_data.get("zoning_and_overlay", "SF-3")
    imp_cov = app_data.get("impervious_cover", "unknown")

    res_zoning = cfg.zoning.get("residential")
    setbacks = res_zoning.setbacks if res_zoning else None

    ren = cfg.application_types.get("REN")
    code_checks_text = ""
    if ren and ren.code_references:
        for ref in ren.code_references[:7]:
            code_checks_text += f"  - {ref.summary} ({ref.code} {ref.section})\n"

    zoning_text = ""
    if res_zoning:
        if setbacks:
            zoning_text += f"setbacks (front {setbacks.front_ft}ft, rear {setbacks.rear_ft}ft, sides {setbacks.side_ft}ft), "
        if res_zoning.max_height_ft:
            zoning_text += f"max height {res_zoning.max_height_ft}ft, "
        if res_zoning.max_lot_coverage_pct:
            zoning_text += f"max lot coverage {res_zoning.max_lot_coverage_pct}%, "
        if res_zoning.max_far:
            zoning_text += f"FAR {res_zoning.max_far}, "

    city_label = f"{cfg.city_name}, {cfg.state}"

    # ── Agents ────────────────────────────────────────────────────────────────
    intake = Agent(
        role="Intake Specialist",
        goal=(
            f"Ensure all required {city_label} permit docs are present, "
            "interpret blueprint vision findings, review submitted site photos, "
            "look up zoning for the project address, and retrieve past permit history."
        ),
        backstory=(
            f"You are the first line of defense at the {city_label} permit office. "
            "You review documents, interpret automated blueprint scans, assess photo submissions, "
            "verify zoning classifications, and check permit history before forwarding to reviewers."
        ),
        llm=llm,
        tools=[get_zoning_info, get_permit_history],
        verbose=True,
        allow_delegation=False,
    )
    code_agent = Agent(
        role="Code Enforcement Official",
        goal=f"Audit blueprints for building code violations per {codes.residential}.",
        backstory=f"You cross-reference blueprint measurements against {codes.building} and {codes.residential}.",
        llm=llm, verbose=True, allow_delegation=False,
    )
    zoning_agent = Agent(
        role="Zoning & Site Planner",
        goal=f"Verify compliance with {city_label} zoning rules including setbacks and coverage limits.",
        backstory=f"Licensed planner specializing in {city_label} zoning districts.",
        llm=llm, verbose=True, allow_delegation=False,
    )
    inspector_agent = Agent(
        role="Field Inspector",
        goal="Review site photos for unpermitted structures and safety hazards.",
        backstory=f"Veteran {city_label} field inspector with 5,000+ site inspections.",
        llm=llm, verbose=True, allow_delegation=False,
    )

    # ── Intake Task 1: Blueprint Analysis ─────────────────────────────────────
    task_blueprint = Task(
        description=(
            f"You are reviewing the uploaded blueprint for permit application at {address} ({city_label}).\n\n"
            "The following findings were produced by an automated AI vision scan of the blueprint:\n\n"
            f"{blueprint_context}\n\n"
            "Interpret these findings, flag any code violations or warnings, "
            "and produce a structured compliance report.\n\n"
            f"Key code checks for {city_label}:\n"
            f"{code_checks_text}\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=intake,
    )

    # ── Intake Task 2: Photo Review ────────────────────────────────────────────
    if photo_paths:
        photo_results = []
        for photo in photo_paths:
            result = run_inference(photo, api_type="local", city_slug=city_slug)
            if result:
                photo_results.append(
                    f"--- {os.path.basename(photo)} ---\n{result}"
                )
        photo_summary = (
            f"{len(photo_paths)} photo(s) submitted and analyzed:\n\n" +
            "\n\n".join(photo_results)
            if photo_results
            else f"{len(photo_paths)} photo(s) submitted but analysis returned no results."
        )
    else:
        photo_summary = "No photos have been uploaded for this application."

    task_photos = Task(
        description=(
            f"You are reviewing the submitted site photos for permit application at {address} ({city_label}).\n\n"
            "The following AI vision analysis was performed on each submitted photo:\n\n"
            f"{photo_summary}\n\n"
            "Based on these photo analyses, produce a consolidated compliance findings report.\n"
            "Flag: unpermitted structures, setback concerns, protected trees, safety hazards, "
            "impervious cover issues, and any evidence of work started before permit.\n\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=intake,
    )

    # ── Intake Task 3: Zoning Lookup ───────────────────────────────────────────
    task_zoning_lookup = Task(
        description=(
            f"Use the get_zoning_info tool to look up the zoning classification "
            f"for the project address: {address}.\n\n"
            "Once you have the zoning data, assess:\n"
            "  - Is the proposed use (application type) permitted under this zoning district?\n"
            "  - Do the proposed setbacks, height, and impervious cover comply with the zoning rules?\n"
            "  - Are there any overlays or special districts that add requirements?\n"
            "  - Flag any mismatches between what was declared in the application and zoning limits.\n\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=intake,
    )

    # ── Intake Task 4: Permit History ──────────────────────────────────────────
    task_permit_history = Task(
        description=(
            f"Use the get_permit_history tool to retrieve the full permit history "
            f"for the project address: {address}.\n\n"
            "Once you have the history, assess:\n"
            "  - Are there any expired permits that suggest unpermitted work was started but not finaled?\n"
            "  - Does the prior construction history (e.g. past new construction permit) "
            "    affect what is required for the current application?\n"
            "  - Are there open or active permits that could conflict with this application?\n"
            "  - Note the age of the original construction (pre-1980 = asbestos risk flag).\n"
            "  - Flag any permits issued to Owner-Builder — these require additional scrutiny.\n\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=intake,
    )

    # ── Intake Task 5: Document Completeness ───────────────────────────────────
    doc_checks = ""
    if ren and ren.special_requirements:
        for req in ren.special_requirements[:5]:
            doc_checks += f"  - {req}\n"

    task_intake = Task(
        description=(
            f"Review the permit application for {address} ({city_label}).\n"
            f"Scope of Work:\n{sow}\n\n"
            f"Check these {city_label} requirements:\n{doc_checks}\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=intake,
    )

    # ── Code Enforcement Task ──────────────────────────────────────────────────
    task_code = Task(
        description=(
            f"Audit the blueprint for {address} — {sq_ft} ({city_label}).\n\n"
            f"Applicable codes: {codes.building}; {codes.residential}.\n"
            f"Key checks:\n{code_checks_text}\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=code_agent,
    )

    # ── Zoning & Site Planner Task ─────────────────────────────────────────────
    task_zoning = Task(
        description=(
            f"Zoning audit for {address} ({city_label}). Zoning: {zoning}. Impervious cover: {imp_cov}.\n\n"
            f"Zoning checks: {zoning_text}\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=zoning_agent,
    )

    # ── Field Inspector Task ───────────────────────────────────────────────────
    task_inspection = Task(
        description=(
            f"Site inspection review for {address} ({city_label}).\n\n"
            "Check: unpermitted structures, setback encroachments, work started before permit, "
            "drainage concerns, accessible parking compliance.\n\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=inspector_agent,
    )

    task_keys = ["blueprint", "photos", "zoning_lookup", "permit_history", "intake", "code", "planner", "inspector"]

    crew = Crew(
        agents=[intake, code_agent, zoning_agent, inspector_agent],
        tasks=[
            task_blueprint, task_photos, task_zoning_lookup,
            task_permit_history, task_intake,
            task_code, task_zoning, task_inspection,
        ],
        process=Process.sequential,
        verbose=True, memory=False, output_log_file=False,
    )
    return crew, task_keys


# ── Thread worker ──────────────────────────────────────────────────────────────

_SENTINEL = object()


def _run_crew_in_thread(app_id: str, event_queue: queue.Queue) -> None:
    all_findings: list[AgentFinding] = []
    task_keys = ["blueprint", "photos", "zoning_lookup", "permit_history", "intake", "code", "planner", "inspector"]

    try:
        # 1. Load app data from DB
        app_data = _load_app_data(app_id)

        # 2. Pre-fetch blueprint vision results and announce to frontend
        event_queue.put(ReviewProgressEvent(
            event_type="agent_start", agent_name=AGENT_META[0]["name"],
            agent_index=0, message="Running blueprint vision analysis…",
        ))
        city_slug = app_data.get("city", "austin")
        blueprint_context = _fetch_blueprint_context(app_id, city=city_slug)
        photo_paths = _get_photo_paths(app_id)

        # 3. Build crew with blueprint context injected into task description
        llm = _llm()
        crew, _ = _build_crew_and_tasks(app_id, app_data, blueprint_context, photo_paths, llm, city_slug=city_slug)

        # 4. Patch callbacks for all 8 tasks
        for i, task in enumerate(crew.tasks):
            def make_callback(task_idx):
                def on_done(output: TaskOutput) -> None:
                    agent_key = task_keys[task_idx]
                    findings  = _parse_findings(output.raw, agent_key)
                    all_findings.extend(findings)

                    event_queue.put(ReviewProgressEvent(
                        event_type=  "agent_done",
                        agent_name=  AGENT_META[task_idx]["name"],
                        agent_index= task_idx,
                        message=     f"{AGENT_META[task_idx]['name']} completed.",
                        finding=     findings[0] if findings else None,
                    ))

                    next_idx = task_idx + 1
                    if next_idx < len(AGENT_META):
                        event_queue.put(ReviewProgressEvent(
                            event_type=  "agent_start",
                            agent_name=  AGENT_META[next_idx]["name"],
                            agent_index= next_idx,
                            message=     AGENT_META[next_idx]["desc"],
                        ))
                return on_done
            task.callback = make_callback(i)

        crew.kickoff()

        # 5. Score & persist
        score = _score_findings(all_findings)
        worst = max(
            (f.severity for f in all_findings),
            key=lambda s: list(FindingSeverity).index(s),
            default=FindingSeverity.PASS,
        )
        stage_label = {
            FindingSeverity.CRITICAL:  "Critical Deficiencies Found",
            FindingSeverity.VIOLATION: "Violations Found — Corrections Required",
            FindingSeverity.FOLLOWUP:  "Follow-up Inspection Required",
            FindingSeverity.WARNING:   "Warnings — Review Required",
            FindingSeverity.PASS:      "Approved — Pending Final Sign-off",
        }.get(worst, "Review Complete")

        save_review_findings(app_id, [f.model_dump() for f in all_findings])
        set_workflow_status(
            app_id=app_id,
            workflow_status="Pending",
            stage=stage_label,
            status_message=f"Review complete: {len(all_findings)} findings.",
            compliance_score=score,
        )

        event_queue.put(ReviewProgressEvent(
            event_type="complete", agent_name="System", agent_index=-1,
            message="All agents completed review.",
            all_findings=all_findings, compliance_score=score,
        ))

    except Exception as exc:
        event_queue.put(ReviewProgressEvent(
            event_type="error", agent_name="System", agent_index=-1,
            message=f"Crew error: {exc}",
        ))
    finally:
        event_queue.put(_SENTINEL)


def stream_review(app_id: str) -> Generator[ReviewProgressEvent, None, None]:
    """Launch crew in background thread; yield events as they arrive."""
    q = queue.Queue()
    threading.Thread(target=_run_crew_in_thread, args=(app_id, q), daemon=True).start()

    while True:
        try:
            item = q.get(timeout=120)
        except queue.Empty:
            yield ReviewProgressEvent(
                event_type="error", agent_name="System",
                agent_index=-1, message="Timeout waiting for agent.",
            )
            break
        if item is _SENTINEL:
            break
        yield item  