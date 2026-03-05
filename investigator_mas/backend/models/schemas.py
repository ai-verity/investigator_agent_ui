"""
schemas.py  v4
==============
Pydantic models — single source of truth for the API contract.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from datetime import datetime


# ── Auth ───────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str  # "public" | "inspector"


# ── Application lifecycle ──────────────────────────────────────────────────────


class ApplicationPayload(BaseModel):
    application_id: str
    date: datetime
    application_type: str = Field(..., pattern="^(REN|NEW)$")
    owner_name: Optional[str] = None
    project_address: Optional[str] = None
    zoning_type: Optional[str] = None


class SOWPayload(BaseModel):
    application_id: str
    question_id: str
    response: str


class SOWResponsePayload(BaseModel):
    application_id: str
    next_question_id: str
    next_question: Optional[str] = None
    is_done: bool
    generated_sow: Optional[str] = None


class SOWInput(BaseModel):
    application_id: str
    application_type: str = Field(..., pattern="^(REN|NEW)$")
    owner_name: Optional[str] = None
    project_address: Optional[str] = None
    zoning_type: Optional[str] = None
    sow_question_answer: dict | None = None
    sow_text: str | None = None
    curr_question_id: str
    curr_response: str


# ═══════════════════════════════════════════════════════════════
#  State enum
# ═══════════════════════════════════════════════════════════════


class SessionState(str, Enum):
    INTAKE = "intake"  # collecting form fields
    QUESTIONING = "questioning"  # Q&A in progress
    REVIEWING = "reviewing"  # Q&A done, generating SOW
    COMPLETE = "complete"  # SOW generated
    GENERATED = "generated"  # delivered to user


# ═══════════════════════════════════════════════════════════════
#  ConversationTurn — typed history entry
# ═══════════════════════════════════════════════════════════════


class ConversationTurn(BaseModel):
    role: str  # "assistant" | "user" | "system"
    content: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    question_number: Optional[int] = None  # which Q this belongs to (if role=assistant)

    model_config = {"frozen": True}


# ═══════════════════════════════════════════════════════════════
#  ImageAttachment — one attached blueprint or photo
# ═══════════════════════════════════════════════════════════════


class ImageAttachment(BaseModel):
    path: str
    context_note: str = ""  # user-supplied note when attaching
    analysis: str = ""  # result from ImageAnalyzerTool
    attached_at_question: Optional[int] = None

    @property
    def has_analysis(self) -> bool:
        return bool(self.analysis.strip())

    def to_prompt_block(self) -> str:
        lines = [f"📎 Attached file: {self.path}"]
        if self.context_note:
            lines.append(f"   User note: {self.context_note}")
        if self.has_analysis:
            lines.append("   Analysis:")
            for line in self.analysis.splitlines():
                lines.append(f"     {line}")
        else:
            lines.append("   (analysis pending)")
        return "\n".join(lines)

    model_config = {"frozen": False}


# ═══════════════════════════════════════════════════════════════
#  ComplianceFlag — a potential issue surfaced during intake
# ═══════════════════════════════════════════════════════════════


class FlagSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


class ComplianceFlag(BaseModel):
    severity: FlagSeverity
    code: str  # short machine-readable code, e.g. "HERITAGE_TREE"
    message: str  # human-readable description
    resolution: str = ""  # what the applicant must do

    def __str__(self) -> str:
        icon = {"info": "ℹ", "warning": "⚠", "blocker": "🚫"}[self.severity]
        line = f"{icon} [{self.code}] {self.message}"
        if self.resolution:
            line += f"\n   → {self.resolution}"
        return line

    model_config = {"frozen": True}


class PermitSession(BaseModel):
    city: str = Field(default="", description="City slug, e.g. 'austin'")
    project_address: str = Field(default="")
    owner_name: str = Field(default="")
    application_type: str = Field(default="", description="REN | NEW | DEM")
    zoning_type: str = Field(
        default="", description="residential | industrial | commercial | mixed_use"
    )
    short_scope: str = Field(
        default="", description="Applicant's initial brief project description"
    )
    project_size_sqft: Optional[float] = Field(default=None, ge=0)
    existing_structure_sqft: Optional[float] = Field(default=None, ge=0)
    num_stories: Optional[int] = Field(default=None, ge=1, le=200)
    occupancy_type: str = Field(
        default="", description="e.g. 'single-family', 'office', 'warehouse'"
    )
    structural_changes: Optional[bool] = Field(default=None)
    mep_changes: Optional[bool] = Field(
        default=None, description="Mechanical / Electrical / Plumbing changes"
    )
    heritage_trees_nearby: Optional[bool] = Field(default=None)
    pre_1980_structure: Optional[bool] = Field(default=None)
    special_conditions: str = Field(
        default="", description="Flood zone, historic district, LEED target, etc."
    )
    lot_sqft: Optional[float] = Field(default=None, ge=0)
    front_setback_ft: Optional[float] = Field(default=None, ge=0)
    rear_setback_ft: Optional[float] = Field(default=None, ge=0)
    side_setback_ft: Optional[float] = Field(default=None, ge=0)
    proposed_height_ft: Optional[float] = Field(default=None, ge=0)
    attachments: List[ImageAttachment] = Field(default_factory=list)
    state: SessionState = Field(default=SessionState.INTAKE)
    questions_asked: int = Field(default=0, ge=0)
    conversation_history: List[ConversationTurn] = Field(default_factory=list)
    is_complete: bool = Field(default=False, description="True when intake Q&A is done")
    generated_sow: str = Field(default="")
    guidelines: str = Field(default="")

    # ── Convenience properties ────────────────────────────────────

    @property
    def image_paths(self) -> List[str]:
        return [a.path for a in self.attachments]

    @property
    def image_analyses(self) -> List[str]:
        return [f"File: {a.path}\n{a.analysis}" for a in self.attachments if a.analysis]

    @property
    def missing_critical_fields(self) -> List[str]:
        return [
            f
            for f in (
                "project_address",
                "owner_name",
                "application_type",
                "zoning_type",
                "short_scope",
            )
            if not getattr(self, f)
        ]

    @property
    def questions_remaining(self) -> int:
        return max(0, 5 - self.questions_asked)

    @property
    def readiness_score(self) -> int:
        weights = {
            "project_address": 10,
            "owner_name": 10,
            "application_type": 10,
            "zoning_type": 10,
            "short_scope": 10,
            "project_size_sqft": 10,
            "occupancy_type": 8,
            "structural_changes": 8,
            "mep_changes": 6,
            "pre_1980_structure": 6,
            "heritage_trees_nearby": 6,
            "special_conditions": 6,
        }
        score = sum(
            w
            for f, w in weights.items()
            if getattr(self, f) is not None and getattr(self, f) != ""
        )
        return min(score, 100)

    # ── Serialization ─────────────────────────────────────────────

    def to_context_dict(self) -> dict:
        return {
            "city": self.city,
            "state": self.state.value if hasattr(self.state, "value") else self.state,
            "project_address": self.project_address,
            "owner_name": self.owner_name,
            "application_type": self.application_type,
            "zoning_type": self.zoning_type,
            "short_scope": self.short_scope,
            "project_size_sqft": self.project_size_sqft,
            "existing_structure_sqft": self.existing_structure_sqft,
            "num_stories": self.num_stories,
            "occupancy_type": self.occupancy_type,
            "structural_changes": self.structural_changes,
            "mep_changes": self.mep_changes,
            "heritage_trees_nearby": self.heritage_trees_nearby,
            "pre_1980_structure": self.pre_1980_structure,
            "special_conditions": self.special_conditions,
            "images_provided": len(self.attachments),
            "images_analyzed": sum(1 for a in self.attachments if a.analysis),
            "questions_asked": self.questions_asked,
            "questions_remaining": self.questions_remaining,
            "readiness_score": self.readiness_score,
            "is_complete": self.is_complete,
            "missing_fields": self.missing_critical_fields,
        }

    # ── Mutation helpers ──────────────────────────────────────────

    def update_from_extracted(self, data: dict) -> List[str]:
        updatable = {
            "project_size_sqft",
            "existing_structure_sqft",
            "num_stories",
            "occupancy_type",
            "structural_changes",
            "mep_changes",
            "heritage_trees_nearby",
            "pre_1980_structure",
            "special_conditions",
            "owner_name",
            "project_address",
            "application_type",
            "zoning_type",
            "short_scope",
            "city",
            "lot_sqft",
            "front_setback_ft",
            "rear_setback_ft",
            "side_setback_ft",
            "proposed_height_ft",
        }
        updated = []
        for key, value in data.items():
            if key not in updatable or value is None:
                continue
            current = getattr(self, key, None)
            if isinstance(current, str) and current and not value:
                continue
            object.__setattr__(self, key, value)
            updated.append(key)
        return updated

    def add_image(
        self, path: str, context_note: str = "", analysis: str = ""
    ) -> "ImageAttachment":
        attachment = ImageAttachment(
            path=path,
            context_note=context_note,
            analysis=analysis,
            attached_at_question=self.questions_asked,
        )
        self.attachments.append(attachment)
        return attachment

    def record_exchange(
        self, question: str, answer: str, question_number: Optional[int] = None
    ) -> None:
        qnum = question_number if question_number is not None else self.questions_asked
        self.conversation_history.append(
            ConversationTurn(role="assistant", content=question, question_number=qnum)
        )
        self.conversation_history.append(
            ConversationTurn(role="user", content=answer, question_number=qnum)
        )

    def mark_intake_complete(self) -> None:
        object.__setattr__(self, "is_complete", True)
        self.state = SessionState.REVIEWING

    def mark_sow_generated(self, sow: str) -> None:
        self.generated_sow = sow
        self.state = SessionState.COMPLETE
        object.__setattr__(self, "is_complete", True)


# class PermitSession(BaseModel):
#     city: str = Field(default="", description="City slug, e.g. 'austin'")
#     project_address: str = Field(default="")
#     owner_name: str = Field(default="")
#     application_type: str = Field(default="", description="REN | NEW | DEM")
#     zoning_type: str = Field(
#         default="", description="residential | industrial | commercial | mixed_use"
#     )
#     short_scope: str = Field(
#         default="", description="Applicant's initial brief project description"
#     )

#     # ── Enriched project details (gathered via Q&A) ───────────────
#     project_size_sqft: Optional[float] = Field(default=None, ge=0)
#     existing_structure_sqft: Optional[float] = Field(default=None, ge=0)
#     num_stories: Optional[int] = Field(default=None, ge=1, le=200)
#     occupancy_type: str = Field(
#         default="", description="e.g. 'single-family', 'office', 'warehouse'"
#     )
#     structural_changes: Optional[bool] = Field(default=None)
#     mep_changes: Optional[bool] = Field(
#         default=None, description="Mechanical / Electrical / Plumbing changes"
#     )
#     heritage_trees_nearby: Optional[bool] = Field(default=None)
#     pre_1980_structure: Optional[bool] = Field(default=None)
#     special_conditions: str = Field(
#         default="", description="Flood zone, historic district, LEED target, etc."
#     )
#     lot_sqft: Optional[float] = Field(default=None, ge=0)
#     front_setback_ft: Optional[float] = Field(default=None, ge=0)
#     rear_setback_ft: Optional[float] = Field(default=None, ge=0)
#     side_setback_ft: Optional[float] = Field(default=None, ge=0)
#     proposed_height_ft: Optional[float] = Field(default=None, ge=0)

#     # ── Attached images ───────────────────────────────────────────
#     attachments: List[ImageAttachment] = Field(default_factory=list)

#     # ── Conversation state ────────────────────────────────────────
#     state: SessionState = Field(default=SessionState.INTAKE)
#     questions_asked: int = Field(default=0, ge=0)
#     conversation_history: List[ConversationTurn] = Field(default_factory=list)
#     is_complete: bool = Field(default=False, description="True when intake Q&A is done")

#     # ── Outputs ───────────────────────────────────────────────────
#     generated_sow: str = Field(default="")
#     guidelines: str = Field(default="")

#     def to_context_dict(self) -> dict:
#         """Serialize session field."""
#         return {
#             "session_id": getattr(self, "session_id", ""),
#             "city": self.city,
#             "state": getattr(self, "state", ""),
#             "project_address": self.project_address,
#             "owner_name": self.owner_name,
#             "application_type": self.application_type,
#             "zoning_type": self.zoning_type,
#             "short_scope": self.short_scope,
#             "project_size_sqft": self.project_size_sqft,
#             "existing_structure_sqft": self.existing_structure_sqft,
#             "num_stories": self.num_stories,
#             "occupancy_type": self.occupancy_type,
#             "structural_changes": self.structural_changes,
#             "mep_changes": self.mep_changes,
#             "heritage_trees_nearby": self.heritage_trees_nearby,
#             "pre_1980_structure": self.pre_1980_structure,
#             "special_conditions": self.special_conditions,
#             "images_provided": len(self.image_paths),
#             "questions_asked": self.questions_asked,
#             "questions_remaining": max(0, 5 - self.questions_asked),
#             "readiness_score": getattr(self, "readiness_score", 0),
#             "is_complete": self.is_complete,
#             "missing_fields": self.missing_critical_fields,
#         }


class WorkflowStatus(str, Enum):
    SUBMITTED = "Submitted"
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class ApplicationCreate(BaseModel):
    owner: str = Field(..., min_length=2)
    address: str = Field(..., min_length=5)
    blueprint_name: str
    scope_of_work: str = Field(..., min_length=10)
    # blueprint file bytes are sent as multipart/form-data, not in this body


class ApplicationStatus(BaseModel):
    app_id: int
    permit_id: str  # e.g. "ATX-2026-000001"
    owner: str
    address: str
    created_at: str
    workflow_status: WorkflowStatus
    stage: str  # detailed review sub-label
    status_message: str
    compliance_score: int  # 0–100


class ApplicationCreateResponse(BaseModel):
    app_id: int
    permit_id: str  # ← the human-readable ID to show in UI
    message: str


# ── SOW Interview ──────────────────────────────────────────────────────────────


class InterviewQuestion(BaseModel):
    index: int
    total: int
    key: str
    question: str
    hint: str


class ValidateAnswerRequest(BaseModel):
    question_key: str
    question_text: str
    answer: str


class ValidateAnswerResponse(BaseModel):
    sufficient: bool
    follow_up: Optional[str] = None


class SOWGenerateRequest(BaseModel):
    collected_data: dict[str, str]


class SOWGenerateResponse(BaseModel):
    scope_of_work: str


class SOWProgressEvent(BaseModel):
    stage: str
    message: str
    progress: int
    result: Optional[str] = None


# ── Blueprint visual analysis ──────────────────────────────────────────────────


class DimensionStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    VIOLATION = "violation"
    NOT_VISIBLE = "not_visible"


class DimensionFinding(BaseModel):
    element: str
    measured_value: str
    code_minimum: str
    status: DimensionStatus
    detail: str


class BlueprintAnalysisResponse(BaseModel):
    app_id: int
    permit_id: str
    overall_assessment: str
    dimensions_found: list[DimensionFinding]
    items_not_visible: list[str]
    recommendation: str
    from_cache: bool
    analysed_at: Optional[str] = None


# ── Review crew ────────────────────────────────────────────────────────────────


class FindingSeverity(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    VIOLATION = "violation"
    CRITICAL = "critical"
    FOLLOWUP = "follow-up"


class AgentFinding(BaseModel):
    agent: str
    finding: str
    severity: FindingSeverity
    detail: str


class ReviewProgressEvent(BaseModel):
    event_type: str  # agent_start | agent_done | complete | error
    agent_name: str
    agent_index: int
    message: str
    finding: Optional[AgentFinding] = None
    all_findings: Optional[list[AgentFinding]] = None
    compliance_score: Optional[int] = None


class ReviewResult(BaseModel):
    app_id: int
    permit_id: str
    findings: list[AgentFinding]
    compliance_score: int
    workflow_status: WorkflowStatus
    stage: str
