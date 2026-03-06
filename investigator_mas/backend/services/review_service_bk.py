"""
backend/services/review_service.py
===================================
Post-submission permit review: 4-agent CrewAI crew streaming via threading.Queue.

Agents: Intake Specialist → Code Enforcement → Zoning & Site Planner → Field Inspector
Each agent fires a task_callback that posts ReviewProgressEvent to a queue.
The SSE generator drains that queue and yields events to the HTTP response.
"""

import json
import os
import queue
import re
import threading
from typing import Generator

import openai
from crewai import Agent, Crew, Process, Task, LLM
from crewai.tasks.task_output import TaskOutput

from backend.models.schemas import AgentFinding, FindingSeverity, ReviewProgressEvent
from backend.models.database import (
    upsert_application_status,
    save_review_findings,
    set_workflow_status,
)
from backend.services.blueprint_service import (
    analyse_blueprint,
    blueprint_findings_to_agent_findings,
)

from backend.tools.nim_llm import create_nim_llm
from backend.austin import *


# ─────────────────────────────────────────────
#  Shared LLM  (all agents use same NIM model)
# ─────────────────────────────────────────────


def _llm():
    return create_nim_llm()

# ── Agent metadata (consumed by frontend for pre-rendering cards) ──────────────

AGENT_META = [
    {"key": "intake",    "name": "Intake Specialist",     "icon": "📋", "desc": "Verifying document completeness against DSD IHB150 requirements."},
    {"key": "code",      "name": "Code Enforcement",      "icon": "📐", "desc": "Cross-referencing blueprint measurements against IRC 2021."},
    {"key": "planner",   "name": "Zoning & Site Planner", "icon": "🗺️",  "desc": "Auditing site data against Austin LDC §25 zoning rules."},
    {"key": "inspector", "name": "Field Inspector",        "icon": "🔍", "desc": "Reviewing site photos for unpermitted structures and safety hazards."},
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
    "pass": FindingSeverity.PASS, "warning": FindingSeverity.WARNING,
    "violation": FindingSeverity.VIOLATION, "critical": FindingSeverity.CRITICAL,
    "follow-up": FindingSeverity.FOLLOWUP, "followup": FindingSeverity.FOLLOWUP,
}

_AGENT_DISPLAY = {"intake": "Intake", "code": "Code", "planner": "Planner", "inspector": "Inspector"}


def _parse_findings(raw: str, agent_key: str) -> list[AgentFinding]:
    try:
        text = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        data = json.loads(text)
        return [
            AgentFinding(
                agent    = _AGENT_DISPLAY.get(agent_key, agent_key.title()),
                finding  = f.get("finding", "Unknown"),
                severity = _SEVERITY_MAP.get(f.get("severity", "warning").lower().replace(" ", "-"), FindingSeverity.WARNING),
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
    deductions = {FindingSeverity.CRITICAL: 25, FindingSeverity.VIOLATION: 15,
                  FindingSeverity.FOLLOWUP: 8, FindingSeverity.WARNING: 4, FindingSeverity.PASS: 0}
    return max(0, 100 - sum(deductions.get(f.severity, 0) for f in findings))


# ── Crew builder ───────────────────────────────────────────────────────────────

def _build_crew_and_tasks(app_data: dict, llm: LLM) -> tuple[Crew, list[str]]:
    sow     = app_data.get("scope_of_work", "")
    address = app_data.get("address", "unknown")
    sq_ft   = app_data.get("square_footage", "800 sqft addition")
    zoning  = app_data.get("zoning_and_overlay", "SF-3")
    imp_cov = app_data.get("impervious_cover", "44.2%")

    intake = Agent(
        role="Intake Specialist",
        goal="Ensure all required Austin permit docs are present including fire egress.",
        backstory="You are the first line of defense at the Austin Development Services Department.",
        llm=llm, verbose=True, allow_delegation=False,
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

    task_intake = Task(
        description=(
            f"Review the permit application for {address}.\n"
            f"Scope of Work:\n{sow}\n\n"
            "Check: fire egress plan (IRC R310), engineer stamp (if load-bearing walls), "
            "energy compliance docs, site photos (min 3), TDLR license numbers.\n\n"
            + _FINDING_JSON_SCHEMA
        ),
        expected_output="JSON object with summary and findings array.",
        agent=intake,
    )
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

    task_keys = ["intake", "code", "planner", "inspector"]

    crew = Crew(
        agents=[intake, code_agent, zoning_agent, inspector_agent],
        tasks=[task_intake, task_code, task_zoning, task_inspection],
        process=Process.sequential,
        verbose=True, memory=False, output_log_file=False,
    )
    return crew, task_keys


# ── Thread worker ──────────────────────────────────────────────────────────────

_SENTINEL = object()


def _run_crew_in_thread(app_id: int, app_data: dict, event_queue: queue.Queue) -> None:
    all_findings: list[AgentFinding] = []
    task_keys = ["intake", "code", "planner", "inspector"]
    completed = [0]
    upsert_application_status(
            app_id=app_id,
            workflow_status="Pending",
            stage="Review In Progress",
            status_message="Automated review started — agents running.",
            compliance_score=0,
        )

    try:
        llm  = _llm()
        crew, _ = _build_crew_and_tasks(app_data, llm)

        # Patch task callbacks after crew is built
        for i, task in enumerate(crew.tasks):
            idx = i  # capture

            def make_callback(task_idx):
                def on_done(output: TaskOutput) -> None:
                    agent_key = task_keys[task_idx] if task_idx < len(task_keys) else "unknown"
                    completed[0] += 1
                    findings = _parse_findings(output.raw, agent_key)
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

            task.callback = make_callback(idx)

        # Announce first agent
        event_queue.put(ReviewProgressEvent(
            event_type="agent_start", agent_name=AGENT_META[0]["name"],
            agent_index=0, message=AGENT_META[0]["desc"],
        ))

        crew.kickoff()

        # ## Append Gemma 3 blueprint findings
        # try:
        #     ph_result   = analyse_photos(app_id)
        #     ph_raw_fds  = photo_findings_to_agent_findings(bp_result)
        #     for f in ph_raw_fds:
        #         all_findings.append(AgentFinding(
        #             agent=f["agent"], finding=f["finding"],
        #             severity=FindingSeverity(f["severity"]), detail=f["detail"],
        #         ))

        #     bp_result   = analyse_blueprint(app_id)
        #     bp_raw_fds  = blueprint_findings_to_agent_findings(bp_result)
        #     for f in bp_raw_fds:
        #         all_findings.append(AgentFinding(
        #             agent=f["agent"], finding=f["finding"],
        #             severity=FindingSeverity(f["severity"]), detail=f["detail"],
        #         ))
        # except Exception:
        #     pass

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
            app_id=app_id, workflow_status="Pending",
            stage=stage_label,
            status_message=f"Review complete: {len(all_findings)} findings.",
            compliance_score=score,
        )
        
        upsert_application_status(
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
        upsert_application_status(
            app_id=app_id,
            workflow_status="Pending",
            stage="Review Failed",
            status_message=f"Review error: {str(exc)[:200]}",
            compliance_score=0,
        )
        event_queue.put(ReviewProgressEvent(
            event_type="error", agent_name="System", agent_index=-1,
            message=f"Crew error: {exc}",
        ))
    finally:
        event_queue.put(_SENTINEL)


def stream_review(app_id: int, app_data: dict) -> Generator[ReviewProgressEvent, None, None]:
    """Launch crew in background thread; yield events as they arrive."""
    q = queue.Queue()
    threading.Thread(target=_run_crew_in_thread, args=(app_id, app_data, q), daemon=True).start()

    while True:
        try:
            item = q.get(timeout=120)
        except queue.Empty:
            yield ReviewProgressEvent(event_type="error", agent_name="System",
                                      agent_index=-1, message="Timeout waiting for agent.")
            break
        if item is _SENTINEL:
            break
        yield item
