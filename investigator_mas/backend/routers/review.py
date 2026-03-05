"""
backend/routers/review.py

GET /review/{app_id}/stream   →  SSE stream of ReviewProgressEvent
GET /review/{app_id}/results  →  stored ReviewResult
GET /review/agents/meta       →  static agent card metadata
"""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.models.schemas import (
    AgentFinding, FindingSeverity, ReviewProgressEvent, ReviewResult, WorkflowStatus,
)
from backend.models.database import get_review_findings, get_application_by_id
from backend.services.review_service import stream_review, AGENT_META
from backend.services.auth_service import get_current_user

router = APIRouter(prefix="/review", tags=["review"])


async def _sse_stream(app_id: int, app_data: dict) -> AsyncGenerator[str, None]:
    for event in stream_review(app_id, app_data):
        yield f"data: {json.dumps(event.model_dump())}\n\n"


@router.get("/{app_id}/stream")
async def review_stream(
    app_id:   int,
    app_data: str = Query(..., description="URL-encoded JSON of application data"),
    _user:    dict = Depends(get_current_user),
):
    return StreamingResponse(
        _sse_stream(app_id, json.loads(app_data)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{app_id}/results", response_model=ReviewResult)
def get_results(app_id: int, _user: dict = Depends(get_current_user)):
    rows = get_review_findings(app_id)
    if not rows:
        raise HTTPException(404, f"No review findings for app_id={app_id}.")

    findings = [
        AgentFinding(
            agent=r["agent"], finding=r["finding"],
            severity=FindingSeverity(r["severity"]), detail=r["detail"],
        )
        for r in rows
    ]
    deductions = {"critical": 25, "violation": 15, "follow-up": 8, "warning": 4, "pass": 0}
    score   = max(0, 100 - sum(deductions.get(f.severity.value, 0) for f in findings))
    app_row = get_application_by_id(app_id)
    if not app_row:
        raise HTTPException(404, f"Application {app_id} not found.")

    return ReviewResult(
        app_id           = app_id,
        permit_id        = app_row["permit_id"] or "",
        findings         = findings,
        compliance_score = score,
        workflow_status  = WorkflowStatus(app_row["workflow_status"] or "Submitted"),
        stage            = app_row["stage"] or "",
    )


@router.get("/agents/meta")
def agent_meta(_user: dict = Depends(get_current_user)):
    return AGENT_META
