"""Progress history across coaching sessions, for the readiness-over-time chart.

The LangGraph checkpointer holds the live session; this table is the durable,
queryable record of every re-score a candidate has had.
"""
import json
import sqlite3
from typing import List

from src.langgraphagenticai.coach.state import ReadinessSnapshot


class ProgressStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS coach_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    target_role TEXT,
                    cycle INTEGER NOT NULL,
                    readiness REAL NOT NULL,
                    per_skill TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_coach_progress_candidate ON coach_progress(candidate_id)"
            )

    def record(self, candidate_id: str, thread_id: str, target_role: str, snap: ReadinessSnapshot) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO coach_progress (candidate_id, thread_id, target_role, cycle, readiness, per_skill, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (candidate_id, thread_id, target_role, snap.cycle, snap.readiness,
                 json.dumps(snap.per_skill), snap.at),
            )

    def history(self, candidate_id: str) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT thread_id, target_role, cycle, readiness, per_skill, created_at"
                " FROM coach_progress WHERE candidate_id = ? ORDER BY created_at, id",
                (candidate_id,),
            ).fetchall()
        return [{**dict(r), "per_skill": json.loads(r["per_skill"])} for r in rows]


class TopicStore:
    """Which study topics a candidate has ticked as done. Kept outside the
    graph state: ticking is frequent, needs no LLM, and must not disturb a
    pending quiz or interview question. Keyed by cycle because each cycle
    brings a new plan."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS topic_progress (
                    thread_id TEXT NOT NULL,
                    cycle INTEGER NOT NULL,
                    skill TEXT NOT NULL,
                    topic_index INTEGER NOT NULL,
                    PRIMARY KEY (thread_id, cycle, skill, topic_index)
                )
            """)

    def set(self, thread_id: str, cycle: int, skill: str, topic_index: int, done: bool) -> None:
        with sqlite3.connect(self.db_path) as conn:
            if done:
                conn.execute("INSERT OR IGNORE INTO topic_progress VALUES (?, ?, ?, ?)",
                             (thread_id, cycle, skill, topic_index))
            else:
                conn.execute("DELETE FROM topic_progress WHERE thread_id = ? AND cycle = ? AND skill = ? AND topic_index = ?",
                             (thread_id, cycle, skill, topic_index))

    def done(self, thread_id: str, cycle: int) -> dict:
        """skill -> sorted list of ticked topic indexes."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT skill, topic_index FROM topic_progress WHERE thread_id = ? AND cycle = ?",
                                (thread_id, cycle)).fetchall()
        out: dict = {}
        for skill, idx in rows:
            out.setdefault(skill, []).append(idx)
        return {k: sorted(v) for k, v in out.items()}
