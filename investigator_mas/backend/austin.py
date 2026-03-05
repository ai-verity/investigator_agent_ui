"""
City of Austin, TX — Permit Configuration
Uses fully implemented ApplicationTypeConfig, ZoningConfig, CityConfig models.

Code references:
  Austin City Code, Title 25 (Land Development Code)
  2021 IBC / 2021 IRC / 2020 NEC / 2021 UPC / 2021 IECC / 2021 IFC
  Texas Accessibility Standards (TAS)
  Austin Energy Green Building Program
"""

from backend.models.base import (
    AdoptedCodes,
    AppTypeCode,
    ApplicationTypeConfig,
    CityConfig,
    CodeReference,
    RequiredDocument,
    SetbackRule,
    ZoningConfig,
    ZoningTypeCode,
)

# ─────────────────────────────────────────────────────────────────
#  Shared code reference helpers
# ─────────────────────────────────────────────────────────────────

def _ref(code: str, section: str, edition: str, summary: str) -> CodeReference:
    return CodeReference(code=code, section=section, edition=edition, summary=summary)


def _doc(
    name: str,
    description: str = "",
    mandatory: bool = True,
    condition: str = None,
    formats: list = None,
) -> RequiredDocument:
    kwargs = dict(name=name, description=description, mandatory=mandatory)
    if condition:
        kwargs["condition"] = condition
    if formats:
        kwargs["accepted_formats"] = formats
    return RequiredDocument(**kwargs)


# ─────────────────────────────────────────────────────────────────
#  ZONING — Residential
# ─────────────────────────────────────────────────────────────────

RESIDENTIAL_ZONING = ZoningConfig(
    type=ZoningTypeCode.RESIDENTIAL,
    label="Residential (SF-1 through SF-6 / MF zones)",
    subzones=["SF-1", "SF-2", "SF-3", "SF-4", "SF-4A", "SF-5", "SF-6"],
    setbacks=SetbackRule(
        front_ft=25,
        rear_ft=10,
        side_ft=5,
        street_side_ft=15,
        narrative=(
            "Front: 25 ft (SF-1/SF-2), 15 ft (SF-3/SF-4/SF-5/SF-6). "
            "Rear: 10 ft minimum. Side: 5 ft minimum. "
            "Corner lots: 15 ft street-side setback. "
            "Ref: Austin City Code §25-2-492 through §25-2-514."
        ),
    ),
    max_height_ft=35,
    max_stories=2,
    max_lot_coverage_pct=45,
    height_limits_narrative=(
        "Maximum 35 ft or 2 stories for primary structure in SF zones. "
        "ADUs: max 1,100 sq ft or 15% of lot area, max 2 stories. "
        "Ref: Austin City Code §25-2-774 (ADU) and §25-2-1063 (SF heights)."
    ),
    lot_coverage_narrative=(
        "Impervious cover: 45% for SF-2, up to 60% for inner-city SF zones. "
        "FAR varies by sub-zone. "
        "Ref: Austin City Code §25-8-301 (Impervious Cover Rules)."
    ),
    additional_notes=(
        "Residential additions >200 sq ft trigger full energy compliance review (IECC Ch.4). "
        "Heritage Tree Ordinance: trees ≥19 in. diameter require Tree Review. "
        "Austin Energy Green Building checklist may apply for additions >1,000 sq ft. "
        "Ref: Austin City Code §25-8-641 (Heritage Trees)."
    ),
    code_references=[
        _ref("Austin City Code", "§25-2-492", "", "Residential setback requirements"),
        _ref("Austin City Code", "§25-8-301", "", "Impervious cover limitations"),
        _ref("Austin City Code", "§25-8-641", "", "Heritage Tree protections"),
        _ref("Austin City Code", "§25-2-774", "", "Accessory Dwelling Unit standards"),
    ],
)


# ─────────────────────────────────────────────────────────────────
#  ZONING — Industrial / Commercial
# ─────────────────────────────────────────────────────────────────

INDUSTRIAL_ZONING = ZoningConfig(
    type=ZoningTypeCode.INDUSTRIAL,
    label="Industrial / Commercial (CS, LI, MI, CH zones)",
    subzones=["CS", "CS-1", "LI", "MI", "CH"],
    setbacks=SetbackRule(
        front_ft=0,
        rear_ft=0,
        side_ft=0,
        narrative=(
            "Front: 0–15 ft depending on corridor overlay. "
            "Side/Rear: 0 ft in most industrial zones; 25 ft buffer if adjacent to residential. "
            "Ref: Austin City Code §25-2-701 through §25-2-761."
        ),
    ),
    max_height_ft=None,   # unlimited in LI/MI — subject to FAA review near airport
    max_stories=None,
    max_lot_coverage_pct=95,
    height_limits_narrative=(
        "Generally unlimited in LI/MI subject to FAA obstruction review near Austin-Bergstrom. "
        "CS zone: 60 ft standard, may be increased with compatibility waiver. "
        "Ref: Austin City Code §25-2-817."
    ),
    lot_coverage_narrative=(
        "Impervious cover up to 95% in industrial zones. "
        "Stormwater quality controls required for sites >5,000 sq ft of impervious cover change. "
        "Ref: Austin City Code §25-8-514 (Water Quality Controls)."
    ),
    additional_notes=(
        "Commercial buildings must meet IBC Ch.11 (Accessibility / ADA) and Texas Accessibility Standards (TAS). "
        "Fire suppression required for new commercial buildings >5,000 sq ft (IFC §903). "
        "Energy modeling or COMcheck required for commercial envelopes (IECC Ch.5). "
        "Mechanical systems governed by IMC 2021. Kitchen hoods require separate grease duct permit. "
        "TDLR review mandatory for all commercial construction in Texas."
    ),
    code_references=[
        _ref("Austin City Code", "§25-2-701", "", "Industrial/commercial zoning districts"),
        _ref("Austin City Code", "§25-8-514", "", "Water quality controls for commercial sites"),
        _ref("IBC", "§1004",   "2021", "Occupant load calculations"),
        _ref("IBC", "§1006",   "2021", "Means of egress requirements"),
        _ref("IFC", "§903",    "2021", "Automatic sprinkler systems"),
    ],
)


# ─────────────────────────────────────────────────────────────────
#  APPLICATION TYPE — REN (Renovation / Addition)
# ─────────────────────────────────────────────────────────────────

REN_CONFIG = ApplicationTypeConfig(
    code=AppTypeCode.RENOVATION,
    label="Renovation / Remodel / Addition",
    description=(
        "Use for interior remodels, exterior alterations, structural modifications, "
        "and additions to existing permitted structures."
    ),
    required_documents=[
        _doc("Existing conditions drawings",
             "Floor plan, elevations, and sections showing existing layout at min 1/8\" scale"),
        _doc("Proposed construction drawings",
             "Floor plans, sections, elevations, and details for all proposed work — min 1/8\" scale"),
        _doc("Structural calculations",
             "Engineer-stamped (PE licensed in TX) calculations for any load-bearing modifications",
             mandatory=False,
             condition="Structural elements (walls, beams, foundations) are being modified or removed"),
        _doc("Energy compliance — REScheck",
             "REScheck report demonstrating IECC §R402 compliance for envelope changes",
             mandatory=False,
             condition="Residential addition >200 sq ft or any envelope modification"),
        _doc("Energy compliance — COMcheck",
             "COMcheck report for commercial envelope or mechanical system changes",
             mandatory=False,
             condition="Commercial renovation involving envelope or HVAC modifications"),
        _doc("Impervious cover worksheet",
             "Calculation of existing vs. proposed impervious cover with site plan",
             mandatory=False,
             condition="Addition increases building footprint"),
        _doc("MEP drawings",
             "Mechanical, electrical, and plumbing drawings stamped by licensed engineers",
             mandatory=False,
             condition="HVAC, electrical service, or plumbing systems are being modified or extended"),
        _doc("Asbestos / Lead survey",
             "Survey by accredited inspector listing all ACM and LBP — EPA NESHAP notification if positive",
             mandatory=False,
             condition="Structure built before 1980 and any existing material is being disturbed"),
    ],
    code_references=[
        _ref("IRC", "§R102.7",  "2021", "Existing buildings: new work must comply with code for new construction"),
        _ref("IRC", "§R301",    "2021", "Structural design criteria — wind, seismic, and snow loads"),
        _ref("IRC", "§R303",    "2021", "Light, ventilation, and heating for habitable rooms"),
        _ref("IRC", "§R310",    "2021", "Emergency escape and rescue openings (egress windows — min 5.7 sq ft net)"),
        _ref("IRC", "§R314",    "2021", "Smoke detector placement requirements"),
        _ref("IRC", "§R315",    "2021", "Carbon monoxide detector requirements"),
        _ref("IECC", "§R402",   "2021", "Building envelope requirements — Climate Zone 2: R-38 ceiling, R-15 walls"),
        _ref("IBC", "§3404",    "2021", "Alterations — existing structural elements may not be reduced below code"),
        _ref("NEC", "§210.8",   "2020", "GFCI protection within 6 ft of water sources in kitchens, baths"),
        _ref("Austin City Code", "§25-11-1", "", "Austin local renovation permit requirements"),
    ],
    special_requirements=[
        "Additions increasing heated area must meet IECC §R402 insulation minimums "
        "(R-38 ceiling / R-15 walls for Austin's Climate Zone 2)",
        "Egress windows required in all new sleeping rooms — min 5.7 sq ft net opening, "
        "min 20 in. wide, min 24 in. high, max 44 in. sill height [IRC §R310]",
        "New bathrooms: GFCI protection required within 6 ft of water source [NEC §210.8]",
        "Smoke + CO detectors required in all sleeping rooms and hallways to sleeping rooms [IRC §R314/R315]",
        "Heritage Trees (≥19 in. diameter) within 150% critical root zone require Tree Review before any grading",
    ],
    structural_review_threshold_sqft=0,      # ANY structural change triggers review
    energy_compliance_threshold_sqft=200,
    site_plan_review_threshold_sqft=500,
)


# ─────────────────────────────────────────────────────────────────
#  APPLICATION TYPE — NEW (New Construction)
# ─────────────────────────────────────────────────────────────────

NEW_CONFIG = ApplicationTypeConfig(
    code=AppTypeCode.NEW,
    label="New Construction",
    description=(
        "Use for construction of entirely new structures on vacant lots or "
        "following complete demolition of existing structures."
    ),
    required_documents=[
        _doc("Architectural drawings — complete set",
             "Site plan, floor plans, exterior elevations, building sections, details — min 1/4\" scale residential"),
        _doc("Structural drawings",
             "Engineer-stamped drawings and calculations (PE licensed in Texas)"),
        _doc("Foundation plan",
             "Foundation plan with rebar layout, slab thickness (min 3.5 in.), and thickened edges [IRC §R403]"),
        _doc("Geotechnical / soils report",
             "Soils report from licensed geotechnical engineer",
             mandatory=False,
             condition="Commercial construction or when expansive soils are suspected"),
        _doc("MEP construction documents",
             "Full mechanical, electrical, and plumbing drawings stamped by licensed engineers"),
        _doc("Energy compliance",
             "REScheck (residential) or COMcheck / full energy model (commercial) per IECC 2021"),
        _doc("Stormwater management plan",
             "Drainage study and stormwater quality controls per Austin City Code §25-8-514"),
        _doc("Utility coordination letters",
             "Written confirmation from Austin Water and Austin Energy of available capacity"),
        _doc("Landscape plan",
             "Landscape plan per Watershed Protection Dept. requirements",
             mandatory=False,
             condition="Site disturbance > 1 acre"),
        _doc("Fire protection system drawings",
             "Full sprinkler / suppression system drawings per IFC §903",
             mandatory=False,
             condition="Commercial building > 5,000 sq ft"),
        _doc("Texas Accessibility Standards (TAS) compliance statement",
             "Statement and TDLR project registration number for all commercial buildings"),
        _doc("Austin Energy Green Building checklist",
             "Completed checklist demonstrating minimum 1-star rating (residential)"),
        _doc("Special inspections program",
             "IBC §1705 special inspections program submitted before permit issuance",
             mandatory=False,
             condition="Commercial construction (IBC occupancies B, A, I, R-2+)"),
    ],
    code_references=[
        _ref("IBC", "§107",    "2021", "Construction document requirements for commercial buildings"),
        _ref("IBC", "§1604",   "2021", "General structural design requirements"),
        _ref("IBC", "§1704",   "2021", "Special inspections required for new commercial construction"),
        _ref("IBC", "§1705",   "2021", "Special inspection types — concrete, masonry, soils, high-strength bolting"),
        _ref("IRC", "§R401",   "2021", "Foundation requirements for residential new construction"),
        _ref("IRC", "§R403",   "2021", "Footings — slab-on-grade minimum 3.5 in. with rebar"),
        _ref("IECC", "§R401",  "2021", "Energy efficiency compliance — residential prescriptive path"),
        _ref("IECC", "§C401",  "2021", "Energy efficiency compliance — commercial prescriptive / performance paths"),
        _ref("IFC", "§903",    "2021", "Automatic sprinkler systems for applicable occupancies"),
        _ref("TAS", "§4.1",    "",     "Texas Accessibility Standards — mandatory for all TX commercial buildings"),
        _ref("Austin Energy Green Building", "§1-star", "", "Minimum rating for all new Austin residential construction"),
    ],
    special_requirements=[
        "All new residential construction must achieve Austin Energy Green Building 1-star rating minimum",
        "Commercial buildings must file TDLR accessibility review before permit issuance",
        "Special inspections (IBC §1705) required: concrete, masonry, soils, high-strength bolting, welding",
        "Certificate of Occupancy (CO) required before building may be occupied",
        "Separate sub-permits required for: electrical, plumbing, mechanical, fire suppression, grading/excavation",
        "FEMA flood zone sites require elevation certificate and may require variance from Watershed Protection Dept.",
        "Austin Water will not connect new service until structural frame inspection is passed",
    ],
    structural_review_threshold_sqft=0,        # ALL new construction requires structural review
    energy_compliance_threshold_sqft=0,        # ALL new construction requires energy compliance
    site_plan_review_threshold_sqft=0,
    fire_suppression_threshold_sqft=5000,
)


# ─────────────────────────────────────────────────────────────────
#  APPLICATION TYPE — DEM (Demolition)
# ─────────────────────────────────────────────────────────────────

DEM_CONFIG = ApplicationTypeConfig(
    code=AppTypeCode.DEMOLITION,
    label="Demolition",
    description=(
        "Use for complete or partial removal of structures. "
        "Required before new construction permit can be issued on same footprint."
    ),
    required_documents=[
        _doc("Demolition permit application",
             "Completed form via Austin Build + Connect portal"),
        _doc("Site plan",
             "Showing structure(s) to be demolished, proximity to property lines, and any structures to remain"),
        _doc("Asbestos and lead-based paint survey",
             "By Texas-licensed inspector — required for ALL structures built before 1980 "
             "(EPA NESHAP: notify 10 days before demolition if asbestos present)"),
        _doc("Utility disconnect confirmations",
             "Written confirmation from Austin Energy, Austin Water, and gas provider that utilities are disconnected"),
        _doc("Erosion / sedimentation control plan",
             "TCEQ-compliant erosion controls",
             mandatory=False,
             condition="Site disturbance > 1 acre"),
        _doc("Tree protection plan",
             "Engineered tree protection plan for Heritage Trees within 150% of critical root zone",
             mandatory=False,
             condition="Heritage Trees (≥19 in. diameter) are present within 150% critical root zone"),
        _doc("Waste management / recycling plan",
             "Austin Resource Recovery C&D waste diversion plan",
             mandatory=False,
             condition="Structure > 5,000 sq ft (ARR strongly encourages for all demos)"),
        _doc("Historic review approval",
             "Austin Historic Landmark Commission review and approval",
             mandatory=False,
             condition="Structure is individually listed or in an Austin Historic District"),
    ],
    code_references=[
        _ref("Austin City Code", "§25-11-1", "", "Austin demolition permit requirements"),
        _ref("TX Health & Safety Code", "§361", "", "Solid waste and asbestos disposal regulations"),
        _ref("IFC", "§3303",   "2021", "Demolition safety requirements"),
        _ref("Austin City Code", "§25-8-641", "", "Heritage Tree protection during demolition"),
        _ref("40 CFR", "§61.145", "", "EPA NESHAP — asbestos notification required 10 days before demolition"),
    ],
    special_requirements=[
        "EPA NESHAP (40 CFR §61.145): written notification to EPA Region 6 required ≥10 working days "
        "before demolition if regulated asbestos-containing material (ACM) is present",
        "All utility services must be disconnected and confirmed in writing before permit issuance",
        "Historical review mandatory if structure is in an Austin Historic District or individually listed",
        "Grading permit required if demolition changes existing drainage patterns",
        "Contractor must maintain erosion controls until site is stabilized with vegetation or impervious cover",
    ],
)


# ─────────────────────────────────────────────────────────────────
#  UNIVERSAL REQUIRED DOCS (all applications)
# ─────────────────────────────────────────────────────────────────

AUSTIN_UNIVERSAL_DOCS = [
    _doc("Permit application form",
         "Completed via Austin Build + Connect portal (https://abc.austintexas.gov)"),
    _doc("Site plan to scale",
         "Property boundaries, existing and proposed structures, setbacks, easements — must be drawn to scale"),
    _doc("Proof of property ownership",
         "Deed, title, or notarized authorization letter from property owner"),
    _doc("Travis County Appraisal District (TCAD) parcel number",
         "Found at www.traviscad.org — enter on all application forms"),
    _doc("Certificate of Occupancy (CO)",
         "Existing CO for the structure",
         mandatory=False,
         condition="Modifying or adding to an existing permitted structure"),
]


# ─────────────────────────────────────────────────────────────────
#  ASSEMBLED CityConfig — AUSTIN
# ─────────────────────────────────────────────────────────────────

AUSTIN = CityConfig(
    city_name="Austin",
    state="TX",
    county="Travis",
    timezone="America/Chicago",

    portal_url="https://abc.austintexas.gov",
    permit_office_phone="512-978-4000",
    permit_office_email="dsd@austintexas.gov",
    permit_office_address="6310 Wilhelmina Delco Dr, Austin, TX 78752",
    permit_office_hours="Mon–Fri 7:30am–4:30pm (closed 12–1pm Tue/Wed for walk-ins)",

    adopted_codes=AdoptedCodes(
        building="2021 International Building Code (IBC) with City of Austin local amendments",
        residential="2021 International Residential Code (IRC) with City of Austin local amendments",
        electrical="2020 National Electrical Code (NEC 70) — Austin Energy amendments apply",
        plumbing="2021 Uniform Plumbing Code (UPC)",
        mechanical="2021 International Mechanical Code (IMC)",
        energy="2021 International Energy Conservation Code (IECC) — Climate Zone 2",
        fire="2021 International Fire Code (IFC) — Austin Fire Department local amendments",
        accessibility="Americans with Disabilities Act (ADA) + Texas Accessibility Standards (TAS) — TDLR review required",
        green_building="Austin Energy Green Building Program — min 1-star for new residential",
        local_amendments_url="https://www.austintexas.gov/department/building-criteria-manual",
    ),

    zoning={
        "residential": RESIDENTIAL_ZONING,
        "industrial":  INDUSTRIAL_ZONING,
    },

    application_types={
        "REN": REN_CONFIG,
        "NEW": NEW_CONFIG,
        "DEM": DEM_CONFIG,
    },

    universal_required_docs=AUSTIN_UNIVERSAL_DOCS,

    general_notes=[
        "Austin uses a concurrent review process — building, electrical, plumbing, and mechanical are reviewed in parallel.",
        "Typical permit review times: residential 4–6 weeks, commercial 8–14 weeks (Express Review available for fee).",
        "All inspections must be scheduled via the Austin Build + Connect portal or by calling 512-978-4000.",
        "Texas state law (HB 2439) prohibits cities from restricting building materials approved by national codes.",
        "Austin Energy will not energize a new service until final electrical inspection is passed.",
        "Austin Water CCN (Certificate of Convenience and Necessity) area — all water/wastewater connections through Austin Water.",
    ],
)
