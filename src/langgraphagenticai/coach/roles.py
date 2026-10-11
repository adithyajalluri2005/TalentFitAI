"""Role tracks: curated skill profiles a candidate can target instead of a JD.

A fixed profile makes diagnoses comparable: the same role always scores the
same skills at the same required levels, so readiness can be tracked over
time and across candidates. These are fresher-level profiles written from
common public role descriptions, not official hiring criteria.
"""
import json
import sqlite3
from typing import List, Optional

from pydantic import BaseModel

from src.langgraphagenticai.coach.state import RoleSkill


class RoleProfile(BaseModel):
    slug: str
    title: str
    description: str
    skills: List[RoleSkill]


def _s(skill: str, level: int, weight: float) -> RoleSkill:
    return RoleSkill(skill=skill, required_level=level, jd_weight=weight)


SEED_ROLES: List[RoleProfile] = [
    RoleProfile(
        slug="java-full-stack",
        title="Java Full Stack Developer",
        description="Builds web applications end to end with Java/Spring Boot services and a JavaScript front end.",
        skills=[
            _s("Java", 4, 1.0), _s("Spring Boot", 3, 0.9), _s("SQL", 3, 0.8),
            _s("REST API Design", 3, 0.8), _s("JavaScript", 3, 0.7), _s("React", 2, 0.6),
            _s("Git", 2, 0.5), _s("Data Structures & Algorithms", 3, 0.7),
        ],
    ),
    RoleProfile(
        slug="python-backend",
        title="Python Backend Developer",
        description="Designs and ships APIs and services in Python, backed by relational databases.",
        skills=[
            _s("Python", 4, 1.0), _s("Django or FastAPI/Flask", 3, 0.9), _s("SQL", 3, 0.8),
            _s("REST API Design", 3, 0.8), _s("Testing (pytest)", 2, 0.5), _s("Docker", 2, 0.5),
            _s("Git", 2, 0.5), _s("Data Structures & Algorithms", 3, 0.7),
        ],
    ),
    RoleProfile(
        slug="data-engineer",
        title="Data Engineer",
        description="Builds pipelines that move, clean and model data for analytics.",
        skills=[
            _s("SQL", 4, 1.0), _s("Python", 3, 0.9), _s("Data Modeling", 3, 0.8),
            _s("ETL / ELT Pipelines", 3, 0.8), _s("Apache Spark", 2, 0.7), _s("Cloud Data Services", 2, 0.6),
            _s("Pandas", 3, 0.6), _s("Git", 2, 0.4),
        ],
    ),
    RoleProfile(
        slug="ai-ml-engineer",
        title="AI/ML Engineer",
        description="Trains, evaluates and deploys machine learning and GenAI models.",
        skills=[
            _s("Python", 4, 1.0), _s("Machine Learning Fundamentals", 3, 1.0), _s("Deep Learning (PyTorch/TensorFlow)", 3, 0.8),
            _s("LLMs & Prompt Engineering", 3, 0.8), _s("Statistics & Probability", 3, 0.7), _s("Pandas & NumPy", 3, 0.6),
            _s("Model Deployment (APIs)", 2, 0.6), _s("SQL", 2, 0.4),
        ],
    ),
    RoleProfile(
        slug="cloud-devops",
        title="Cloud & DevOps Engineer",
        description="Automates build, deployment and operation of applications on cloud infrastructure.",
        skills=[
            _s("Linux", 3, 0.9), _s("Cloud Platform (AWS/Azure/GCP)", 3, 1.0), _s("Docker", 3, 0.9),
            _s("CI/CD", 3, 0.8), _s("Kubernetes", 2, 0.7), _s("Scripting (Bash/Python)", 3, 0.7),
            _s("Networking Basics", 2, 0.6), _s("Infrastructure as Code (Terraform)", 2, 0.5),
        ],
    ),
]


class RoleStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS role_profiles (
                    slug TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    skills TEXT NOT NULL
                )
            """)
            if not conn.execute("SELECT 1 FROM role_profiles LIMIT 1").fetchone():
                conn.executemany(
                    "INSERT INTO role_profiles (slug, title, description, skills) VALUES (?, ?, ?, ?)",
                    [(r.slug, r.title, r.description, json.dumps([s.model_dump() for s in r.skills]))
                     for r in SEED_ROLES],
                )

    @staticmethod
    def _row(r) -> RoleProfile:
        return RoleProfile(slug=r[0], title=r[1], description=r[2],
                           skills=[RoleSkill(**s) for s in json.loads(r[3])])

    def list(self) -> List[RoleProfile]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT slug, title, description, skills FROM role_profiles ORDER BY title").fetchall()
        return [self._row(r) for r in rows]

    def get(self, slug: str) -> Optional[RoleProfile]:
        with sqlite3.connect(self.db_path) as conn:
            r = conn.execute("SELECT slug, title, description, skills FROM role_profiles WHERE slug = ?", (slug,)).fetchone()
        return self._row(r) if r else None
