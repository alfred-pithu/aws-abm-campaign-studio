"""SQLite campaign persistence."""

import sqlite3
from datetime import datetime, timezone

from src.config import get_settings
from src.graph.state import WorkflowState
from src.models.campaign import WorkflowStatus


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
          campaign_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          version INTEGER NOT NULL,
          state_json TEXT NOT NULL,
          approved_by TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          published_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def save_campaign(state: WorkflowState) -> None:
    now = datetime.now(timezone.utc).isoformat()
    created = state.created_at.isoformat()
    published = state.published_at.isoformat() if state.published_at else None
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO campaigns (
              campaign_id, status, version, state_json, approved_by,
              created_at, updated_at, published_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id) DO UPDATE SET
              status=excluded.status,
              version=excluded.version,
              state_json=excluded.state_json,
              approved_by=excluded.approved_by,
              updated_at=excluded.updated_at,
              published_at=excluded.published_at
            """,
            (
                state.campaign_brief.campaign_id,
                state.workflow_status.value
                if isinstance(state.workflow_status, WorkflowStatus)
                else state.workflow_status,
                state.version,
                state.model_dump_json(),
                state.approved_by,
                created,
                now,
                published,
            ),
        )
        conn.commit()


def load_campaign(campaign_id: str) -> WorkflowState | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT state_json FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
    if row is None:
        return None
    return WorkflowState.model_validate_json(row[0])
