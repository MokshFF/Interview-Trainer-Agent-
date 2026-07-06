from __future__ import annotations


class ScoreService:
    def score_response(self, answer: str, expected_signals: list[str] | None = None) -> dict:
        expected_signals = expected_signals or []
        answer_lower = answer.lower()

        coverage = sum(signal.lower() in answer_lower for signal in expected_signals)
        clarity = min(100, 55 + len(answer.split()) * 2)
        structure = 70 if any(token in answer_lower for token in ["first", "then", "finally", "situation", "action", "result"]) else 55
        confidence = 65 if len(answer) > 80 else 45
        technical = 60 + coverage * 8

        overall = round((clarity + structure + confidence + technical) / 4)
        strengths = ["Clear response structure"] if structure >= 70 else ["Concise communication"]
        if coverage:
            strengths.append("Aligned to the expected concept")
        weaknesses = []
        if len(answer.split()) < 40:
            weaknesses.append("Answer may be too brief")
        if coverage == 0:
            weaknesses.append("Include more role-specific details")

        return {
            "overall_score": max(0, min(100, overall)),
            "section_scores": {
                "clarity": clarity,
                "structure": structure,
                "confidence": confidence,
                "technical_depth": technical,
            },
            "strengths": strengths,
            "weaknesses": weaknesses or ["Keep refining examples and measurable outcomes"],
        }
