"""
backend/services/review_service.py
===================================
Post-submission permit review: 4-agent CrewAI crew streaming via threading.Queue.

Agents: Intake Specialist (5 tasks) → Code Enforcement → Zoning & Site Planner → Field Inspector
Each agent fires a task_callback that posts ReviewProgressEvent to a queue.
The SSE generator drains that queue and yields events to the HTTP response.
"""

import json
import queue
import re
import threading
from typing import Generator

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
)
from backend.tools.nim_llm import create_nim_llm
from backend.austin import *


# ─────────────────────────────────────────────
#  Shared LLM
# ─────────────────────────────────────────────

def _llm():
    return create_nim_llm()


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
        "zoning_district": "SF-3",
        "overlay": "Residential",
        "max_impervious_cover_pct": 45,
        "max_height_ft": 35,
        "min_front_setback_ft": 25,
        "min_rear_setback_ft": 10,
        "min_side_setback_ft": 5,
        "far": 0.4,
        "source": "Austin Land Development Code §25-2 (dummy data)",
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
        "source": "City of Austin Development Services Department (dummy data)",
    })


# ── Agent metadata — 8 tasks total ────────────────────────────────────────────

AGENT_META = [
    {"key": "blueprint",      "name": "Intake: Blueprint Analysis", "icon": "🖼️",  "desc": "Intake agent running AI vision analysis on uploaded blueprint drawings."},
    {"key": "photos",         "name": "Intake: Photo Review",       "icon": "📷",  "desc": "Intake agent reviewing submitted site photos for compliance."},
    {"key": "zoning_lookup",  "name": "Intake: Zoning Lookup",      "icon": "🗂️",  "desc": "Intake agent fetching zoning classification for the project address."},
    {"key": "permit_history", "name": "Intake: Permit History",     "icon": "📜",  "desc": "Intake agent retrieving past permit records for this address."},
    {"key": "intake",         "name": "Intake: Document Check",     "icon": "📋",  "desc": "Intake agent verifying document completeness against DSD IHB150 requirements."},
    {"key": "code",           "name": "Code Enforcement",           "icon": "📐",  "desc": "Cross-referencing blueprint measurements against IRC 2021."},
    {"key": "planner",        "name": "Zoning & Site Planner",      "icon": "🗺️",  "desc": "Auditing site data against Austin LDC §25 zoning rules."},
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
    return {
        "address":            row["project_address"]          or "Unknown address",
        "scope_of_work":      row["sow_text"]                 or "No scope of work provided.",
        "owner":              row["owner_name"]               or "",
        "application_type":   row["application_type"]         or "",
        "zoning_type":        row["zoning_type"]              or "SF-3",
        "square_footage":     row.get("project_size_sqft")    or "unknown sqft",
        "zoning_and_overlay": row["zoning_type"]              or "SF-3",
        "impervious_cover":   row.get("impervious_cover")     or "unknown",
    }


def _fetch_blueprint_context(app_id: int) -> str:
    """
    Run vision analysis ahead of crew kickoff and return a formatted
    string to embed in the intake agent's blueprint task description.
    """
    try:
        result = analyse_blueprint(app_id)
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
) -> tuple[Crew, list[str]]:

    sow     = app_data.get("scope_of_work", "")
    address = app_data.get("address", "unknown")
    sq_ft   = app_data.get("square_footage", "unknown sqft")
    zoning  = app_data.get("zoning_and_overlay", "SF-3")
    imp_cov = app_data.get("impervious_cover", "unknown")

    # ── Agents ────────────────────────────────────────────────────────────────
    intake = Agent(
        role="Intake Specialist",
        goal=(
            "Ensure all required Austin permit docs are present, "
            "interpret blueprint vision findings, review submitted site photos, "
            "look up zoning for the project address, and retrieve past permit history."
        ),
        backstory=(
            "You are the first line of defense at the Austin Development Services Department. "
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
        goal="Audit blueprints for IRC violations (railing height, ceiling height).",
        backstory="You cross-reference blueprint measurements against the IRC 2021 standards.",
        llm=llm, verbose=True, allow_delegation=False,
    )
    zoning_agent = Agent(
        role="Zoning & Site Planner",
        goal="Verify compliance with Austin LDC §25 zoning rules including impervious cover limits.",
        backstory="Licensed TX landscape architect specializing in Austin SF-3, SF-6, and MF districts.",
        llm=llm, verbose=True, allow_delegation=False,
    )
    inspector_agent = Agent(
        role="Field Inspector",
        goal="Review site photos for unpermitted structures and safety hazards.",
        backstory="Veteran Austin DSD field inspector with 5,000+ site inspections.",
        llm=llm, verbose=True, allow_delegation=False,
    )

    # ── Intake Task 1: Blueprint Analysis ─────────────────────────────────────
    task_blueprint = Task(
        description=(
            f"You are reviewing the uploaded blueprint for permit application at {address}.\n\n"
            "The following findings were produced by an automated AI vision scan of the blueprint:\n\n"
            f"{blueprint_context}\n\n"
            "Interpret these findings, flag any IRC violations or warnings, "
            "and produce a structured compliance report.\n\n"
            "Key IRC checks:\n"
            "  - Ceiling height ≥ 7 ft habitable rooms (IRC R305.1)\n"
            "  - Railing height ≥ 36 in (IRC R312.1.2)\n"
            "  - Egress window ≥ 5.7 sq ft clear opening (IRC R310.2)\n"
            "  - Room width ≥ 7 ft (IRC R304.3)\n"
            "  - Hallway width ≥ 36 in (IRC R311.6)\n"
            "  - Stair width ≥ 36 in (IRC R311.7.1)\n\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=intake,
    )

    # ── Intake Task 2: Photo Review ────────────────────────────────────────────
    photo_summary = (
            f"{len(photo_paths)} photo(s) submitted:\n" +
            "\n".join(f"  - {os.path.basename(p)}" for p in photo_paths)
            if photo_paths
            else "No photos have been uploaded for this application."
        )

    task_photos = Task(
        description=(
            f"You are reviewing the submitted site photos for permit application at {address}.\n\n"
            f"Scope of Work: {sow}\n\n"
            f"Submitted photos:\n{photo_summary}\n\n"
            "Assess:\n"
            "  - Are a minimum of 3 site photos submitted? (currently: {len(photo_paths)})\n"
            "  - Do the filenames/count suggest: existing structure, site boundaries, "
            "    drainage, any trees >19in diameter (heritage tree permit required)?\n"
            "  - Flag any expected photo evidence that appears to be missing.\n"
            "  - If 0 photos uploaded, flag as a blocker — photos are mandatory.\n\n"
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
    task_intake = Task(
        description=(
            f"Review the permit application for {address}.\n"
            f"Scope of Work:\n{sow}\n\n"
            "Check: fire egress plan (IRC R310), engineer stamp (if load-bearing walls), "
            "energy compliance docs, TDLR license numbers.\n\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=intake,
    )

    # ── Code Enforcement Task ──────────────────────────────────────────────────
    task_code = Task(
        description=(
            f"Audit the blueprint for {address} — {sq_ft}.\n\n"
            "IRC 2021 checks: ceiling height min 7ft (R305.1), railing height min 36in (R312.1.2), "
            "egress window min 5.7 sq ft (R310.2), smoke detectors (R314), CO detectors (R315), "
            "bathroom ventilation 50 CFM (M1507.4).\n\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=code_agent,
    )

    # ── Zoning & Site Planner Task ─────────────────────────────────────────────
    task_zoning = Task(
        description=(
            f"Zoning audit for {address}. Zoning: {zoning}. Impervious cover: {imp_cov}.\n\n"
            "LDC §25-2 checks: impervious cover (SF-3 max 45%), setbacks (front 25ft, rear 10ft, sides 5ft), "
            "max height 35ft, FAR 0.4, tree permit (>19in diameter).\n\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=zoning_agent,
    )

    # ── Field Inspector Task ───────────────────────────────────────────────────
    task_inspection = Task(
        description=(
            f"Site inspection review for {address}.\n\n"
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


def _run_crew_in_thread(app_id: int, event_queue: queue.Queue) -> None:
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
        blueprint_context = _fetch_blueprint_context(app_id)
        photo_paths = _get_photo_paths(app_id)

        # 3. Build crew with blueprint context injected into task description
        llm = _llm()
        crew, _ = _build_crew_and_tasks(app_id, app_data, blueprint_context, photo_paths, llm)

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


def stream_review(app_id: int) -> Generator[ReviewProgressEvent, None, None]:
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