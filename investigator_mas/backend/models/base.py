"""
config/cities/base.py
─────────────────────
Full Pydantic v2 implementation of the three core config models:

    ApplicationTypeConfig  — rules for REN / NEW / DEM permit types
    ZoningConfig           — zoning rules (residential / industrial / etc.)
    CityConfig             — city-level permit authority, codes, and registry

Design goals:
  • Validated on construction — bad data raises immediately, not at runtime
  • Rich accessor / helper methods used by CrewAI agents and the SOW generator
  • Serializable to dict / JSON (Pydantic .model_dump())
  • Extensible — new cities instantiate CityConfig with their own overrides
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ═══════════════════════════════════════════════════════════════
#  Enums
# ═══════════════════════════════════════════════════════════════

class AppTypeCode(str, Enum):
    RENOVATION  = "REN"
    NEW         = "NEW"
    DEMOLITION  = "DEM"


class ZoningTypeCode(str, Enum):
    RESIDENTIAL = "residential"
    INDUSTRIAL  = "industrial"
    COMMERCIAL  = "commercial"   # alias — maps to industrial in many cities
    MIXED_USE   = "mixed_use"


# ═══════════════════════════════════════════════════════════════
#  CodeReference — a single building code citation
# ═══════════════════════════════════════════════════════════════

class CodeReference(BaseModel):
    """One parsed code citation: body, section, edition, and plain-English summary."""

    code: str    = Field(..., description="Code body — e.g. 'IRC', 'IBC', 'NEC', 'IECC'")
    section: str = Field(..., description="Section — e.g. '§R310', '§1705'")
    edition: str = Field(default="", description="Year/edition — e.g. '2021'")
    summary: str = Field(..., description="Plain-English description of the requirement")

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("section")
    @classmethod
    def normalize_section(cls, v: str) -> str:
        v = v.strip()
        if v and not v.startswith("§"):
            v = "§" + v
        return v

    @property
    def citation(self) -> str:
        """Formatted citation: '2021 IRC §R310'."""
        parts = [p for p in [self.edition, self.code, self.section] if p]
        return " ".join(parts)

    def __str__(self) -> str:
        return f"[{self.citation}] {self.summary}"

    model_config = {"frozen": True}


# ═══════════════════════════════════════════════════════════════
#  RequiredDocument — one item in a permit checklist
# ═══════════════════════════════════════════════════════════════

class RequiredDocument(BaseModel):
    """A single required document with instructions on what it must contain."""

    name: str = Field(..., description="Document title")
    description: str = Field(default="", description="What the document must show or include")
    mandatory: bool = Field(default=True, description="False = conditional / situational")
    condition: Optional[str] = Field(
        default=None,
        description="When mandatory=False, the condition that triggers this requirement",
    )
    accepted_formats: List[str] = Field(
        default_factory=lambda: ["PDF"],
        description="Accepted submission formats",
    )

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("RequiredDocument.name must not be empty")
        return v.strip()

    def to_checklist_line(self) -> str:
        """Render as a single formatted checklist item."""
        tag  = "[ ]" if self.mandatory else "[?]"
        line = f"{tag} {self.name}"
        if self.description:
            line += f"\n      → {self.description}"
        if not self.mandatory and self.condition:
            line += f"\n      ⚠ Required if: {self.condition}"
        return line

    model_config = {"frozen": True}


# ═══════════════════════════════════════════════════════════════
#  SetbackRule — numeric setbacks per direction
# ═══════════════════════════════════════════════════════════════

class SetbackRule(BaseModel):
    """
    Minimum setback requirements in feet.
    Use -1 to indicate 'no minimum' (zero-lot-line).
    """
    front_ft: float        = Field(..., ge=-1)
    rear_ft: float         = Field(..., ge=-1)
    side_ft: float         = Field(..., ge=-1)
    street_side_ft: Optional[float] = Field(default=None, ge=-1,
                                             description="Corner lot street-side setback")
    narrative: str         = Field(default="", description="Full narrative with code refs")

    def check(
        self, front: float, rear: float, side: float
    ) -> Dict[str, Any]:
        """Validate proposed setbacks. Returns {passed, violations}."""
        violations = []
        if self.front_ft >= 0 and front < self.front_ft:
            violations.append(
                f"Front setback {front} ft < required {self.front_ft} ft"
            )
        if self.rear_ft >= 0 and rear < self.rear_ft:
            violations.append(
                f"Rear setback {rear} ft < required {self.rear_ft} ft"
            )
        if self.side_ft >= 0 and side < self.side_ft:
            violations.append(
                f"Side setback {side} ft < required {self.side_ft} ft"
            )
        return {"passed": not violations, "violations": violations}


# ═══════════════════════════════════════════════════════════════
#  ApplicationTypeConfig
# ═══════════════════════════════════════════════════════════════

class ApplicationTypeConfig(BaseModel):
    """
    All permit rules for one application type (REN / NEW / DEM).
    Instantiated per city — cities set their own thresholds and documents.
    """

    # ── Identity ────────────────────────────────────────────────
    code: AppTypeCode = Field(..., description="Application type code")
    label: str        = Field(..., description="Human-readable label")
    description: str  = Field(default="", description="When to choose this type")

    # ── Required documents ───────────────────────────────────────
    required_documents: List[RequiredDocument] = Field(default_factory=list)

    # ── Code citations ───────────────────────────────────────────
    code_references: List[CodeReference] = Field(default_factory=list)

    # ── Free-text special requirements (for agent prompts) ───────
    special_requirements: List[str] = Field(default_factory=list)

    # ── Size thresholds that trigger additional review ────────────
    structural_review_threshold_sqft:  Optional[float] = Field(default=None, ge=0)
    energy_compliance_threshold_sqft:  Optional[float] = Field(default=None, ge=0)
    site_plan_review_threshold_sqft:   Optional[float] = Field(default=None, ge=0)
    fire_suppression_threshold_sqft:   Optional[float] = Field(default=None, ge=0)

    # ── Validators ───────────────────────────────────────────────
    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ApplicationTypeConfig.label must not be empty")
        return v.strip()

    # ── Document helpers ─────────────────────────────────────────

    @property
    def mandatory_documents(self) -> List[RequiredDocument]:
        return [d for d in self.required_documents if d.mandatory]

    @property
    def conditional_documents(self) -> List[RequiredDocument]:
        return [d for d in self.required_documents if not d.mandatory]

    def get_triggered_reviews(self, project_sqft: float) -> List[str]:
        """Return additional review types triggered by project size."""
        triggered = []
        checks = [
            (self.structural_review_threshold_sqft,
             "Full structural review required"),
            (self.energy_compliance_threshold_sqft,
             "Energy compliance documentation (REScheck / COMcheck) required"),
            (self.site_plan_review_threshold_sqft,
             "Full site plan review required"),
            (self.fire_suppression_threshold_sqft,
             "Automatic fire suppression / sprinkler system required"),
        ]
        for threshold, label in checks:
            if threshold is not None and project_sqft > threshold:
                triggered.append(
                    f"{label} (project {project_sqft:,.0f} sq ft > {threshold:,.0f} sq ft threshold)"
                )
        return triggered

    def get_document_checklist(self, project_sqft: Optional[float] = None) -> str:
        """Render a formatted document checklist, with size-triggered additions."""
        lines = [f"DOCUMENT CHECKLIST — {self.label}", "=" * 50, ""]

        lines.append("Mandatory Documents:")
        for doc in self.mandatory_documents:
            lines.append(f"  {doc.to_checklist_line()}")

        if self.conditional_documents:
            lines += ["", "Conditional Documents:"]
            for doc in self.conditional_documents:
                lines.append(f"  {doc.to_checklist_line()}")

        if project_sqft:
            triggered = self.get_triggered_reviews(project_sqft)
            if triggered:
                lines += ["", "Size-Triggered Requirements:"]
                for t in triggered:
                    lines.append(f"  ⚡ {t}")

        return "\n".join(lines)

    def get_code_summary(self) -> str:
        """Render all code references as a numbered list."""
        if not self.code_references:
            return "No specific code references configured for this application type."
        lines = [f"KEY CODE REFERENCES — {self.label}", "=" * 50]
        for i, ref in enumerate(self.code_references, 1):
            lines.append(f"  {i:>2}. {ref}")
        return "\n".join(lines)

    def to_agent_context(self, project_sqft: Optional[float] = None) -> str:
        """Full formatted context block for injection into agent prompts."""
        sections = [
            f"## Application Type: {self.label} ({self.code.value if hasattr(self.code, 'value') else self.code})",
            "",
        ]
        if self.description:
            sections += [self.description, ""]

        sections += [self.get_document_checklist(project_sqft), ""]
        sections += [self.get_code_summary(), ""]

        if self.special_requirements:
            sections.append("## Special Requirements")
            for req in self.special_requirements:
                sections.append(f"  • {req}")

        return "\n".join(sections)

    model_config = {"use_enum_values": True}


# ═══════════════════════════════════════════════════════════════
#  ZoningConfig
# ═══════════════════════════════════════════════════════════════

class ZoningConfig(BaseModel):
    """
    Zoning rules for one zone category.
    Provides both compliance checking methods and LLM-ready context text.
    """

    # ── Identity ────────────────────────────────────────────────
    type: ZoningTypeCode = Field(..., description="Zone category")
    label: str           = Field(..., description="Full label, e.g. 'Residential SF-1–SF-6'")
    subzones: List[str]  = Field(default_factory=list,
                                  description="Sub-zone designations, e.g. ['SF-1','SF-2']")

    # ── Dimensional standards ────────────────────────────────────
    setbacks: SetbackRule = Field(..., description="Minimum setback requirements")

    max_height_ft:         Optional[float] = Field(default=None, ge=0)
    max_stories:           Optional[int]   = Field(default=None, ge=1)
    max_lot_coverage_pct:  Optional[float] = Field(default=None, ge=0, le=100)
    max_far:               Optional[float] = Field(default=None, ge=0,
                                                    description="Max floor-to-area ratio")

    # ── Narrative text (for prompt context) ─────────────────────
    height_limits_narrative: str  = Field(default="")
    lot_coverage_narrative: str   = Field(default="")
    additional_notes: str         = Field(default="")

    # ── Zone-specific code citations ─────────────────────────────
    code_references: List[CodeReference] = Field(default_factory=list)

    # ── Validators ───────────────────────────────────────────────
    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ZoningConfig.label must not be empty")
        return v.strip()

    @model_validator(mode="after")
    def height_consistency(self) -> "ZoningConfig":
        """Sanity check: max_height_ft must be plausible for max_stories."""
        if (
            self.max_height_ft is not None
            and self.max_stories is not None
            and self.max_height_ft < self.max_stories * 5  # floor minimum ~5 ft/story
        ):
            raise ValueError(
                f"max_height_ft ({self.max_height_ft} ft) is implausibly low "
                f"for {self.max_stories} stories"
            )
        return self

    # ── Compliance checks ─────────────────────────────────────────

    def check_setbacks(
        self, front_ft: float, rear_ft: float, side_ft: float
    ) -> Dict[str, Any]:
        return self.setbacks.check(front_ft, rear_ft, side_ft)

    def check_height(self, proposed_ft: float) -> Dict[str, Any]:
        if self.max_height_ft is None:
            return {"passed": True, "note": "No height limit in this zone"}
        passed = proposed_ft <= self.max_height_ft
        return {
            "passed": passed,
            "proposed_ft": proposed_ft,
            "max_ft": self.max_height_ft,
            "violation": (
                None if passed
                else f"Proposed height {proposed_ft} ft exceeds max {self.max_height_ft} ft"
            ),
        }

    def check_lot_coverage(
        self, impervious_sqft: float, lot_sqft: float
    ) -> Dict[str, Any]:
        if self.max_lot_coverage_pct is None:
            return {"passed": True, "note": "No lot coverage limit configured"}
        if lot_sqft <= 0:
            return {"passed": False, "violation": "lot_sqft must be > 0"}
        pct = (impervious_sqft / lot_sqft) * 100
        passed = pct <= self.max_lot_coverage_pct
        return {
            "passed": passed,
            "coverage_pct": round(pct, 1),
            "max_pct": self.max_lot_coverage_pct,
            "violation": (
                None if passed
                else f"Impervious cover {pct:.1f}% exceeds max {self.max_lot_coverage_pct}%"
            ),
        }

    def run_all_checks(
        self,
        front_ft: Optional[float] = None,
        rear_ft: Optional[float] = None,
        side_ft: Optional[float] = None,
        height_ft: Optional[float] = None,
        impervious_sqft: Optional[float] = None,
        lot_sqft: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run all configured checks and return a combined compliance report."""
        results: Dict[str, Any] = {
            "zone": self.label,
            "checks": {},
            "violations": [],
        }

        if all(v is not None for v in [front_ft, rear_ft, side_ft]):
            sb = self.check_setbacks(front_ft, rear_ft, side_ft)
            results["checks"]["setbacks"] = sb
            results["violations"].extend(sb.get("violations", []))

        if height_ft is not None:
            h = self.check_height(height_ft)
            results["checks"]["height"] = h
            if h.get("violation"):
                results["violations"].append(h["violation"])

        if impervious_sqft is not None and lot_sqft is not None:
            lc = self.check_lot_coverage(impervious_sqft, lot_sqft)
            results["checks"]["lot_coverage"] = lc
            if lc.get("violation"):
                results["violations"].append(lc["violation"])

        results["passed"] = len(results["violations"]) == 0
        return results

    # ── Prompt context ────────────────────────────────────────────

    def to_agent_context(self) -> str:
        """Formatted zoning context for LLM prompt injection."""
        sb = self.setbacks
        lines = [
            f"## Zoning: {self.label}",
            f"   Type: {self.type}",
        ]
        if self.subzones:
            lines.append(f"   Sub-zones: {', '.join(self.subzones)}")

        lines += ["", "### Dimensional Standards"]

        # Setbacks
        sb_text = (
            f"  Setbacks:    Front {sb.front_ft} ft | "
            f"Rear {sb.rear_ft} ft | Side {sb.side_ft} ft"
        )
        if sb.street_side_ft is not None:
            sb_text += f" | Street-side {sb.street_side_ft} ft (corner lots)"
        lines.append(sb_text)
        if sb.narrative:
            lines.append(f"               ↳ {sb.narrative}")

        # Height
        h_parts = []
        if self.max_height_ft is not None:
            h_parts.append(f"{self.max_height_ft} ft")
        if self.max_stories is not None:
            h_parts.append(f"{self.max_stories} stories")
        if h_parts:
            lines.append(f"  Height max:  {' / '.join(h_parts)}")
        if self.height_limits_narrative:
            lines.append(f"               ↳ {self.height_limits_narrative}")

        # Lot coverage
        lc_parts = []
        if self.max_lot_coverage_pct is not None:
            lc_parts.append(f"{self.max_lot_coverage_pct}% impervious cover")
        if self.max_far is not None:
            lc_parts.append(f"FAR {self.max_far}")
        if lc_parts:
            lines.append(f"  Lot coverage:{' | '.join(lc_parts)}")
        if self.lot_coverage_narrative:
            lines.append(f"               ↳ {self.lot_coverage_narrative}")

        if self.additional_notes:
            lines += ["", "### Additional Zoning Notes", f"  {self.additional_notes}"]

        if self.code_references:
            lines += ["", "### Zoning Code References"]
            for ref in self.code_references:
                lines.append(f"  • {ref}")

        return "\n".join(lines)

    model_config = {"use_enum_values": True}


# ═══════════════════════════════════════════════════════════════
#  AdoptedCodes — all code editions adopted by a city
# ═══════════════════════════════════════════════════════════════

class AdoptedCodes(BaseModel):
    """Code editions adopted by the city, with local amendment notes."""
    building:     str = Field(default="", description="e.g. '2021 IBC with local amendments'")
    residential:  str = Field(default="", description="e.g. '2021 IRC'")
    electrical:   str = Field(default="", description="e.g. '2020 NEC'")
    plumbing:     str = Field(default="", description="e.g. '2021 UPC'")
    mechanical:   str = Field(default="", description="e.g. '2021 IMC'")
    energy:       str = Field(default="", description="e.g. '2021 IECC'")
    fire:         str = Field(default="", description="e.g. '2021 IFC'")
    accessibility: str = Field(default="", description="e.g. 'ADA + Texas Accessibility Standards'")
    green_building: str = Field(default="")
    local_amendments_url: Optional[str] = Field(default=None)

    def to_table(self) -> str:
        """Render a formatted code edition table."""
        rows = []
        for field_name, label in [
            ("building",      "Building"),
            ("residential",   "Residential"),
            ("electrical",    "Electrical"),
            ("plumbing",      "Plumbing"),
            ("mechanical",    "Mechanical"),
            ("energy",        "Energy"),
            ("fire",          "Fire"),
            ("accessibility", "Accessibility"),
            ("green_building","Green Building"),
        ]:
            val = getattr(self, field_name)
            if val:
                rows.append(f"  {label:<15} {val}")
        if self.local_amendments_url:
            rows.append(f"\n  Local amendments: {self.local_amendments_url}")
        return "\n".join(rows) if rows else "  (no code editions configured)"


# ═══════════════════════════════════════════════════════════════
#  CityConfig
# ═══════════════════════════════════════════════════════════════

class CityConfig(BaseModel):
    """
    Complete permit authority for one city.

    Key public methods for CrewAI agents:
        to_agent_context(app_type, zoning_type, project_sqft)  → LLM prompt block
        validate_application(...)                               → compliance report
        render_full_checklist(...)                              → document checklist
        get_guidelines(app_type, zoning_type)                  → raw dict (legacy)
    """

    # ── Identity ────────────────────────────────────────────────
    city_name:  str           = Field(..., min_length=2)
    state:      str           = Field(..., min_length=2, max_length=2)
    county:     Optional[str] = Field(default=None)
    timezone:   str           = Field(default="America/Chicago")

    # ── Contact ──────────────────────────────────────────────────
    portal_url:            str           = Field(...)
    permit_office_phone:   str           = Field(...)
    permit_office_email:   str           = Field(...)
    permit_office_address: str           = Field(default="")
    permit_office_hours:   str           = Field(default="Mon–Fri 7:30am–4:30pm")

    # ── Adopted codes ────────────────────────────────────────────
    adopted_codes: AdoptedCodes = Field(default_factory=AdoptedCodes)

    # ── Zone configs  (keyed by ZoningTypeCode string) ───────────
    zoning: Dict[str, ZoningConfig] = Field(
        default_factory=dict,
        description="Keyed by zone type string: 'residential', 'industrial', etc.",
    )

    # ── Application type configs  (keyed by AppTypeCode string) ──
    application_types: Dict[str, ApplicationTypeConfig] = Field(
        default_factory=dict,
        description="Keyed by code string: 'REN', 'NEW', 'DEM'",
    )

    # ── Universal required docs ───────────────────────────────────
    universal_required_docs: List[RequiredDocument] = Field(default_factory=list)

    # ── General city-level notes ──────────────────────────────────
    general_notes: List[str] = Field(
        default_factory=list,
        description="City-wide process notes, review timelines, helpful tips",
    )

    # ── Validators ───────────────────────────────────────────────

    @field_validator("state")
    @classmethod
    def uppercase_state(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.match(r"^[A-Z]{2}$", v):
            raise ValueError(f"state must be a 2-letter US abbreviation, got '{v}'")
        return v

    @field_validator("permit_office_phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) not in (10, 11):
            raise ValueError(
                f"Phone number must have 10 or 11 digits, got '{v}' ({len(digits)} digits)"
            )
        return v.strip()

    @model_validator(mode="after")
    def validate_app_type_keys(self) -> "CityConfig":
        valid = {c.value for c in AppTypeCode}
        for key in self.application_types:
            if key.upper() not in valid:
                raise ValueError(
                    f"application_types key '{key}' is invalid. Valid codes: {valid}"
                )
        return self

    @model_validator(mode="after")
    def validate_zoning_keys(self) -> "CityConfig":
        valid = {z.value for z in ZoningTypeCode}
        for key in self.zoning:
            if key.lower() not in valid:
                raise ValueError(
                    f"zoning key '{key}' is invalid. Valid types: {valid}"
                )
        return self

    # ── Typed accessors ───────────────────────────────────────────

    def get_app_type(self, code: str) -> ApplicationTypeConfig:
        """Retrieve ApplicationTypeConfig by code ('REN', 'NEW', 'DEM')."""
        cfg = self.application_types.get(code.upper())
        if not cfg:
            raise KeyError(
                f"Application type '{code}' is not configured for {self.city_name}. "
                f"Available: {list(self.application_types.keys())}"
            )
        return cfg

    def get_zoning(self, zone_type: str) -> ZoningConfig:
        """Retrieve ZoningConfig by type string ('residential', 'industrial', etc.)."""
        cfg = self.zoning.get(zone_type.lower())
        if not cfg:
            raise KeyError(
                f"Zoning type '{zone_type}' is not configured for {self.city_name}. "
                f"Available: {list(self.zoning.keys())}"
            )
        return cfg

    def supports_app_type(self, code: str) -> bool:
        return code.upper() in self.application_types

    def supports_zoning(self, zone_type: str) -> bool:
        return zone_type.lower() in self.zoning

    # ── Document helpers ──────────────────────────────────────────

    def get_all_required_docs(
        self,
        app_type: str,
        zoning_type: str,
        project_sqft: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Return all docs split by category (universal / mandatory / conditional / size-triggered)."""
        at = self.get_app_type(app_type)
        return {
            "universal":     self.universal_required_docs,
            "mandatory":     at.mandatory_documents,
            "conditional":   at.conditional_documents,
            "size_triggered": at.get_triggered_reviews(project_sqft) if project_sqft else [],
        }

    def render_full_checklist(
        self,
        app_type: str,
        zoning_type: str,
        project_sqft: Optional[float] = None,
    ) -> str:
        """Full formatted checklist ready for permit submission."""
        at = self.get_app_type(app_type)
        lines = [
            "PERMIT DOCUMENT CHECKLIST",
            f"City of {self.city_name}, {self.state}",
            f"Application Type: {at.label} ({at.code})",
            "=" * 55,
            "",
            "SECTION A — Universal (required for all applications):",
        ]
        for doc in self.universal_required_docs:
            lines.append(f"  {doc.to_checklist_line()}")

        lines += ["", f"SECTION B — {at.label} Specific:"]
        for doc in at.mandatory_documents:
            lines.append(f"  {doc.to_checklist_line()}")

        if at.conditional_documents:
            lines += ["", "SECTION C — Conditional:"]
            for doc in at.conditional_documents:
                lines.append(f"  {doc.to_checklist_line()}")

        if project_sqft:
            triggered = at.get_triggered_reviews(project_sqft)
            if triggered:
                lines += ["", "SECTION D — Size-Triggered Requirements:"]
                for t in triggered:
                    lines.append(f"  ⚡ {t}")

        return "\n".join(lines)

    # ── Compliance validation ─────────────────────────────────────

    def validate_application(
        self,
        app_type: str,
        zoning_type: str,
        project_sqft: Optional[float] = None,
        front_setback_ft: Optional[float] = None,
        rear_setback_ft: Optional[float] = None,
        side_setback_ft: Optional[float] = None,
        height_ft: Optional[float] = None,
        impervious_sqft: Optional[float] = None,
        lot_sqft: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run all available compliance checks.
        Returns a structured report: {passed, city, checks, all_violations}.
        """
        report: Dict[str, Any] = {
            "city":       self.city_name,
            "app_type":   app_type,
            "zoning_type": zoning_type,
            "checks":     {},
            "all_violations": [],
        }

        try:
            zone = self.get_zoning(zoning_type)
            zoning_result = zone.run_all_checks(
                front_ft=front_setback_ft,
                rear_ft=rear_setback_ft,
                side_ft=side_setback_ft,
                height_ft=height_ft,
                impervious_sqft=impervious_sqft,
                lot_sqft=lot_sqft,
            )
            report["checks"]["zoning"] = zoning_result
            report["all_violations"].extend(zoning_result.get("violations", []))
        except KeyError as e:
            report["checks"]["zoning"] = {"error": str(e)}

        if project_sqft:
            try:
                at = self.get_app_type(app_type)
                triggered = at.get_triggered_reviews(project_sqft)
                report["checks"]["size_triggers"] = triggered
            except KeyError as e:
                report["checks"]["size_triggers"] = {"error": str(e)}

        report["passed"] = len(report["all_violations"]) == 0
        return report

    # ── Agent prompt context ──────────────────────────────────────

    def get_guidelines(self, app_type: str, zoning_type: str) -> Dict[str, Any]:
        """
        Backward-compatible dict for existing permit_crew.py usage.
        Prefer to_agent_context() for new code.
        """
        at = self.application_types.get(app_type.upper())
        zt = self.zoning.get(zoning_type.lower())
        return {
            "city":          self.city_name,
            "state":         self.state,
            "portal":        self.portal_url,
            "app_type":      at,
            "zoning":        zt,
            "universal_docs": self.universal_required_docs,
            "codes":         self.adopted_codes.model_dump(),
        }

    def to_agent_context(
        self,
        app_type: str,
        zoning_type: str,
        project_sqft: Optional[float] = None,
    ) -> str:
        """
        Full LLM-ready context block — call this from CrewAI task descriptions.
        Combines city info, adopted codes, zoning rules, and app-type requirements.
        """
        lines = [
            "=" * 62,
            f"  CITY OF {self.city_name.upper()}, {self.state} — PERMIT AUTHORITY",
            "=" * 62,
            f"  Portal:  {self.portal_url}",
            f"  Phone:   {self.permit_office_phone}",
            f"  Email:   {self.permit_office_email}",
            f"  Hours:   {self.permit_office_hours}",
            "",
            "── ADOPTED CODES ──────────────────────────────────────────",
            self.adopted_codes.to_table(),
            "",
        ]

        # Zoning section
        try:
            zone = self.get_zoning(zoning_type)
            lines += [
                "── ZONING ─────────────────────────────────────────────────",
                zone.to_agent_context(),
                "",
            ]
        except KeyError:
            lines.append(f"⚠ Zoning type '{zoning_type}' not found for {self.city_name}.\n")

        # Application type section
        try:
            at = self.get_app_type(app_type)
            lines += [
                "── APPLICATION TYPE ────────────────────────────────────────",
                at.to_agent_context(project_sqft=project_sqft),
                "",
            ]
        except KeyError:
            lines.append(f"⚠ Application type '{app_type}' not found for {self.city_name}.\n")

        # Universal documents
        if self.universal_required_docs:
            lines.append("── UNIVERSAL REQUIRED DOCUMENTS ────────────────────────────")
            for doc in self.universal_required_docs:
                lines.append(f"  {doc.to_checklist_line()}")
            lines.append("")

        # General notes
        if self.general_notes:
            lines.append("── GENERAL PROCESS NOTES ───────────────────────────────────")
            for note in self.general_notes:
                lines.append(f"  • {note}")

        return "\n".join(lines)

    model_config = {"use_enum_values": True}
