"""
New York City — Permit Configuration
=====================================
Jurisdiction: NYC Department of Buildings (DOB)

Code references:
  NYC Construction Codes (2022 edition):
    - NYC Building Code (BC)  — based on 2015 IBC with extensive local amendments
    - NYC Residential Code (RC) — based on 2015 IRC with local amendments
    - NYC Mechanical Code (MC)
    - NYC Plumbing Code (PC)
    - NYC Fuel Gas Code (FGC)
    - NYC Fire Code (FC)       — FDNY enforcement
  NYC Electrical Code (NEC 2011 with local amendments) — DOB/Con Edison
  NYC Energy Conservation Code (NYCECC 2020) — based on ASHRAE 90.1-2016
  NYC Zoning Resolution (ZR) — administered by NYC Department of City Planning (DCP)
  Local Law 97 of 2019 (LL97) — building decarbonization / carbon caps
  Local Law 26 of 2004       — high-rise sprinkler requirements
  ADA + NYC Human Rights Law  — accessibility
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
#  Helpers
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
#  NYC residential districts: R1 (lowest density) through R10 (highest)
# ─────────────────────────────────────────────────────────────────

RESIDENTIAL_ZONING = ZoningConfig(
    type=ZoningTypeCode.RESIDENTIAL,
    label="Residential (R1 through R10 districts)",
    subzones=["R1-1", "R1-2", "R2", "R3", "R3A", "R4", "R4A", "R5",
              "R6", "R6A", "R7", "R7A", "R8", "R8A", "R9", "R10"],
    setbacks=SetbackRule(
        front_ft=10,    # R3-R5 contextual: matches adjacent buildings; R6+ varies
        rear_ft=30,     # minimum rear yard — R1/R2: 40 ft; R3-R5: 30 ft
        side_ft=5,      # R3-R5: 8 ft one side; R6+: 0 ft (zero-lot-line permitted)
        street_side_ft=10,
        narrative=(
            "Front yard: R1-R2 min 15 ft; R3-R5 contextual (matches block average). "
            "Rear yard: R1-R2 min 40 ft; R3-R5 min 30 ft; R6-R10 min 30 ft. "
            "Side yards: R1-R2 min 8 ft each side; R3-R5 min 8 ft one side, 5 ft other. "
            "R6-R10 tower-on-a-base districts: sky exposure plane controls height. "
            "Ref: NYC Zoning Resolution (ZR) §23-45 through §23-47 (yard regulations)."
        ),
    ),
    max_height_ft=35,       # R1-R5 low density; R6+ governed by FAR + sky exposure
    max_stories=3,          # R1-R5; R6-R10 can go much higher via FAR
    max_lot_coverage_pct=35,  # R1-R2; increases up to 70% for R6-R10 with bonuses
    max_far=0.5,            # R1-1 base FAR; R10 can reach FAR 10.0
    height_limits_narrative=(
        "R1-R2: max 35 ft / 2.5 stories. R3-R5: max 35 ft contextual. "
        "R6-R10: no absolute height limit — governed by Floor Area Ratio (FAR) and "
        "sky exposure plane. R10 allows FAR up to 12.0 with inclusionary bonuses. "
        "Ref: ZR §23-631 through §23-694 (height and setback rules)."
    ),
    lot_coverage_narrative=(
        "R1-R2: max 35% lot coverage. R3-R5: max 55%. "
        "R6-R10 contextual: governed by FAR (Floor Area Ratio), not lot coverage. "
        "Maximum FAR ranges from 0.5 (R1-1) to 10.0 (R10) before inclusionary bonuses. "
        "Ref: ZR §23-141 through §23-145 (floor area regulations)."
    ),
    additional_notes=(
        "All alterations in NYC require DOB NOW Build filing — paper filing phased out. "
        "Landmark buildings and Historic Districts require LPC (Landmarks Preservation Commission) approval. "
        "Local Law 97 (2019): buildings >25,000 sq ft face carbon emissions caps starting 2024 — "
        "energy upgrades may be required before permit approval. "
        "HPD (Housing Preservation & Development) approval needed for rent-stabilized/controlled units. "
        "Ref: NYC Admin Code §28-101 (work permits); ZR §72-21 (variances)."
    ),
    code_references=[
        _ref("NYC ZR", "§23-00",  "2024", "NYC residential district use regulations"),
        _ref("NYC ZR", "§23-45",  "2024", "Yard regulations for residential districts"),
        _ref("NYC ZR", "§23-141", "2024", "Floor area ratio (FAR) for residential districts"),
        _ref("NYC ZR", "§23-631", "2024", "Height and setback regulations"),
        _ref("NYC Admin Code", "§28-101", "2022", "Work permit requirements"),
        _ref("Local Law", "§97",  "2019", "Building decarbonization carbon caps (LL97)"),
    ],
)


# ─────────────────────────────────────────────────────────────────
#  ZONING — Industrial / Commercial
#  NYC commercial districts: C1–C8; manufacturing: M1–M3
# ─────────────────────────────────────────────────────────────────

INDUSTRIAL_ZONING = ZoningConfig(
    type=ZoningTypeCode.INDUSTRIAL,
    label="Commercial / Industrial (C1–C8 and M1–M3 districts)",
    subzones=["C1-1", "C1-2", "C2", "C4", "C5", "C6", "C8",
              "M1-1", "M1-2", "M1-5", "M2", "M3"],
    setbacks=SetbackRule(
        front_ft=0,
        rear_ft=0,
        side_ft=0,
        narrative=(
            "C1-C4 and M1-M3: generally 0 ft setbacks (built to street line). "
            "C5-C6 (Midtown/Downtown): governed by sky exposure plane and street wall rules. "
            "Special purpose districts (e.g., Hudson Yards, Special Midtown) have unique controls. "
            "Ref: ZR §32-00 (commercial districts); §42-00 (manufacturing districts)."
        ),
    ),
    max_height_ft=None,     # no absolute limit in C5/C6/M1 — FAR-governed
    max_stories=None,
    max_lot_coverage_pct=100,   # C5-C6 CBD: 100% lot coverage permitted
    max_far=15.0,               # C6-9 with bonuses; C1 base ~1.0
    height_limits_narrative=(
        "C1-C4: max building height 35–65 ft depending on district suffix. "
        "C5-C6 (Midtown, Downtown): unlimited height governed by FAR (up to 15.0 with bonuses). "
        "M1-M3 manufacturing: typically limited by FAR 1.0–5.0 depending on suffix. "
        "Special Midtown District (ZR §81): street wall + tower coverage rules apply. "
        "Ref: ZR §33-43 (commercial height); §43-43 (manufacturing height)."
    ),
    lot_coverage_narrative=(
        "C1-C2: max 60% lot coverage. C4-C6: up to 100% lot coverage in CBD. "
        "M1-M3: up to 100% lot coverage for industrial uses. "
        "FAR is the primary massing control for large commercial buildings. "
        "Ref: ZR §33-12 (commercial FAR); §42-12 (manufacturing FAR)."
    ),
    additional_notes=(
        "All commercial projects >5,000 sq ft require Special Inspection per NYC BC §1705. "
        "NYC FC (Fire Code) §903: automatic sprinklers required in all new commercial buildings. "
        "Local Law 26 (2004): existing high-rises must retrofit sprinklers by 2019 deadline. "
        "LL97 carbon caps apply to commercial buildings >25,000 sq ft — energy audit may be required. "
        "ADA + NYC Human Rights Law §8-107: accessibility compliance mandatory for all commercial uses. "
        "FDNY approval required for fire suppression, fuel storage, and place-of-assembly occupancies. "
        "Con Edison coordination required for new electrical service >200A."
    ),
    code_references=[
        _ref("NYC ZR", "§32-00",  "2024", "Commercial district use regulations"),
        _ref("NYC ZR", "§42-00",  "2024", "Manufacturing district use regulations"),
        _ref("NYC BC", "§1705",   "2022", "Special inspections for commercial construction"),
        _ref("NYC FC", "§903",    "2022", "Automatic fire suppression systems"),
        _ref("Local Law", "§26",  "2004", "High-rise sprinkler retrofit requirements"),
        _ref("Local Law", "§97",  "2019", "Carbon emissions caps for large buildings"),
        _ref("NYCECC", "§C401",   "2020", "Commercial energy compliance — ASHRAE 90.1-2016 path"),
    ],
)


# ─────────────────────────────────────────────────────────────────
#  APPLICATION TYPE — REN (Alteration)
#  NYC uses "Alteration Type 1 (Alt-1)", "Alt-2", "Alt-3" terminology
# ─────────────────────────────────────────────────────────────────

REN_CONFIG = ApplicationTypeConfig(
    code=AppTypeCode.RENOVATION,
    label="Alteration / Renovation (Alt-1, Alt-2, or Alt-3)",
    description=(
        "Alt-1: change of use, occupancy, or egress — requires new Certificate of Occupancy. "
        "Alt-2: multiple types of work not affecting CO (structural, MEP, facades). "
        "Alt-3: single minor item (one trade, no structural impact). "
        "File via DOB NOW: Build at dobonline.nyc.gov."
    ),
    required_documents=[
        _doc("DOB NOW: Build alteration application",
             "Filed online at dobonline.nyc.gov — select correct Alt type (1, 2, or 3)"),
        _doc("Existing conditions drawings",
             "Measured drawings of existing conditions — floor plans, sections, elevations"),
        _doc("Proposed construction drawings",
             "Architect/engineer stamped drawings (RA or PE licensed in NY State) — "
             "floor plans, RCP, sections, elevations, details at min 1/8\" scale"),
        _doc("Structural drawings and calculations",
             "PE-stamped structural drawings for any load-bearing modifications",
             mandatory=False,
             condition="Structural elements, floor systems, or facade are being altered"),
        _doc("Energy compliance — NYCECC",
             "COMcheck or REScheck demonstrating NYCECC 2020 compliance",
             mandatory=False,
             condition="Envelope, HVAC, or lighting systems are being modified"),
        _doc("MEP drawings",
             "Mechanical, electrical, and plumbing drawings by licensed engineers",
             mandatory=False,
             condition="Any MEP system is being installed, replaced, or modified"),
        _doc("Landmarks Preservation Commission (LPC) approval",
             "LPC Certificate of Appropriateness or No-Action Letter",
             mandatory=False,
             condition="Building is a NYC Landmark or within an Historic District"),
        _doc("Asbestos investigation report (ACP-5 or ACP-7)",
             "NYC DEP-licensed inspector report — ACP-5 (no asbestos) or ACP-7 (abatement required)",
             mandatory=False,
             condition="Any demolition, disturbance, or renovation of pre-1987 building materials"),
        _doc("Lead-based paint survey",
             "XRF survey by certified inspector",
             mandatory=False,
             condition="Disturbance of surfaces in pre-1960 buildings (pre-1978 for child-occupied facilities)"),
        _doc("HPD approval",
             "NYC Housing Preservation & Development sign-off",
             mandatory=False,
             condition="Building has rent-stabilized or rent-controlled units"),
        _doc("Owner's authorization / Tenant Permission",
             "Notarized owner authorization if applicant is not the owner"),
    ],
    code_references=[
        _ref("NYC BC", "§28-101",  "2022", "Work permit requirements — when a permit is required"),
        _ref("NYC BC", "§28-105",  "2022", "Permit application filing requirements"),
        _ref("NYC BC", "§34-01",   "2022", "Alterations to existing buildings — compliance path"),
        _ref("NYC BC", "§1002",    "2022", "Means of egress for altered occupancies"),
        _ref("NYC RC", "§R102.7",  "2022", "Existing residential buildings — alteration standards"),
        _ref("NYCECC", "§R503",    "2020", "Residential energy compliance for alterations"),
        _ref("NYCECC", "§C503",    "2020", "Commercial energy compliance for alterations"),
        _ref("NYC Admin Code", "§24-146", "2022", "Asbestos regulations (DEP) — ACP-5/ACP-7 requirements"),
        _ref("NYC ZR", "§72-21",   "2024", "Board of Standards and Appeals variance procedure"),
    ],
    special_requirements=[
        "All Alt-1 applications require a Progress Inspection by a Special Inspector before CO issuance",
        "Facade work on buildings >6 stories requires compliance with Local Law 11 (Facade Inspection Safety Program — FISP)",
        "Asbestos: NYC DEP ACP-5 form required before DOB will approve any demolition/renovation permit in pre-1987 buildings",
        "Lead paint: EPA RRP rule applies — use certified renovator for pre-1978 child-occupied facilities",
        "Elevator alterations require separate NYC DOB Elevator Unit filing and ConEd coordination",
        "All drawings must be filed by a NYS-licensed Registered Architect (RA) or Professional Engineer (PE)",
        "LL97 compliance check required for buildings >25,000 sq ft — alteration may trigger carbon cap review",
    ],
    structural_review_threshold_sqft=0,
    energy_compliance_threshold_sqft=1000,
    site_plan_review_threshold_sqft=5000,
)


# ─────────────────────────────────────────────────────────────────
#  APPLICATION TYPE — NEW (New Building)
# ─────────────────────────────────────────────────────────────────

NEW_CONFIG = ApplicationTypeConfig(
    code=AppTypeCode.NEW,
    label="New Building (NB)",
    description=(
        "Filed as a New Building (NB) application via DOB NOW: Build. "
        "Covers construction of entirely new structures on vacant lots or "
        "after full demolition of an existing building."
    ),
    required_documents=[
        _doc("DOB NOW: Build new building application",
             "Online filing at dobonline.nyc.gov — select 'New Building (NB)'"),
        _doc("Architectural drawings — complete set",
             "NYS RA-stamped drawings: zoning analysis, site plan, floor plans, "
             "elevations, sections, details — min 1/8\" scale"),
        _doc("Zoning analysis",
             "Detailed ZR compliance memo: FAR, yard, height/setback, use group, parking"),
        _doc("Structural drawings and calculations",
             "NYS PE-stamped structural drawings, specifications, and calculations including "
             "foundation design, wind/seismic analysis per ASCE 7-22"),
        _doc("Geotechnical / soil boring report",
             "Soil investigation report from licensed geotechnical engineer",
             mandatory=False,
             condition="Foundation on rock requires NB-3 sign-off; soft soils trigger enhanced boring requirements"),
        _doc("MEP construction documents",
             "Full mechanical, electrical, and plumbing drawings by NYS-licensed engineers"),
        _doc("Energy compliance — NYCECC 2020",
             "COMcheck (commercial) or REScheck (1-2 family) energy model; "
             "LEED / WELL documentation if pursuing green certification"),
        _doc("Stormwater management plan",
             "NYC DEP stormwater pollution prevention plan (SWPPP) per SPDES General Permit",
             mandatory=False,
             condition="Site disturbance ≥1 acre or in a combined sewer overflow (CSO) area"),
        _doc("Fire protection system drawings",
             "FDNY-reviewed sprinkler and standpipe system drawings (NYC FC §903)",
             mandatory=False,
             condition="All new buildings except detached 1-2 family <3 stories"),
        _doc("Special inspections program",
             "Statement of Special Inspections per NYC BC §1705 — must be filed with application"),
        _doc("Site safety plan",
             "NYC DOB Site Safety Manager (SSM) plan for buildings >10 stories or >100 ft"),
        _doc("Utility service applications",
             "Con Edison (electric/gas), NYC Water Board DEP (water/sewer) service applications"),
        _doc("Environmental review (CEQR)",
             "City Environmental Quality Review — Full EAS or EIS",
             mandatory=False,
             condition="Project exceeds CEQR thresholds: typically >200 residential units or >200,000 sq ft commercial"),
        _doc("Disability access compliance",
             "ADA + NYC BC Chapter 11 accessibility compliance drawings and narrative"),
    ],
    code_references=[
        _ref("NYC BC", "§28-104",  "2022", "Construction document filing requirements for new buildings"),
        _ref("NYC BC", "§1604",    "2022", "Structural design loads — wind, seismic, live, dead"),
        _ref("NYC BC", "§1705",    "2022", "Special inspections required for new construction"),
        _ref("NYC BC", "§1803",    "2022", "Soil investigation and foundation requirements"),
        _ref("NYC BC", "§11-00",   "2022", "Accessibility — ADA + NYC Human Rights Law"),
        _ref("NYC FC", "§903",     "2022", "Automatic sprinkler systems — required in all new buildings"),
        _ref("NYC FC", "§905",     "2022", "Standpipe systems for buildings >6 stories"),
        _ref("NYCECC", "§C401",    "2020", "Commercial energy compliance — prescriptive or performance path"),
        _ref("NYCECC", "§R401",    "2020", "Residential energy compliance"),
        _ref("NYC ZR", "§23-00",   "2024", "Residential zoning bulk and use requirements"),
        _ref("NYC ZR", "§33-00",   "2024", "Commercial zoning bulk and use requirements"),
        _ref("Local Law", "§97",   "2019", "LL97 carbon caps — new buildings must meet 2030 cap from day one"),
        _ref("ASCE", "§7-22",      "2022", "Minimum design loads — wind 110 mph (NYC), seismic SDC B"),
    ],
    special_requirements=[
        "All new buildings require a Certificate of Occupancy (CO) before occupancy — issued by DOB after final inspection",
        "Special Inspections (NYC BC §1705): concrete, masonry, steel, high-strength bolts, soils, fire-resistive construction",
        "Site Safety Manager (SSM) required for buildings >10 stories; Site Safety Coordinator for 7-9 stories",
        "NYC FC §903: sprinklers required in all new residential buildings (Local Law 58 of 2008 expanded requirement)",
        "LL97 compliance: new buildings >25,000 sq ft must demonstrate 2030 carbon cap compliance at permit stage",
        "CEQR: environmental review required if project exceeds thresholds — coordinate with DCP/CEQR Technical Manual",
        "Separate DOB filings required for: plumbing (PW1), sprinklers, standpipes, elevators, fuel oil burning equipment",
        "NYC Water Board: water/sewer tap application and DEP approval required before water service activation",
        "Con Edison: electric service coordination for buildings >800A — may require substation contribution",
        "1-2 family buildings ≤3 stories may use simplified NYC RC process — larger buildings use full NYC BC",
    ],
    structural_review_threshold_sqft=0,
    energy_compliance_threshold_sqft=0,
    site_plan_review_threshold_sqft=0,
    fire_suppression_threshold_sqft=0,     # ALL new NYC buildings require sprinklers
)


# ─────────────────────────────────────────────────────────────────
#  APPLICATION TYPE — DEM (Demolition)
# ─────────────────────────────────────────────────────────────────

DEM_CONFIG = ApplicationTypeConfig(
    code=AppTypeCode.DEMOLITION,
    label="Demolition (Full or Partial)",
    description=(
        "Full demolition: entire building razed. "
        "Partial demolition: structural removal filed as an Alt-1 or Alt-2. "
        "File via DOB NOW: Build — select 'Demolition (DM)'."
    ),
    required_documents=[
        _doc("DOB NOW: Build demolition application",
             "Online filing at dobonline.nyc.gov — select 'Demolition (DM)'"),
        _doc("NYC DEP asbestos investigation — ACP-5 or ACP-7",
             "Pre-demolition asbestos survey by NYC DEP-licensed investigator. "
             "ACP-5: no regulated ACM found. ACP-7: abatement plan required. "
             "DOB will NOT issue demolition permit without DEP sign-off."),
        _doc("Lead-based paint survey and abatement plan",
             "XRF survey + abatement plan by certified firm if pre-1978 building"),
        _doc("Utility disconnection confirmations",
             "Written disconnection letters from Con Edison (electric/gas) and NYC DEP (water/sewer) "
             "— required before permit issuance"),
        _doc("Site safety plan",
             "Demolition safety plan per NYC BC §3306 — must address adjacent structures, "
             "shoring, sidewalk protection, and dust/debris control"),
        _doc("Structural drawings — shoring and underpinning",
             "PE-stamped shoring and underpinning drawings for adjacent buildings",
             mandatory=False,
             condition="Demolition of attached building or any building sharing a party wall"),
        _doc("Landmarks Preservation Commission (LPC) approval",
             "LPC Certificate of Appropriateness for demolition",
             mandatory=False,
             condition="Building is a NYC Landmark or contributes to an Historic District"),
        _doc("CEQR / environmental review",
             "Environmental impact assessment",
             mandatory=False,
             condition="Site is in a potential contamination area (Phase I/II ESA may be required)"),
        _doc("Rodent extermination certification",
             "NYC DOHMH-required rat extermination before demolition begins"),
        _doc("Stormwater / erosion control plan",
             "SWPPP per NYC DEP SPDES GP",
             mandatory=False,
             condition="Site disturbance ≥1 acre"),
    ],
    code_references=[
        _ref("NYC BC", "§3306",    "2022", "Demolition safety requirements — site protection and adjacent structures"),
        _ref("NYC BC", "§3307",    "2022", "Protection of adjoining properties during demolition"),
        _ref("NYC Admin Code", "§24-146", "2022", "Asbestos regulations — DEP ACP-5/ACP-7 required pre-demolition"),
        _ref("NYC Admin Code", "§17-159", "2022", "Rodent extermination required before demolition"),
        _ref("NYC FC", "§3303",    "2022", "Fire safety during demolition operations"),
        _ref("NYC ZR", "§52-00",   "2024", "Non-conforming uses — demolition restrictions in some districts"),
        _ref("40 CFR", "§61.145",  "",     "EPA NESHAP — federal asbestos notification ≥10 days before demolition if ACM present"),
    ],
    special_requirements=[
        "NYC DEP ACP-5 or ACP-7 sign-off is an absolute prerequisite — DOB will not issue demo permit without it",
        "Con Edison and NYC DEP water/sewer disconnection letters required before permit issuance",
        "NYC BC §3307: license surveyor must document condition of all adjoining buildings before demolition begins",
        "Landmarks: LPC approval mandatory even for partial demolition of any exterior feature on a landmark building",
        "Rodent control: NYC Health Code §§153.09 requires pest extermination certificate before demolition",
        "Party wall buildings: PE-stamped shoring drawings required and neighbor notification under NYC BC §3309",
        "EPA NESHAP 40 CFR §61.145: notify EPA Region 2 ≥10 working days before demolition if regulated ACM found",
        "Post-demolition: site must be secured, graded, and seeded/paved within 30 days per NYC Admin Code",
    ],
)


# ─────────────────────────────────────────────────────────────────
#  UNIVERSAL REQUIRED DOCS (all NYC applications)
# ─────────────────────────────────────────────────────────────────

NYC_UNIVERSAL_DOCS = [
    _doc("DOB NOW: Build online filing",
         "All permit applications filed at dobonline.nyc.gov — paper filing no longer accepted"),
    _doc("Certificate of Occupancy (CO) or Letter of Completion",
         "Existing CO for the building — obtain from DOB BIS (Buildings Information System)",
         mandatory=False,
         condition="Altering, adding to, or demolishing an existing building"),
    _doc("NYS-licensed professional stamp",
         "All drawings must be signed/sealed by a NYS Registered Architect (RA) "
         "or Professional Engineer (PE) — digital seal accepted"),
    _doc("Property ownership documentation",
         "Current deed or notarized owner's authorization letter if applicant is not the owner"),
    _doc("NYC DOF property tax block and lot number",
         "Borough-Block-Lot (BBL) number — find at nyc.gov/finance or via ACRIS"),
    _doc("Workers' Compensation and General Liability insurance",
         "Certificates of insurance naming NYC DOB as additional insured — "
         "required before permit issuance"),
]


# ─────────────────────────────────────────────────────────────────
#  ASSEMBLED CityConfig — NEW YORK CITY
# ─────────────────────────────────────────────────────────────────

NEW_YORK_CITY = CityConfig(
    city_name="New York City",
    state="NY",
    county="Five Boroughs (Manhattan, Brooklyn, Queens, Bronx, Staten Island)",
    timezone="America/New_York",

    portal_url="https://dobonline.nyc.gov",
    permit_office_phone="212-566-5000",
    permit_office_email="dobcustomerservice@buildings.nyc.gov",
    permit_office_address="280 Broadway, New York, NY 10007 (Manhattan Borough Office)",
    permit_office_hours="Mon–Fri 8:30am–4:30pm (borough offices vary — check DOB website)",

    adopted_codes=AdoptedCodes(
        building="2022 NYC Building Code (BC) — based on 2015 IBC with extensive NYC amendments",
        residential="2022 NYC Residential Code (RC) — based on 2015 IRC, applies to 1-2 family",
        electrical="NYC Electrical Code — based on NEC 2011 with local amendments; enforced by DOB/Con Edison",
        plumbing="2022 NYC Plumbing Code (PC) — based on 2015 IPC with NYC amendments",
        mechanical="2022 NYC Mechanical Code (MC) — based on 2015 IMC with NYC amendments",
        energy="NYC Energy Conservation Code (NYCECC) 2020 — based on ASHRAE 90.1-2016",
        fire="2022 NYC Fire Code (FC) — enforced by FDNY; stricter than IFC in many areas",
        accessibility="ADA + NYC Building Code Chapter 11 + NYC Human Rights Law §8-107",
        green_building=(
            "NYC Green New Deal / LL97 (2019) carbon caps; "
            "LEED, WELL, Enterprise Green Communities accepted for affordable housing bonuses"
        ),
        local_amendments_url="https://www1.nyc.gov/site/buildings/codes/construction-codes.page",
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

    universal_required_docs=NYC_UNIVERSAL_DOCS,

    general_notes=[
        "NYC uses DOB NOW: Build for all permit filings — paper applications are no longer accepted.",
        "Typical review times: standard plan review 4–8 weeks; Accelerated Plan Review (APR) available for fee (5 business days).",
        "DOB Hub locations: Manhattan (280 Broadway), Brooklyn (210 Joralemon St), Queens (120-55 Queens Blvd), "
        "Bronx (1932 Arthur Ave), Staten Island (10 Richmond Terrace).",
        "All contractors must be NYC DOB-licensed; owner-builders permitted only for 1-2 family owner-occupied homes.",
        "Progressive enforcement: DOB Stop Work Orders (SWO) issued for violations — resolve before any permit can proceed.",
        "Special Inspection agencies must be NYC DOB-approved; list at nyc.gov/buildings.",
        "Local Law 97 (2019): buildings >25,000 sq ft face escalating carbon penalties starting 2024 — "
        "verify LL97 status before planning major alterations.",
        "NYC landmarks: even interior work on a designated landmark may require LPC review — check LPC map first.",
        "Tenant protection: HPD involvement required for occupied residential buildings — "
        "'Tenant Protection Plans' required for most alterations affecting occupied units (Local Law 55 of 2018).",
        "Expeditor services: most large projects use a NYC DOB expeditor; highly recommended for first-time filers.",
    ],
)
