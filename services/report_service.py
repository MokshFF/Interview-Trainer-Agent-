from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


class ReportService:
    def __init__(self, instance_dir: Path) -> None:
        self.instance_dir = instance_dir
        self.instance_dir.mkdir(parents=True, exist_ok=True)

    def build_report(self, profile: dict, dashboard: dict) -> dict:
        return {
            "candidate": profile.get("candidate_name", "Candidate"),
            "target_role": profile.get("target_role", "Software Engineer"),
            "target_company": profile.get("target_company", "Target Company"),
            "overall_score": dashboard.get("overall_score", 68),
            "section_scores": dashboard.get("section_scores", {}),
            "strengths": dashboard.get("strengths", []),
            "weaknesses": dashboard.get("weaknesses", []),
            "recommended_topics": dashboard.get("recommended_topics", []),
            "summary": "Downloadable readiness report generated successfully.",
        }

    def export_pdf(self, profile: dict, dashboard: dict) -> Path:
        report_path = self.instance_dir / "interview_readiness_report.pdf"
        pdf = canvas.Canvas(str(report_path), pagesize=letter)
        width, height = letter
        y = height - 50

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, y, "Interview Readiness Report")
        y -= 30

        pdf.setFont("Helvetica", 11)
        lines = [
            f"Candidate: {profile.get('candidate_name', 'Candidate')}",
            f"Target Role: {profile.get('target_role', 'Software Engineer')}",
            f"Target Company: {profile.get('target_company', 'Target Company')}",
            f"Overall Score: {dashboard.get('overall_score', 68)}",
            f"Strengths: {', '.join(dashboard.get('strengths', []))}",
            f"Weaknesses: {', '.join(dashboard.get('weaknesses', []))}",
            f"Recommended Topics: {', '.join(dashboard.get('recommended_topics', []))}",
        ]
        for line in lines:
            pdf.drawString(50, y, line)
            y -= 18
            if y < 80:
                pdf.showPage()
                y = height - 50
        pdf.save()
        return report_path
