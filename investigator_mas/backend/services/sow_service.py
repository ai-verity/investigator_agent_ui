"""
backend/services/sow_service.py
================================
SOW interview question catalogue, per-answer NIM validation,
and 3-agent CrewAI crew (Intake Validator → Code Expert → SOW Writer).

All LLM/crew logic lives here — zero HTTP, zero Streamlit.
"""

import json
import os
from typing import Generator
from backend.agents.sow_crew import SOWCrew
from backend.models.schemas import PermitSession, SOWInput, SOWResponsePayload

ps = None


def generate_sow(input: SOWInput):
    city = "austin"
    if input.project_address:
        addr = input.project_address.lower()
        if "austin" in addr:
            city = "austin"
    sc = SOWCrew(city)
    global ps
    if not ps:
        ps = PermitSession(
            city=city,
            project_address=input.project_address,
            owner_name=input.owner_name,
            application_type=input.application_type,
            zoning_type=input.zoning_type,
            short_scope=input.sow_text,
        )
    question_id, question, is_done, generated_sow = sc.run_interactive(
        input.curr_response, ps
    )
    return SOWResponsePayload(
        application_id=input.application_id,
        next_question_id=str(question_id),
        next_question=question,
        is_done=is_done,
        generated_sow=generated_sow,
    )


# # ── NIM config ─────────────────────────────────────────────────────────────────

# invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
# stream = False

# def _get_nim_headers() -> dict:
#     api_key = os.environ.get("NVIDIA_API_KEY", "").strip()

#     if not api_key:
#         print("🚨 WARNING: NVIDIA_API_KEY is missing or empty!")

#     return {
#         "Authorization": f"Bearer {api_key}",
#         "Accept": "text/event-stream" if stream else "application/json",
#     }

# # ── Interview catalogue ────────────────────────────────────────────────────────

# INTERVIEW_QUESTIONS: list[dict] = [
#     {
#         "key": "project_type",
#         "question": "What type of construction project is this? (e.g., new single-family residence, room addition, garage conversion to ADU, interior remodel, detached accessory structure)",
#         "hint": "Project type determines which Austin code chapter and permit track applies.",
#     },
#     {
#         "key": "property_address",
#         "question": "What is the full site address including zip code? Do you know the legal description — lot, block, and subdivision name?",
#         "hint": "Austin DSD requires the exact address and legal description on every permit.",
#     },
#     {
#         "key": "zoning_and_overlay",
#         "question": "What is the property's zoning district and any overlay districts? (e.g., SF-3, SF-6, MF-2, CS, TOD, Waterfront Overlay, Historic District)",
#         "hint": "Zoning controls setbacks, impervious cover %, max height, and use restrictions.",
#     },
#     {
#         "key": "square_footage",
#         "question": "What is the total square footage? Break it down: conditioned living space, covered-but-unconditioned areas, and total impervious cover added or removed.",
#         "hint": "SF-3 zones cap total impervious cover at 45% of lot area.",
#     },
#     {
#         "key": "foundation",
#         "question": "What foundation type will be used? (Slab-on-grade, monolithic, pier & beam, stem wall, drilled piers) Who is responsible — homeowner or licensed contractor? Will engineered drawings be provided?",
#         "hint": "Expansive clay soils in Austin often require a geotechnical report and PE-stamped plans.",
#     },
#     {
#         "key": "structural_framing",
#         "question": "Describe all structural and framing work: wall framing system, roof system (stick-framed or trusses), ceiling heights, and any load-bearing wall removal.",
#         "hint": "Removal of any load-bearing wall requires a PE or architect stamp in Austin.",
#     },
#     {
#         "key": "roofing",
#         "question": "Describe the roofing scope: new or re-roof? Material? Roof pitch? Underlayment spec? Is this in a Wildland-Urban Interface (WUI) zone?",
#         "hint": "WUI zones require Class A rated roofing material per Austin Code §25-12-3.",
#     },
#     {
#         "key": "electrical",
#         "question": "Describe ALL electrical work: new service or existing? Panel upgrade? New branch circuits (list each purpose)? Solar PV? Homeowner or licensed master electrician (TDLR license #)?",
#         "hint": "Austin Energy requires separate ESA for new or upgraded electrical service.",
#     },
#     {
#         "key": "plumbing",
#         "question": "Describe ALL plumbing work: new fixtures (list each), water heater type and fuel source, any drain/waste/vent rerouting, water service size? Homeowner or licensed plumber (TSBPE license #)?",
#         "hint": "Austin Water requires separate permits for meter work and backflow prevention.",
#     },
#     {
#         "key": "mechanical_hvac",
#         "question": "Describe ALL HVAC/mechanical work: new or replacement? Equipment type and capacity (tons/BTU)? New ductwork? Gas line work? Ventilation strategy? Homeowner or licensed HVAC contractor (TDLR license #)?",
#         "hint": "2021 IECC requires Manual J load calculations for all new HVAC equipment in Austin.",
#     },
#     {
#         "key": "insulation_energy",
#         "question": "Describe insulation and energy compliance: wall R-value, ceiling/attic R-value, floor insulation (if pier & beam), window specs (U-factor and SHGC), prescriptive or performance path?",
#         "hint": "Austin Climate Zone 2 prescriptive path requires R-49 ceiling, R-13+5ci walls per 2021 IECC.",
#     },
#     {
#         "key": "exterior_envelope",
#         "question": "Describe exterior envelope finishes: wall cladding material, weather-resistive barrier product, exterior door specs, and any new or replaced windows?",
#         "hint": "All new windows must meet egress requirements per IRC R310 (min 5.7 sq ft net opening).",
#     },
#     {
#         "key": "demolition",
#         "question": "Is any demolition involved? If yes — what is being demolished? Has an asbestos and lead-based paint survey been completed? (Required for pre-1980 structures.)",
#         "hint": "Austin requires TCEQ notification for demolition of structures ≥ 260 sf with regulated ACM.",
#     },
#     {
#         "key": "contractor_info",
#         "question": "Who is the General Contractor of record? If licensed GC — full name, company, TX GC license #, phone, email. If owner-builder — confirm owner will occupy and has not sold an owner-built home in the past 12 months.",
#         "hint": "Owner-builder exemption per Texas Occupations Code §53.001 and §1151.004.",
#     },
#     {
#         "key": "project_timeline",
#         "question": "What is the estimated construction start date and expected completion timeline? How many phases (if any)?",
#         "hint": "Austin building permits expire after 180 days of inactivity; one 180-day extension available.",
#     },
# ]

# # TOTAL_QUESTIONS = len(INTERVIEW_QUESTIONS)
# TOTAL_QUESTIONS = 5


# def get_question(index: int) -> InterviewQuestion | None:
#     if index < 0 or index >= TOTAL_QUESTIONS:
#         return None
#     q = INTERVIEW_QUESTIONS[index]
#     return InterviewQuestion(
#         index=index,
#         total=TOTAL_QUESTIONS,
#         key=q["key"],
#         question=q["question"],
#         hint=q["hint"],
#     )


# # ── Per-answer NIM validation (fast, no CrewAI) ────────────────────────────────


# def validate_answer(question_text: str, answer: str) -> ValidateAnswerResponse:
#     try:
#         payload = {
#             "model": "google/gemma-3-27b-it",
#             "messages": [
#                 {
#                     "role": "system",
#                     "content": (
#                         "You are a senior permit technician at the Austin Development "
#                         "Services Department. Determine whether the applicant's answer "
#                         "is sufficiently specific for an Austin DSD building permit. "
#                         "Be strict but fair."
#                     ),
#                 },
#                 {
#                     "role": "user",
#                     "content": (
#                         f'Interview question: "{question_text}"\n'
#                         f'Applicant answer: "{answer}"\n\n'
#                         "Reply with EXACTLY one of:\n"
#                         "  SUFFICIENT\n"
#                         "  CLARIFY: <one concise follow-up asking for the specific missing detail>"
#                     ),
#                 },
#             ],
#             "max_tokens": 512,
#             "temperature": 0.20,
#             "top_p": 0.70,
#             "stream": stream,
#         }

#         response = requests.post(invoke_url, headers=_get_nim_headers(), json=payload)

#         # 1. Catch HTTP errors immediately to see the REAL error message
#         if not response.ok:
#             print(f"API Error {response.status_code}: {response.text}")
#             # Fallback so your app doesn't crash during the interview
#             return ValidateAnswerResponse(sufficient=True)

#         if stream:
#             for line in response.iter_lines():
#                 if line:
#                     print(line.decode("utf-8"))
#             return ValidateAnswerResponse(
#                 sufficient=True
#             )  # Handle stream return logic as needed
#         else:
#             # 2. Safely parse the JSON now that we know it's a 200 OK
#             response_data = response.json()
#             print("Raw JSON Data:", response_data)

#             # 3. Use dictionary syntax, not OpenAI object dot-notation
#             text = response_data["choices"][0]["message"]["content"].strip()
#             print("Parsed Response:", text)

#             if text.upper().startswith("SUFFICIENT"):
#                 return ValidateAnswerResponse(sufficient=True)
#             if text.upper().startswith("CLARIFY:"):
#                 return ValidateAnswerResponse(
#                     sufficient=False, follow_up=text[len("CLARIFY:") :].strip()
#                 )

#             return ValidateAnswerResponse(sufficient=True)

#     except Exception as e:
#         print(f"Exception during validation: {e}")
#         return ValidateAnswerResponse(sufficient=True)


# # ── CrewAI SOW crew ────────────────────────────────────────────────────────────


# # def _crewai_llm() -> LLM:
# #     return LLM(
# #         model=f"openai/{NIM_MODEL}",
# #         base_url=NIM_BASE_URL,
# #         api_key=_nim_api_key(),
# #         temperature=0.2,
# #         max_tokens=4096,
# #     )


# # def generate_sow_stream(
# #     collected_data: dict,
# # ) -> Generator[SOWProgressEvent, None, None]:
# #     """
# #     Runs the 3-agent SOW crew and yields SOWProgressEvent objects.
# #     FastAPI router converts these to Server-Sent Events.
# #     """
# #     yield SOWProgressEvent(
# #         stage="validating",
# #         message="Intake Validator: checking completeness…",
# #         progress=5,
# #     )

# #     try:
# #         llm = _crewai_llm()
# #         data_json = json.dumps(collected_data, indent=2)

# #         intake = Agent(
# #             role="Permit Intake Validator",
# #             goal="Verify all data meets Austin DSD IHB150 requirements.",
# #             backstory="15-year DSD veteran who processes hundreds of applications per month.",
# #             llm=llm,
# #             verbose=True,
# #             allow_delegation=False,
# #         )
# #         code_exp = Agent(
# #             role="Austin Building Code Authority",
# #             goal="Map every project aspect to exact code sections with citations.",
# #             backstory="ICC-certified Building Official and licensed TX Architect. Cites exact IRC, IBC, IECC, NEC, LDC §25 sections.",
# #             llm=llm,
# #             verbose=True,
# #             allow_delegation=False,
# #         )
# #         writer = Agent(
# #             role="SOW Technical Writer",
# #             goal="Draft a complete, legally defensible Scope of Work that passes DSD plan review first time.",
# #             backstory="Construction attorney and licensed TX GC. Known internally at DSD as the gold standard for SOW documents.",
# #             llm=llm,
# #             verbose=True,
# #             allow_delegation=False,
# #         )

# #         t1 = Task(
# #             description=(
# #                 f"Validate this permit application data against Austin DSD IHB150 requirements:\n\n"
# #                 f"```json\n{data_json}\n```\n\n"
# #                 "Output: DATA COMPLETENESS | CONSISTENCY CHECK | CONTRACTOR LICENSING | VALIDATED DATA"
# #             ),
# #             expected_output="Structured validation report with all four sections.",
# #             agent=intake,
# #         )

# #         yield SOWProgressEvent(
# #             stage="code_analysis",
# #             message="Code Expert: mapping project to IRC, IBC, IECC, NEC, LDC §25…",
# #             progress=35,
# #         )

# #         t2 = Task(
# #             description=(
# #                 f"Produce a comprehensive code compliance analysis for this Austin, TX project:\n\n"
# #                 f"```json\n{data_json}\n```\n\n"
# #                 "Cover with exact citations: PRIMARY CODES | ZONING | STRUCTURAL | ELECTRICAL | "
# #                 "PLUMBING | MECHANICAL | ENERGY | FIRE/LIFE SAFETY | INSPECTIONS | SPECIAL APPROVALS"
# #             ),
# #             expected_output="Numbered code compliance report with exact citations for every trade.",
# #             agent=code_exp,
# #         )

# #         yield SOWProgressEvent(
# #             stage="writing",
# #             message="SOW Writer: drafting formal Scope of Work…",
# #             progress=65,
# #         )

# #         t3 = Task(
# #             description=(
# #                 f"Draft the final Scope of Work. Project data:\n```json\n{data_json}\n```\n\n"
# #                 "REQUIRED SECTIONS: PROJECT OVERVIEW | PARTIES & RESPONSIBILITIES | "
# #                 "SCOPE BY TRADE (Foundation | Framing | Roofing | Envelope | HVAC | Plumbing | Electrical | Insulation) | "
# #                 "DEMOLITION (omit if N/A) | ENERGY CODE COMPLIANCE PATH | REQUIRED INSPECTIONS | LEGAL ATTESTATION\n\n"
# #                 "REQUIREMENTS: formal prose, 700-1400 words, every code citation as (IRC R302.1), "
# #                 "owner/GC details verbatim. Start with 'PROJECT OVERVIEW'."
# #             ),
# #             expected_output="Complete SOW document 700-1400 words beginning with 'PROJECT OVERVIEW'.",
# #             agent=writer,
# #         )

# #         crew = Crew(
# #             agents=[intake, code_exp, writer],
# #             tasks=[t1, t2, t3],
# #             process=Process.sequential,
# #             verbose=True,
# #             memory=False,
# #         )
# #         result = crew.kickoff()

# #         yield SOWProgressEvent(
# #             stage="done",
# #             message="Scope of Work generated.",
# #             progress=100,
# #             result=str(result).strip(),
# #         )

# #     except Exception as exc:
# #         yield SOWProgressEvent(stage="error", message=f"Crew error: {exc}", progress=0)
