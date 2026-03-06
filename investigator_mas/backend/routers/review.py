"""
backend/routers/review.py
"""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.models.schemas import (
    AgentFinding, FindingSeverity, ReviewProgressEvent, ReviewResult, WorkflowStatus,
)
from backend.models.database import get_review_findings, get_application_by_id
from backend.services.review_service import stream_review, AGENT_META
from backend.services.auth_service import get_current_user

router = APIRouter(prefix="/review", tags=["review"])

# @router.post("/{app_id}/photos")
# async def upload_photos(app_id: str, files: list[UploadFile] = File(...)):
#     _ensure_dirs(app_id)
#     saved = []
#     for file in files:
#         dest = os.path.join(UPLOAD_ROOT, app_id, "photos", file.filename)
#         with open(dest, "wb") as f:
#             shutil.copyfileobj(file.file, f)
#         saved.append(dest)
#     return JSONResponse({"uploaded": saved})


# @router.post("/{app_id}/blueprint")
# async def upload_blueprint(app_id: str, file: UploadFile = File(...)):
#     _ensure_dirs(app_id)
#     dest = os.path.join(UPLOAD_ROOT, app_id, "blueprint", file.filename)
#     with open(dest, "wb") as f:
#         shutil.copyfileobj(file.file, f)
#     return JSONResponse({"uploaded": dest})

def _build_review_result(app_id: int) -> ReviewResult:
    """Shared logic for both /images and /results endpoints."""
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


async def _sse_stream(app_id: int) -> AsyncGenerator[str, None]:
    for event in stream_review(app_id):                   # ← no more app_data arg
        yield f"data: {json.dumps(event.model_dump())}\n\n"


@router.get("/{app_id}/stream")
async def review_stream(
    app_id: int,
    _user:  dict = Depends(get_current_user),
):
    return StreamingResponse(
        _sse_stream(app_id),                              # ← no more app_data
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{app_id}/results", response_model=ReviewResult)
def get_results(app_id: int, _user: dict = Depends(get_current_user)):
    return _build_review_result(app_id)


@router.get("/{app_id}/images")
def analyze_photos(app_id: int):
    return _build_review_result(app_id)


@router.get("/agents/meta")
def agent_meta(_user: dict = Depends(get_current_user)):
    return AGENT_META