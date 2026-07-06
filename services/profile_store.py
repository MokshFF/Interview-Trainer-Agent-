from __future__ import annotations

import json
from pathlib import Path


class ProfileStore:
    def __init__(self, instance_dir: Path) -> None:
        self.instance_dir = instance_dir
        self.instance_dir.mkdir(parents=True, exist_ok=True)
        self.profile_file = self.instance_dir / "candidate_profile.json"
        self.dashboard_file = self.instance_dir / "dashboard.json"

    def save_profile(self, profile: dict) -> dict:
        normalized = {
            "candidate_name": profile.get("candidate_name", "Candidate"),
            "target_role": profile.get("target_role", "Software Engineer"),
            "experience_level": profile.get("experience_level", "Mid-level"),
            "skills": profile.get("skills", []),
            "target_company": profile.get("target_company", "Target Company"),
            "resume_text": profile.get("resume_text", ""),
            "strengths": profile.get("strengths", []),
            "gaps": profile.get("gaps", []),
            "summary": profile.get("summary", ""),
        }
        with self.profile_file.open("w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2)
        self._update_dashboard(normalized)
        return normalized

    def load_profile(self) -> dict:
        if not self.profile_file.exists():
            return {
                "candidate_name": "Candidate",
                "target_role": "Software Engineer",
                "experience_level": "Mid-level",
                "skills": [],
                "target_company": "Target Company",
                "resume_text": "",
                "strengths": [],
                "gaps": [],
                "summary": "",
            }
        with self.profile_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def load_dashboard(self) -> dict:
        if self.dashboard_file.exists():
            with self.dashboard_file.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        return self._default_dashboard()

    def _update_dashboard(self, profile: dict) -> None:
        dashboard = self._default_dashboard()
        dashboard["candidate_name"] = profile.get("candidate_name", "Candidate")
        dashboard["target_role"] = profile.get("target_role", "Software Engineer")
        dashboard["target_company"] = profile.get("target_company", "Target Company")
        dashboard["strengths"] = profile.get("strengths", [])
        dashboard["weaknesses"] = profile.get("gaps", [])
        dashboard["recommended_topics"] = ["system design", "problem solving", "coding practice", "behavioral examples"]
        with self.dashboard_file.open("w", encoding="utf-8") as handle:
            json.dump(dashboard, handle, indent=2)

    def _default_dashboard(self) -> dict:
        return {
            "candidate_name": "Candidate",
            "target_role": "Software Engineer",
            "target_company": "Target Company",
            "overall_score": 68,
            "section_scores": {
                "technical": 70,
                "behavioral": 66,
                "hr": 72,
                "coding": 64,
            },
            "progress": 55,
            "strengths": ["Communication", "Problem solving"],
            "weaknesses": ["System design depth", "Coding speed"],
            "recommended_topics": ["Data structures", "Behavioral STAR stories", "API design", "Interview practice"],
            "interview_progress": [
                {"label": "Profile Setup", "value": 100},
                {"label": "Resume Review", "value": 85},
                {"label": "Mock Interview", "value": 60},
                {"label": "Readiness", "value": 55},
            ],
            "analytics": {
                "responses": 12,
                "improvement": 18,
                "time_spent_minutes": 45,
            },
        }
