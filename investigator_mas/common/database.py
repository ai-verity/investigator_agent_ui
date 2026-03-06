"""
database.py  v5
===============
Pure data-access layer.

Schema additions in v5
──────────────────────
applications  (replaces the legacy permit-centric table for new workflows)
  application_id   TEXT  UUID PRIMARY KEY
  date             TEXT  ISO-8601 creation timestamp
  application_type TEXT
  owner_name       TEXT
  project_address  TEXT
  sow_question_answer  TEXT  JSON → {"context": str, "questions": [{"question": str, "answer": str}]}
  sow_text         TEXT
  status           TEXT  pending | approved | rejected

ai  (AI agent execution log)
  uuid             TEXT  UUID PRIMARY KEY
  date             TEXT  ISO-8601
  agent_name       TEXT
  task_name        TEXT
  reasoning_text   TEXT
  status           TEXT
  ai_compliance_summary  TEXT  JSON → {"agent_name": str, "findings": str,
                                        "severity": str, "description": str}

Legacy tables (v4) are retained for backward compatibility.
"""

import hashlib
import json
import sqlite3
import uuid as _uuid_mod
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "permits.db"

# ── Status enumerations ────────────────────────────────────────────────────────

VALID_WORKFLOW_STATUSES = ("Submitted", "Pending", "Approved", "Rejected")
VALID_APPLICATION_STATUSES = ("pending", "approved", "rejected", "ai_rejected")


# ── Connection ─────────────────────────────────────────────────────────────────


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# def _new_uuid() -> str:
#     return str(_uuid_mod.uuid4())


# def _generate_permit_id(conn: sqlite3.Connection) -> str:
#     """ATX-YYYY-NNNNNN — used by legacy insert path."""
#     year = datetime.now(timezone.utc).year
#     row = conn.execute("SELECT MAX(rowid) FROM legacy_applications").fetchone()
#     next_n = (row[0] or 0) + 1
#     return f"ATX-{year}-{next_n:06d}"


# ══════════════════════════════════════════════════════════════════════════════
# Schema init
# ══════════════════════════════════════════════════════════════════════════════


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
            -- ── Legacy tables (v4) ──────────────────────────────────────────

            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS legacy_applications (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                permit_id      TEXT    UNIQUE NOT NULL DEFAULT '',
                owner          TEXT    NOT NULL DEFAULT '',
                address        TEXT    NOT NULL DEFAULT '',
                blueprint_name TEXT    NOT NULL DEFAULT '',
                blueprint_data BLOB,
                blueprint_mime TEXT    NOT NULL DEFAULT 'application/pdf',
                scope_of_work  TEXT    NOT NULL DEFAULT '',
                created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS application_status (
                app_id           INTEGER PRIMARY KEY,
                workflow_status  TEXT    NOT NULL DEFAULT 'Submitted',
                stage            TEXT    NOT NULL DEFAULT 'Submitted',
                status_message   TEXT    NOT NULL DEFAULT 'Application received.',
                compliance_score INTEGER NOT NULL DEFAULT 100,
                updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (app_id) REFERENCES legacy_applications(id)
            );

            CREATE TABLE IF NOT EXISTS review_findings (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id   INTEGER NOT NULL,
                agent    TEXT    NOT NULL,
                finding  TEXT    NOT NULL,
                severity TEXT    NOT NULL,
                detail   TEXT    NOT NULL,
                FOREIGN KEY (app_id) REFERENCES legacy_applications(id)
            );

            CREATE TABLE IF NOT EXISTS blueprint_analysis (
                app_id        INTEGER PRIMARY KEY,
                raw_response  TEXT NOT NULL,
                findings_json TEXT NOT NULL DEFAULT '[]',
                analysed_at   TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (app_id) REFERENCES legacy_applications(id)
            );

            -- ── v5 tables ────────────────────────────────────────────────────

            CREATE TABLE IF NOT EXISTS applications (
                application_id      TEXT PRIMARY KEY,
                date                TEXT NOT NULL,
                application_type    TEXT NOT NULL DEFAULT '',
                owner_name          TEXT NOT NULL DEFAULT '',
                zoning_type         TEXT NOT NULL DEFAULT '',
                project_address     TEXT NOT NULL DEFAULT '',
                sow_question_answer TEXT NOT NULL DEFAULT '{"context":"","questions":[]}',
                sow_text            TEXT NOT NULL DEFAULT '',
                status              TEXT NOT NULL DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS ai (
                uuid                  TEXT PRIMARY KEY,
                date                  TEXT NOT NULL,
                agent_name            TEXT NOT NULL DEFAULT '',
                task_name             TEXT NOT NULL DEFAULT '',
                reasoning_text        TEXT NOT NULL DEFAULT '',
                status                TEXT NOT NULL DEFAULT '',
                ai_compliance_summary TEXT NOT NULL DEFAULT '{}'
            );
        """)

        # _migrate(conn)

        # Seed default users
        conn.execute(
            "INSERT OR IGNORE INTO users VALUES ('user1', ?, 'public')",
            (hashlib.sha256(b"pass123").hexdigest(),),
        )
        conn.execute(
            "INSERT OR IGNORE INTO users VALUES ('admin', ?, 'inspector')",
            (hashlib.sha256(b"admin123").hexdigest(),),
        )


def _migrate(conn: sqlite3.Connection) -> None:
    """Non-destructive column additions for databases upgrading from v4."""
    # legacy_applications may have been called 'applications' in v4
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "applications" in tables and "legacy_applications" not in tables:
        conn.execute("ALTER TABLE applications RENAME TO legacy_applications")

    legacy_cols = {r[1] for r in conn.execute("PRAGMA table_info(legacy_applications)")}
    for col, sql in {
        "permit_id": "ALTER TABLE legacy_applications ADD COLUMN permit_id TEXT DEFAULT ''",
        "blueprint_data": "ALTER TABLE legacy_applications ADD COLUMN blueprint_data BLOB",
        "blueprint_mime": "ALTER TABLE legacy_applications ADD COLUMN blueprint_mime TEXT DEFAULT 'application/pdf'",
        "created_at": "ALTER TABLE legacy_applications ADD COLUMN created_at TEXT DEFAULT (datetime('now'))",
    }.items():
        if col not in legacy_cols:
            conn.execute(sql)

    st_cols = {r[1] for r in conn.execute("PRAGMA table_info(application_status)")}
    for col, sql in {
        "workflow_status": "ALTER TABLE application_status ADD COLUMN workflow_status TEXT DEFAULT 'Submitted'",
        "updated_at": "ALTER TABLE application_status ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))",
    }.items():
        if col not in st_cols:
            conn.execute(sql)


# ══════════════════════════════════════════════════════════════════════════════
# ── Users ─────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════


def get_user(username: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


# ══════════════════════════════════════════════════════════════════════════════
# ── Table: applications (v5) ──────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

# SOW Q&A helper
# Expected structure: {"context": str, "questions": [{"question": str, "answer": str}]}


def _validate_application_status(status: str) -> None:
    if status not in VALID_APPLICATION_STATUSES:
        raise ValueError(
            f"Invalid application status '{status}'. "
            f"Must be one of {VALID_APPLICATION_STATUSES}."
        )


def _validate_sow_qa(sow_qa: dict) -> None:
    """Light structural validation for sow_question_answer payload."""
    if "context" not in sow_qa:
        raise ValueError("sow_question_answer must contain a 'context' key.")
    if "questions" not in sow_qa or not isinstance(sow_qa["questions"], list):
        raise ValueError("sow_question_answer must contain a 'questions' list.")
    for i, q in enumerate(sow_qa["questions"]):
        if "question" not in q or "answer" not in q:
            raise ValueError(
                f"questions[{i}] must have both 'question' and 'answer' keys."
            )

def update_application_sow_state(application_id: str, sow_question_answer: str, sow_text: str, status: str):
    with get_db() as conn:
        conn.execute(
            """UPDATE applications 
            SET sow_question_answer = ?, sow_text = ?, status = ?
            WHERE application_id = ?""",
            (sow_question_answer, sow_text, status, application_id),
        )
    return True

# CREATE
def create_application(
    application_id: str,
    application_type: str,
    owner_name: str,
    project_address: str,
    zoning_type: str,
    sow_text: str | None = None,
    sow_question_answer: dict | None = None,
    status: str = "pending",
) -> str:
    """
    Insert a new application row.
    Returns the application_id (UUID string).

    sow_question_answer should match:
        {"context": str, "questions": [{"question": str, "answer": str}]}
    """
    # _validate_application_status(status)
    sow_qa = sow_question_answer or {"context": "", "questions": []}
    _sow_text = sow_text or ""
    # _validate_sow_qa(sow_qa)
    # app_id = application_id
    now = _now_iso()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO applications
                (application_id, date, application_type, owner_name,
                 project_address, zoning_type, sow_question_answer, sow_text, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?,?)
            """,
            (
                application_id,
                now,
                application_type,
                owner_name,
                project_address,
                zoning_type,
                json.dumps(sow_qa),
                _sow_text,
                "pending",
            ),
        )
    return application_id


# READ — single
def get_application(application_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE application_id = ?",
            (application_id,),
        ).fetchone()
    if not row:
        return None
    return _application_row_to_dict(row)


# READ — all
def get_all_applications_v5(
    status: str | None = None,
    owner_name: str | None = None,
) -> list[dict]:
    """
    Returns all applications, optionally filtered by status and/or owner_name.
    """
    query = "SELECT * FROM applications WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if owner_name:
        query += " AND owner_name = ?"
        params.append(owner_name)
    query += " ORDER BY date DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_application_row_to_dict(r) for r in rows]


# UPDATE — full
def update_application(
    application_id: str,
    application_type: str | None = None,
    owner_name: str | None = None,
    project_address: str | None = None,
    sow_text: str | None = None,
    sow_question_answer: dict | None = None,
    status: str | None = None,
) -> bool:
    """
    Partial update — only supplied (non-None) fields are changed.
    Returns True if a row was updated, False if application_id not found.
    """
    if status is not None:
        _validate_application_status(status)
    if sow_question_answer is not None:
        _validate_sow_qa(sow_question_answer)

    sets, params = [], []
    if application_type is not None:
        sets.append("application_type = ?")
        params.append(application_type)
    if owner_name is not None:
        sets.append("owner_name = ?")
        params.append(owner_name)
    if project_address is not None:
        sets.append("project_address = ?")
        params.append(project_address)
    if sow_text is not None:
        sets.append("sow_text = ?")
        params.append(sow_text)
    if sow_question_answer is not None:
        sets.append("sow_question_answer = ?")
        params.append(json.dumps(sow_question_answer))
    if status is not None:
        sets.append("status = ?")
        params.append(status)

    if not sets:
        return False  # nothing to update

    params.append(application_id)
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE applications SET {', '.join(sets)} WHERE application_id = ?",
            params,
        )
    return cur.rowcount > 0


# UPDATE — status only (convenience setter)
def set_application_status(application_id: str, status: str) -> bool:
    """Set only the status field. Returns True if found and updated."""
    _validate_application_status(status)
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE applications SET status = ? WHERE application_id = ?",
            (status, application_id),
        )
    return cur.rowcount > 0


# UPDATE — SOW Q&A only (convenience setter)
def set_sow_question_answer(application_id: str, sow_qa: dict) -> bool:
    """Replace the sow_question_answer JSON for an application."""
    _validate_sow_qa(sow_qa)
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE applications SET sow_question_answer = ? WHERE application_id = ?",
            (json.dumps(sow_qa), application_id),
        )
    return cur.rowcount > 0


# DELETE
def delete_application(application_id: str) -> bool:
    """Hard-delete an application. Returns True if a row was removed."""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM applications WHERE application_id = ?",
            (application_id,),
        )
    return cur.rowcount > 0


# Row → dict deserialiser
def _application_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["sow_question_answer"] = json.loads(d["sow_question_answer"])
    except (json.JSONDecodeError, TypeError):
        d["sow_question_answer"] = {"context": "", "questions": []}
    return d


# ══════════════════════════════════════════════════════════════════════════════
# ── Table: ai ─────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

# ai_compliance_summary structure:
#   {"agent_name": str, "findings": str, "severity": str, "description": str}


def _validate_compliance_summary(summary: dict) -> None:
    required = {"agent_name", "findings", "severity", "description"}
    missing = required - summary.keys()
    if missing:
        raise ValueError(f"ai_compliance_summary is missing required keys: {missing}")


# CREATE
def create_ai_record(
    agent_name: str,
    task_name: str,
    reasoning_text: str,
    status: str,
    ai_compliance_summary: dict,
    record_uuid: str | None = None,
) -> str:
    """
    Insert a new AI agent execution record.
    Returns the uuid string.

    ai_compliance_summary must contain:
        {"agent_name": str, "findings": str, "severity": str, "description": str}
    """
    _validate_compliance_summary(ai_compliance_summary)
    rec_uuid = record_uuid or _new_uuid()
    now = _now_iso()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO ai
                (uuid, date, agent_name, task_name,
                 reasoning_text, status, ai_compliance_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec_uuid,
                now,
                agent_name,
                task_name,
                reasoning_text,
                status,
                json.dumps(ai_compliance_summary),
            ),
        )
    return rec_uuid


# READ — single
def get_ai_record(record_uuid: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM ai WHERE uuid = ?", (record_uuid,)).fetchone()
    if not row:
        return None
    return _ai_row_to_dict(row)


# READ — all records for an agent
def get_ai_records_by_agent(agent_name: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM ai WHERE agent_name = ? ORDER BY date DESC",
            (agent_name,),
        ).fetchall()
    return [_ai_row_to_dict(r) for r in rows]


# READ — all records for a task
def get_ai_records_by_task(task_name: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM ai WHERE task_name = ? ORDER BY date DESC",
            (task_name,),
        ).fetchall()
    return [_ai_row_to_dict(r) for r in rows]


# READ — all
def get_all_ai_records(status: str | None = None) -> list[dict]:
    query = "SELECT * FROM ai WHERE 1=1"
    params: list = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY date DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_ai_row_to_dict(r) for r in rows]


# UPDATE — full partial
def update_ai_record(
    record_uuid: str,
    agent_name: str | None = None,
    task_name: str | None = None,
    reasoning_text: str | None = None,
    status: str | None = None,
    ai_compliance_summary: dict | None = None,
) -> bool:
    """
    Partial update. Returns True if a row was updated.
    """
    if ai_compliance_summary is not None:
        _validate_compliance_summary(ai_compliance_summary)

    sets, params = [], []
    if agent_name is not None:
        sets.append("agent_name = ?")
        params.append(agent_name)
    if task_name is not None:
        sets.append("task_name = ?")
        params.append(task_name)
    if reasoning_text is not None:
        sets.append("reasoning_text = ?")
        params.append(reasoning_text)
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if ai_compliance_summary is not None:
        sets.append("ai_compliance_summary = ?")
        params.append(json.dumps(ai_compliance_summary))

    if not sets:
        return False

    params.append(record_uuid)
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE ai SET {', '.join(sets)} WHERE uuid = ?",
            params,
        )
    return cur.rowcount > 0


# UPDATE — status setter
def set_ai_status(record_uuid: str, status: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE ai SET status = ? WHERE uuid = ?",
            (status, record_uuid),
        )
    return cur.rowcount > 0


# UPDATE — compliance summary setter
def set_ai_compliance_summary(record_uuid: str, summary: dict) -> bool:
    _validate_compliance_summary(summary)
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE ai SET ai_compliance_summary = ? WHERE uuid = ?",
            (json.dumps(summary), record_uuid),
        )
    return cur.rowcount > 0


# DELETE
def delete_ai_record(record_uuid: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM ai WHERE uuid = ?", (record_uuid,))
    return cur.rowcount > 0


# Row → dict deserialiser
def _ai_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["ai_compliance_summary"] = json.loads(d["ai_compliance_summary"])
    except (json.JSONDecodeError, TypeError):
        d["ai_compliance_summary"] = {}
    return d


# ══════════════════════════════════════════════════════════════════════════════
# ── Legacy v4 helpers (unchanged, kept for backward compatibility) ─────────────
# ══════════════════════════════════════════════════════════════════════════════


def insert_application(
    owner: str,
    address: str,
    blueprint_name: str,
    scope_of_work: str,
    blueprint_data: bytes | None = None,
    blueprint_mime: str = "application/pdf",
) -> tuple[int, str]:
    """Legacy insert → legacy_applications. Returns (app_id, permit_id)."""
    with get_db() as conn:
        year = datetime.now(timezone.utc).year
        row = conn.execute("SELECT MAX(id) FROM legacy_applications").fetchone()
        next_n = (row[0] or 0) + 1
        permit_id = f"ATX-{year}-{next_n:06d}"

        cur = conn.execute(
            "INSERT INTO legacy_applications "
            "(permit_id, owner, address, blueprint_name, blueprint_data, blueprint_mime, scope_of_work) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                permit_id,
                owner,
                address,
                blueprint_name,
                blueprint_data,
                blueprint_mime,
                scope_of_work,
            ),
        )
        app_id = cur.lastrowid
        conn.execute(
            "INSERT INTO application_status (app_id, workflow_status) VALUES (?, 'Submitted')",
            (app_id,),
        )
        return app_id, permit_id


def get_latest_application(owner: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            """
            SELECT a.id, a.permit_id, a.owner, a.address, a.created_at,
                   s.workflow_status, s.stage, s.status_message, s.compliance_score,
                   s.updated_at
              FROM legacy_applications a
              JOIN application_status s ON a.id = s.app_id
             WHERE a.owner = ?
          ORDER BY a.id DESC LIMIT 1
            """,
            (owner,),
        ).fetchone()


def get_application_by_id(app_id: int) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            """
            SELECT *
              FROM applications
             WHERE application_id   = ?
            """,
            (app_id,),
        ).fetchone()


# def get_all_applications() -> list[sqlite3.Row]:
#     with get_db() as conn:
#         return conn.execute(
#             """
#             SELECT * FROM applications
#             """
#         ).fetchall()
def get_all_applications():
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT 
                a.application_id,
                a.date,
                a.application_type,
                a.owner_name,
                a.zoning_type,
                a.project_address,
                a.sow_text,
                a.status,
                COALESCE(s.workflow_status, 'Submitted')      AS workflow_status,
                COALESCE(s.stage, 'Submitted')                AS stage,
                COALESCE(s.status_message, 'Application received.') AS status_message,
                COALESCE(s.compliance_score, 100)             AS compliance_score
            FROM applications a
            LEFT JOIN application_status s ON s.app_id = a.application_id
            ORDER BY a.date DESC
            """
        ).fetchall()

def get_blueprint_bytes(app_id: int) -> tuple[bytes | None, str]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT blueprint_data, blueprint_mime FROM legacy_applications WHERE id = ?",
            (app_id,),
        ).fetchone()
        if not row or row["blueprint_data"] is None:
            return None, "application/pdf"
        return bytes(row["blueprint_data"]), row["blueprint_mime"]


def set_workflow_status(
    app_id: int,
    workflow_status: str,
    stage: str = "",
    status_message: str = "",
    compliance_score: int | None = None,
) -> None:
    if workflow_status not in VALID_WORKFLOW_STATUSES:
        raise ValueError(
            f"Invalid workflow_status '{workflow_status}'. "
            f"Must be one of {VALID_WORKFLOW_STATUSES}."
        )
    with get_db() as conn:
        row = conn.execute(
            "SELECT compliance_score FROM application_status WHERE app_id=?", (app_id,)
        ).fetchone()
        score = (
            compliance_score
            if compliance_score is not None
            else (row["compliance_score"] if row else 100)
        )
        conn.execute(
            """
            UPDATE application_status
               SET workflow_status  = ?,
                   stage            = CASE WHEN ? != '' THEN ? ELSE stage END,
                   status_message   = CASE WHEN ? != '' THEN ? ELSE status_message END,
                   compliance_score = ?,
                   updated_at       = datetime('now')
             WHERE app_id = ?
            """,
            (
                workflow_status,
                stage,
                stage,
                status_message,
                status_message,
                score,
                app_id,
            ),
        )


def upsert_application_status(
    app_id: int, stage: str, status_message: str, compliance_score: int
) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE application_status "
            "SET stage=?, status_message=?, compliance_score=?, updated_at=datetime('now') "
            "WHERE app_id=?",
            (stage, status_message, compliance_score, app_id),
        )


def save_review_findings(app_id: int, findings: list[dict]) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM review_findings WHERE app_id=?", (app_id,))
        conn.executemany(
            "INSERT INTO review_findings (app_id, agent, finding, severity, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (app_id, f["agent"], f["finding"], f["severity"], f["detail"])
                for f in findings
            ],
        )


def get_review_findings(app_id: int) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT agent, finding, severity, detail FROM review_findings WHERE app_id=?",
            (app_id,),
        ).fetchall()


def save_blueprint_analysis(
    app_id: int, raw_response: str, findings: list[dict]
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO blueprint_analysis (app_id, raw_response, findings_json)
            VALUES (?, ?, ?)
            ON CONFLICT(app_id) DO UPDATE SET
                raw_response  = excluded.raw_response,
                findings_json = excluded.findings_json,
                analysed_at   = datetime('now')
            """,
            (app_id, raw_response, json.dumps(findings)),
        )


def get_blueprint_analysis(app_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT raw_response, findings_json, analysed_at FROM blueprint_analysis WHERE app_id=?",
            (app_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "raw_response": row["raw_response"],
            "findings": json.loads(row["findings_json"]),
            "analysed_at": row["analysed_at"],
        }
