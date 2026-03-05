"""
routers/applications.py  v4

POST /applications/submit        →  multipart/form-data upload (blueprint + metadata)
GET  /applications/my            →  latest application for current user
GET  /applications/all           →  all applications (inspector only)
POST /applications/{app_id}/status →  advance workflow_status (inspector only)
GET  /applications/{app_id}/blueprint/analyse  →  trigger Gemma 3 visual analysis
"""

from fastapi import APIRouter, HTTPException

from backend.models.schemas import ApplicationPayload
from backend.models.database import get_application_by_id, create_application

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("/start")
async def process_application(payload: ApplicationPayload):
    app_id = payload.application_id
    print(payload)
    # 1. Check if application exists
    existing_app = get_application_by_id(app_id)  # Assume this helper exists

    if not existing_app:
        # VALIDATION: First-time entry must have all fields
        if not all(
            [payload.owner_name, payload.project_address, payload.application_type]
        ):
            raise HTTPException(
                status_code=400,
                detail="New applications must include owner_name, project_address, and application_type.",
            )
        app_id = create_application(
            payload.application_id,
            payload.application_type,
            payload.owner_name,
            payload.project_address,
            payload.zoning_type,
        )
    return "application created " + app_id


@router.post("/{app_id}")
async def get_application(app_id):

    # 1. Check if application exists
    existing_app = get_application_by_id(app_id)  # Assume this helper exists
    if not existing_app:
        # VALIDATION: First-time entry must have all fields
        raise HTTPException(
            status_code=400,
            detail="application does not exist.",
        )
    return existing_app


# # ── Submit (multipart) ────────────────────────────────────────────────────────


# @router.post(
#     "/submit",
#     response_model=ApplicationCreateResponse,
#     status_code=status.HTTP_201_CREATED,
# )
# async def submit_application(
#     owner: str = Form(...),
#     address: str = Form(...),
#     scope_of_work: str = Form(...),
#     blueprint: UploadFile = File(..., description="PDF or image blueprint"),
#     user: dict = Depends(get_current_user),
# ) -> ApplicationCreateResponse:
#     """
#     Accepts multipart/form-data so the blueprint file is stored in the DB.
#     The blueprint is persisted as BLOB and later retrieved for visual analysis.
#     """
#     if blueprint.content_type not in (
#         "application/pdf",
#         "image/png",
#         "image/jpeg",
#         "image/jpg",
#     ):
#         raise HTTPException(
#             status_code=400,
#             detail="Blueprint must be PDF, PNG, or JPEG.",
#         )

#     raw_bytes = await blueprint.read()
#     if len(raw_bytes) > 20 * 1024 * 1024:  # 20 MB guard
#         raise HTTPException(status_code=413, detail="Blueprint exceeds 20 MB limit.")

#     app_id, permit_id = insert_application(
#         owner=owner,
#         address=address,
#         blueprint_name=blueprint.filename or "blueprint",
#         scope_of_work=scope_of_work,
#         blueprint_data=raw_bytes,
#         blueprint_mime=blueprint.content_type,
#     )

#     return ApplicationCreateResponse(
#         app_id=app_id,
#         permit_id=permit_id,
#         message=(
#             f"Application {permit_id} submitted successfully. "
#             "Status: Submitted. Review crew will begin shortly."
#         ),
#     )


# # ── My application ────────────────────────────────────────────────────────────


# @router.get("/my", response_model=ApplicationStatus | None)
# def get_my_application(
#     user: dict = Depends(get_current_user),
# ) -> ApplicationStatus | None:
#     row = get_latest_application(user["username"])
#     if not row:
#         return None
#     return _row_to_status(row)


# # ── All applications (inspector) ──────────────────────────────────────────────


# @router.get("/all", response_model=list[ApplicationStatus])
# def get_all(
#     _user: dict = Depends(require_role("inspector")),
# ) -> list[ApplicationStatus]:
#     return [_row_to_status(r) for r in get_all_applications()]


# # ── Workflow status transition (inspector) ────────────────────────────────────


# @router.post("/{app_id}/status", response_model=ApplicationStatus)
# def advance_status(
#     app_id: int,
#     workflow_status: WorkflowStatus,
#     status_message: str = "",
#     _user: dict = Depends(require_role("inspector")),
# ) -> ApplicationStatus:
#     """
#     Inspector endpoint to manually advance workflow_status.
#     Valid transitions enforced by DB layer.
#     """
#     set_workflow_status(
#         app_id=app_id,
#         workflow_status=workflow_status.value,
#         status_message=status_message,
#     )
#     row = get_application_by_id(app_id)
#     if not row:
#         raise HTTPException(404, f"Application {app_id} not found.")
#     return _row_to_status(row)


# # ── Blueprint visual analysis ──────────────────────────────────────────────────


# @router.get("/{app_id}/blueprint/analyse", response_model=BlueprintAnalysisResponse)
# def blueprint_analyse(
#     app_id: int,
#     force_refresh: bool = False,
#     user: dict = Depends(get_current_user),
# ) -> BlueprintAnalysisResponse:
#     """
#     Trigger (or retrieve cached) Gemma 3 27B IT visual analysis on the blueprint.
#     First call takes ~10–30 seconds. Subsequent calls return cached results instantly.
#     """
#     app_row = get_application_by_id(app_id)
#     if not app_row:
#         raise HTTPException(404, f"Application {app_id} not found.")

#     try:
#         result = analyse_blueprint(app_id, force_refresh=force_refresh)
#     except RuntimeError as e:
#         raise HTTPException(500, str(e))

#     # Resolve analysed_at timestamp
#     cached_row = get_blueprint_analysis(app_id)
#     analysed_at = cached_row["analysed_at"] if cached_row else None

#     return BlueprintAnalysisResponse(
#         app_id=app_id,
#         permit_id=app_row["permit_id"],
#         overall_assessment=result.overall_assessment,
#         dimensions_found=[
#             DimensionFinding(
#                 element=d.get("element", ""),
#                 measured_value=d.get("measured_value", ""),
#                 code_minimum=d.get("code_minimum", ""),
#                 status=DimensionStatus(d.get("status", "not_visible")),
#                 detail=d.get("detail", ""),
#             )
#             for d in result.dimensions_found
#         ],
#         items_not_visible=result.items_not_visible,
#         recommendation=result.recommendation,
#         from_cache=result.from_cache,
#         analysed_at=analysed_at,
#     )


# # ── Helper ────────────────────────────────────────────────────────────────────


# def _row_to_status(row) -> ApplicationStatus:
#     return ApplicationStatus(
#         app_id=row["id"],
#         permit_id=row["permit_id"] or "",
#         owner=row["owner"],
#         address=row["address"],
#         created_at=row["created_at"] or "",
#         workflow_status=WorkflowStatus(row["workflow_status"] or "Submitted"),
#         stage=row["stage"] or "",
#         status_message=row["status_message"] or "",
#         compliance_score=row["compliance_score"] or 100,
#     )
