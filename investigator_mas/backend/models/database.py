"""
backend/models/database.py
==========================
Re-export shim — the canonical DB code lives in common/database.py
(shared between the Streamlit frontend and the FastAPI backend).

All backend code imports from here:
    from backend.models.database import get_user, insert_application, ...

This file just forwards every name so imports don't break regardless of
which layer uses them.
"""

from common.database import (  # noqa: F401  (re-exports)
    # ── Connection & init ──────────────────────────────────────────────────────
    get_db,
    init_db,
    # ── Constants ─────────────────────────────────────────────────────────────
    VALID_WORKFLOW_STATUSES,
    VALID_APPLICATION_STATUSES,
    # ── Users ─────────────────────────────────────────────────────────────────
    get_user,
    # ── Legacy applications (v4) ───────────────────────────────────────────────
    insert_application,
    get_latest_application,
    get_application_by_id,
    get_all_applications,
    get_blueprint_bytes,
    set_workflow_status,
    upsert_application_status,
    save_review_findings,
    get_review_findings,
    save_blueprint_analysis,
    get_blueprint_analysis,
    # ── Applications (v5) ─────────────────────────────────────────────────────
    create_application,
    get_application,
    get_all_applications_v5,
    update_application,
    set_application_status,
    set_sow_question_answer,
    delete_application,
    # ── AI records ────────────────────────────────────────────────────────────
    create_ai_record,
    get_ai_record,
    get_ai_records_by_agent,
    get_ai_records_by_task,
    get_all_ai_records,
    update_ai_record,
    set_ai_status,
    set_ai_compliance_summary,
    delete_ai_record,
    update_application_sow_state
)
