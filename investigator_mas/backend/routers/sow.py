"""
backend/routers/sow.py

GET  /sow/{app_id}     →  InterviewQuestion
"""

from fastapi import APIRouter, HTTPException
import json

# from backend.models.schemas import SOWApplicationPayload
from backend.services.sow_service import generate_sow
from backend.models.database import get_application_by_id
from backend.models.schemas import SOWPayload, SOWResponsePayload, SOWInput

router = APIRouter(prefix="/sow", tags=["sow"])


@router.post("/sow", response_model=SOWResponsePayload)
async def create_sow(payload: SOWPayload):
    # 1. Check if application exists
    existing_app = get_application_by_id(
        payload.application_id
    )  # Assume this helper exists
    if not existing_app:
        # VALIDATION: First-time entry must have all fields
        raise HTTPException(
            status_code=400,
            detail="application does not exist.",
        )

    return generate_sow(
        SOWInput(
            application_id=payload.application_id,
            application_type=existing_app["application_type"],
            owner_name=existing_app["owner_name"],
            project_address=existing_app["project_address"],
            zoning_type=existing_app["zoning_type"],
            sow_question_answer=json.loads(existing_app["sow_question_answer"]),
            sow_text=existing_app["sow_text"],
            status=existing_app["status"],
            curr_question_id=payload.question_id,
            curr_response=payload.response,
        )
    )
