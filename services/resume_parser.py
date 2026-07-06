from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyPDF2 import PdfReader


@dataclass
class ParsedResume:
    text: str
    skills: list[str]
    strengths: list[str]
    gaps: list[str]


class ResumeParser:
    skill_keywords = [
        "python",
        "flask",
        "javascript",
        "sql",
        "docker",
        "kubernetes",
        "aws",
        "azure",
        "ibm cloud",
        "watsonx",
        "react",
        "apis",
        "machine learning",
        "system design",
        "ibm orchestrate",
        "watson orchestrate",
    ]

    def parse(self, uploaded_file: Any) -> dict:
        suffix = Path(uploaded_file.filename or "resume.pdf").suffix.lower()
        text = ""

        if suffix == ".pdf":
            reader = PdfReader(uploaded_file)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            raw = uploaded_file.read()
            text = raw.decode("utf-8", errors="ignore")

        normalized = re.sub(r"\s+", " ", text).strip()
        lowered = normalized.lower()
        skills = [skill for skill in self.skill_keywords if skill in lowered]
        strengths = self._infer_strengths(normalized, skills)
        gaps = self._infer_gaps(skills)

        return {
            "resume_text": normalized[:20000],
            "skills": skills,
            "strengths": strengths,
            "gaps": gaps,
            "summary": self._summary(normalized),
        }

    def _summary(self, text: str) -> str:
        if not text:
            return "No resume content detected."
        return text[:500] + ("..." if len(text) > 500 else "")

    def _infer_strengths(self, text: str, skills: list[str]) -> list[str]:
        strengths: list[str] = []
        if any(keyword in text.lower() for keyword in ["lead", "led", "ownership"]):
            strengths.append("Leadership and ownership")
        if any(keyword in text.lower() for keyword in ["built", "designed", "implemented"]):
            strengths.append("Execution and delivery")
        if skills:
            strengths.append("Relevant technical skills detected")
        return strengths or ["Resume parsed successfully"]

    def _infer_gaps(self, skills: list[str]) -> list[str]:
        desired = ["system design", "sql", "testing", "deployment"]
        missing = [item for item in desired if item not in skills]
        return missing[:4]
