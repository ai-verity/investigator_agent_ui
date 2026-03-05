"""
Permit Assistant Crew
─────────────────────
Agents:
  1. PermitIntakeAgent  — Conversational agent, asks ≤5 targeted questions,
                          extracts structured data from user responses.
  2. ScopeOfWorkAgent   — Generates a full SOW + compliance guidelines
                          based on city config + gathered session data.

The crew runs sequentially. The intake agent populates the session;
the SOW agent produces the final deliverable.
"""

import json
import os
from textwrap import dedent
from typing import Optional

from crewai import Agent, Crew, Process, Task
from crewai.tools import tool

from backend.models.schemas import PermitSession
from backend.tools.nim_llm import create_nim_llm
from backend.austin import *


# ─────────────────────────────────────────────
#  Shared LLM  (all agents use same NIM model)
# ─────────────────────────────────────────────


def _llm():
    return create_nim_llm()


# ─────────────────────────────────────────────
#  Helper: format city guidelines for prompt
# ─────────────────────────────────────────────


def _format_city_context(
    city_cfg, app_type: str, zoning_type: str, project_sqft: float = None
) -> str:
    """Delegate to the rich CityConfig.to_agent_context() method."""
    return city_cfg.to_agent_context(
        app_type=app_type,
        zoning_type=zoning_type,
        project_sqft=project_sqft,
    )


# ─────────────────────────────────────────────
#  SOWCrew — main class
# ─────────────────────────────────────────────


class SOWCrew:
    """
    Orchestrates the full permit assistance workflow.

    Usage:
        crew = SOWCrew(city="austin")
        # Interactive mode:
        crew.run_interactive()

        # Batch / demo mode (prefill session):
        session = PermitSession(city="austin", owner_name="Jane Doe", ...)
        result = crew.run_batch(session)
    """

    def __init__(self, city: str = "austin"):
        self.city_key = city
        self.city_cfg = AUSTIN
        self.llm = _llm()
        # self.image_tool = ImageAnalyzerTool()

    # ── Agents ────────────────────────────────

    def _intake_agent(self) -> Agent:
        return Agent(
            role="Permit Application Intake Specialist",
            goal=(
                "Gather all information needed for a complete permit application "
                "by asking clear, targeted questions — never more than 5 total. "
                "Extract structured data from user answers."
            ),
            backstory=dedent(f"""
                You are an experienced permit intake specialist at the City of
                {self.city_cfg.city_name} Development Services Department.
                You know exactly what information is needed for renovation, new
                construction, and demolition permits. You are friendly, concise,
                and ask only what is necessary. You batch related questions together
                to minimize burden on the applicant.
            """),
            llm=self.llm,
            #          tools=[self.image_tool],
            verbose=True,
            allow_delegation=False,
        )

    def _sow_agent(self) -> Agent:
        return Agent(
            role="Scope of Work & Compliance Analyst",
            goal=(
                "Generate a professional, code-compliant Scope of Work (SOW) document "
                "and provide actionable guidelines — citing specific building codes, "
                "required documents, and local amendments — to ensure a successful "
                "permit application."
            ),
            backstory=dedent(f"""
                You are a licensed building official and construction attorney
                specializing in {self.city_cfg.city_name} permitting. You have deep
                knowledge of the IBC, IRC, IECC, NEC, and all local amendments.
                You write clear, professional SOW documents that satisfy plan reviewers
                on first submission, minimizing costly re-submittals.
            """),
            llm=self.llm,
            #      tools=[self.image_tool],
            verbose=True,
            allow_delegation=False,
        )

    # ── Tasks ─────────────────────────────────

    def _intake_task(self, agent: Agent, session: PermitSession) -> Task:
        session_json = json.dumps(session.to_context_dict(), indent=2)
        # image_note = ""
        # if session.image_analyses:
        #     image_note = "\n\nImage analyses already completed:\n" + "\n---\n".join(
        #         session.image_analyses
        #     )

        return Task(
            description=dedent(f"""
                Review the current permit session data and determine what critical
                information is still missing. Generate the NEXT BEST QUESTION(S)
                to ask the applicant — grouped so that you ask at most 5 questions
                across the entire conversation.

                CURRENT SESSION DATA:
                {session_json}

                RULES:
                - Questions remaining allowed: {max(0, 5 - session.questions_asked)}
                - If all critical information is already present, set is_complete=true
                - Prioritize: occupancy type, project size, structural/MEP changes,
                  heritage trees (Austin), pre-1980 structure (asbestos risk)
                - Ask multiple related sub-questions in a single numbered question
                  to use your question budget efficiently
                - Keep tone professional but warm

                OUTPUT FORMAT (JSON):
                {{
                  "question": "The question text to present to user (null if complete)",
                  "is_complete": false,
                  "extracted_data": {{
                    "field_name": "value extracted from prior user input (if any)"
                  }}
                }}
            """),
            agent=agent,
            expected_output="JSON with question, is_complete, and extracted_data fields",
        )

    def _sow_task(self, agent: Agent, session: PermitSession) -> Task:
        session_json = json.dumps(session.to_context_dict(), indent=2)
        city_context = _format_city_context(
            self.city_cfg,
            session.application_type,
            session.zoning_type,
            project_sqft=session.project_size_sqft,
        )
        # image_note = ""
        # if session.image_analyses:
        #     image_note = "\n\n## Blueprint / Photo Analysis\n" + "\n---\n".join(
        #         session.image_analyses
        #     )

        return Task(
            description=dedent(f"""
                Generate a complete, professional permit package for this project.

                ## Session Data
                {session_json}

                ## City & Code Reference
                {city_context}

                ## Required Output Sections

                ### SCOPE OF WORK (SOW)
                Write a detailed, code-aware SOW suitable for submission with the
                permit application on behalf of the applicant. It must include:
                - Project description (address, owner, application type)
                - Detailed description of ALL proposed work
                - Materials and methods (reference specific code sections)
                - What is NOT included in this permit (exclusions)
                - Anticipated permit sub-types required (electrical, plumbing, etc.)

                As an addendum add the following 

                ### 1. REQUIRED DOCUMENTS CHECKLIST
                Based on application type + zoning, list every document needed,
                with a note on what each must contain.

                ### 2. CODE COMPLIANCE HIGHLIGHTS
                Call out the top 5–8 code sections most critical for this specific
                project, with plain-English explanation of what they require.

                ### 3. SUBMISSION TIPS
                Practical advice for a smooth first-pass approval in {self.city_cfg.city_name}.

                ### 4. WARNINGS & RED FLAGS
                Any potential issues that could cause rejection or costly revisions.

                Use professional, clear language. Cite code sections in brackets [IRC §R310].
            """),
            agent=agent,
            expected_output="Complete permit package document in markdown format",
        )

    # ── Public API ────────────────────────────

    def run_batch(self, session: PermitSession) -> str:
        """
        Run full pipeline on a pre-populated session (demo / API mode).
        Skips the intake Q&A and goes straight to SOW generation.
        """
        sow_agent = self._sow_agent()
        sow_task = self._sow_task(sow_agent, session)

        crew = Crew(
            agents=[sow_agent],
            tasks=[sow_task],
            process=Process.sequential,
            verbose=True,
        )
        result = crew.kickoff()
        session.generated_sow = str(result)
        return str(result)

    def run_interactive(
        self, user_response, initial_session: Optional[PermitSession] = None
    ) -> PermitSession:
        """
        Run a fully interactive conversational permit intake session.
        Returns the completed PermitSession with generated SOW.
        """
        session = initial_session or PermitSession(city=self.city_key)

        print(f"\n{'=' * 65}")
        print(f"  City of {self.city_cfg.city_name} Permit Application Assistant")
        print(f"  Development Services Department")
        print(f"{'=' * 65}")
        print("Welcome! I'll help you prepare a complete permit application.")
        print("You can attach blueprints or photos by entering the file path.")
        print("Type 'done' at any time to proceed with available information.\n")

        # ── Collect mandatory form fields upfront ──────────────────
        session.conversation_history.append({"role": "user", "content": user_response})

        # ── Conversational Q&A loop (≤5 questions) ─────────────────
        intake_agent = self._intake_agent()

        question = None

        if session.questions_asked < 5 and not session.is_complete:
            intake_task = self._intake_task(intake_agent, session)
            crew = Crew(
                agents=[intake_agent],
                tasks=[intake_task],
                process=Process.sequential,
                verbose=True,
            )

            raw = str(crew.kickoff())

            # Strip markdown fences
            clean = raw.strip()
            if "```" in clean:
                # pull out the JSON block between the fences
                clean = clean.split("```")
                # find the part that looks like JSON
                clean = next(
                    (p.lstrip("json").strip() for p in clean if "{" in p), clean[0]
                )

            try:
                response = json.loads(clean)
            except json.JSONDecodeError:
                # last resort: extract question with regex
                import re

                match = re.search(
                    r'"question"\s*:\s*"(.*?)"(?=\s*,\s*"is_complete")',
                    clean,
                    re.DOTALL,
                )
                response = {
                    "question": match.group(1).replace('\\"', '"') if match else raw,
                    "is_complete": False,
                    "extracted_data": {},
                }

            # Always ensure question is a plain string, never a JSON blob
            question = response.get("question") or ""
            if question.strip().startswith("{"):
                # agent returned JSON as the question text — extract it properly
                try:
                    inner = json.loads(question)
                    question = inner.get("question", question)
                except json.JSONDecodeError:
                    pass

            # # Parse agent response
            # try:
            #     # Strip markdown fences if present
            #     clean = raw.strip()
            #     if clean.startswith("```"):
            #         clean = "\n".join(clean.split("\n")[1:])
            #         clean = clean.rsplit("```", 1)[0]
            #     response = json.loads(clean)
            # except json.JSONDecodeError:
            #     # Fallback: treat as plain question
            #     response = {"question": raw, "is_complete": False, "extracted_data": {}}

            # Update session with extracted data
            extracted = response.get("extracted_data", {})
            self._apply_extracted_data(session, extracted)

            if response.get("is_complete"):
                session.is_complete = True
            question = response.get("question")
            if not question:
                session.is_complete = True

            # Present question to user
            session.questions_asked += 1
            print(f"\nQuestion {session.questions_asked}/5:")
            print(f"  {question}\n")

            # # Check for file attachment offer
            # if session.questions_asked == 1:
            #     print("  (You may also enter a file path to attach a blueprint/photo,")
            #     print("   or press Enter to skip)\n")

            # user_input = input("Your answer: ").strip()

            # if user_input.lower() == "done":
            #     session.is_complete = True
            #     break

            # Check if user provided a file path
            # if os.path.exists(user_input) and user_input.lower().endswith(
            #     (".jpg", ".jpeg", ".png", ".webp", ".pdf")
            # ):
            #     print("  📎 Analyzing attached file…")
            #     analysis = self.image_tool._run(user_input, context=session.short_scope)
            #     session.image_paths.append(user_input)
            #     session.image_analyses.append(f"File: {user_input}\n{analysis}")
            #     print(f"  ✓ File analyzed.\n")
            #     # Also record the text part of their answer
            #     user_text = input("  Any additional context for this file? ").strip()
            #     if user_text:
            #         user_input = f"[Attached: {user_input}] {user_text}"
            #     else:
            #         user_input = f"[Attached and analyzed: {user_input}]"

            # Store in conversation history
            session.conversation_history.append(
                {"role": "assistant", "content": question}
            )
            session.generated_sow = None
        else:
            session.generated_sow = self.run_batch(session)

        return (
            session.questions_asked,
            question,
            session.is_complete,
            session.generated_sow,
        )

    def _apply_extracted_data(self, session: PermitSession, data: dict):
        """Apply extracted fields from agent response to session."""
        field_map = {
            "project_size_sqft": "project_size_sqft",
            "existing_structure_sqft": "existing_structure_sqft",
            "num_stories": "num_stories",
            "occupancy_type": "occupancy_type",
            "structural_changes": "structural_changes",
            "mep_changes": "mep_changes",
            "heritage_trees_nearby": "heritage_trees_nearby",
            "pre_1980_structure": "pre_1980_structure",
            "special_conditions": "special_conditions",
            "owner_name": "owner_name",
            "project_address": "project_address",
            "application_type": "application_type",
            "zoning_type": "zoning_type",
            "short_scope": "short_scope",
        }
        for key, attr in field_map.items():
            if key in data and data[key] is not None:
                setattr(session, attr, data[key])
