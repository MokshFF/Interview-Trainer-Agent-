from __future__ import annotations

import re
from typing import Any

from services.agent_config import AGENT_SYSTEM_PROMPT


class InterviewEngine:
    def __init__(self, rag_service, score_service, agent_instructions: dict, orchestrate_client=None) -> None:
        self.rag_service = rag_service
        self.score_service = score_service
        self.agent_instructions = agent_instructions
        self.orchestrate_client = orchestrate_client

    def sample_questions(self, profile: dict) -> list[str]:
        base_query = " ".join([profile.get("target_role", ""), profile.get("target_company", ""), "interview"])
        documents = self.rag_service.retrieve(base_query, profile=profile, top_k=4)
        if documents:
            return [document.get("question", "") for document in documents]
        return [
            "Tell me about yourself.",
            "Walk me through a challenging project.",
            "How do you handle ambiguity?",
            "Describe a time you learned a new technology quickly.",
        ]

    def generate_response(self, payload: dict[str, Any]) -> dict:
        profile = payload.get("profile", {})
        message = payload.get("message", "")
        history = payload.get("history", [])
        documents = self.rag_service.retrieve(message, profile=profile, top_k=3)
        answer = self._generate_with_model_or_fallback(message, profile, documents, history)
        readiness = self.score_service.score_response(answer, [doc.get("answer", "") for doc in documents])

        return {
            "reply": answer,
            "sources": documents,
            "readiness": readiness,
            "history_count": len(history),
            "agent_instructions": self.agent_instructions,
        }

    def evaluate_answer(self, payload: dict[str, Any]) -> dict:
        answer = payload.get("answer", "")
        question = payload.get("question", "")
        context = self.rag_service.retrieve(question, profile=payload.get("profile", {}), top_k=3)
        expected_signals = [item.get("answer", "") for item in context]
        evaluation = self.score_service.score_response(answer, expected_signals)
        evaluation["model_answer"] = self._generate_model_answer(question, context)
        evaluation["feedback"] = self._feedback_from_score(evaluation)
        evaluation["recommendations"] = [
            "Add a concise situation-action-result structure",
            "Mention measurable outcomes",
            "Tie the response back to the target role",
        ]
        return evaluation

    def _generate_with_local_fallback(self, message: str, profile: dict, documents: list[dict], history: list[dict]) -> str:
        if not self._is_interview_related(message):
            return "I only answer interview-preparation questions. Tell me your target role, company, or interview type."

        role = self._extract_role(message, profile)
        company = self._extract_company(message, profile)
        topic = self._extract_topic(message, documents)
        experience = profile.get("experience_level", "your experience level")
        recent_user_messages = [item.get("content", "") for item in history[-6:] if item.get("role") == "user"]
        repeated_prompt = sum(1 for item in recent_user_messages if self._normalize_text(item) == self._normalize_text(message)) > 1

        if self._looks_like_greeting(message) or len(message.split()) <= 3:
            return self._pick_variant(
                [
                    f"Hi there! What role at {company} are you preparing for, and what is your experience level?",
                    f"Hello! Tell me the job role you want and your experience level, and I'll tailor the prep for {company}.",
                    f"Hi! What job are you targeting at {company}, and how many years of experience do you have?",
                ],
                message,
                history,
            )

        if any(word in message.lower() for word in ["question", "interview", "mock", "questions"]):
            if topic:
                return self._pick_variant(
                    [
                        f"For {company}, here is a {topic} interview question: Explain the core concept of {topic} and how you have used it in a project.",
                        f"Here is a technical {topic} question for {company}: What are the key trade-offs and performance bottlenecks when implementing {topic}?",
                        f"Let's practice a {topic} question for {company}: Walk me through a challenging problem you solved using {topic}.",
                    ],
                    message,
                    history,
                )
            return self._pick_variant(
                [
                    f"For a {role} interview at {company}, try this question: Tell me about a time you solved a difficult problem.",
                    f"Here’s a solid behavioral question for {role} at {company}: Describe a challenge you handled and the outcome.",
                    f"Let’s start with this for {role} at {company}: Tell me about a time you solved a difficult technical problem.",
                ],
                message,
                history,
            )

        if any(word in message.lower() for word in ["answer", "response", "feedback", "evaluate"]):
            return self._pick_variant(
                [
                    f"For a {role} at {company}, use a clear structure: situation, action, result, and one measurable outcome.",
                    f"A strong answer for {role} should be structured, concise, and end with a clear business impact metric.",
                    f"Keep your answer focused on situation, action, result, plus one clear impact metric.",
                ],
                message,
                history,
            )

        if repeated_prompt:
            return self._pick_variant(
                [
                    f"We’ve covered that already, so let’s move forward: for {role} at {company}, what is your biggest interview concern right now?",
                    f"Let’s shift to the next step for {role}: what part of the interview at {company} feels hardest to you?",
                    f"To keep this useful, tell me the interview area you want to improve first: technical, HR, behavioral, or coding.",
                ],
                message,
                history,
            )

        return self._pick_variant(
            [
                f"Understood. For {role} at {company}, I’ll keep this focused on interview prep for {experience}.",
                f"Got it. I’ll tailor the next steps for {role} at {company} based on {experience}.",
                f"Perfect. I’ll keep the coaching targeted to {role} at {company} and your experience level.",
            ],
            message,
            history,
        )

    def _generate_with_model_or_fallback(self, message: str, profile: dict, documents: list[dict], history: list[dict]) -> str:
        prompt = self._build_prompt(message, profile, documents)
        if self.orchestrate_client and self.orchestrate_client.configured:
            try:
                response = self.orchestrate_client.generate(
                    prompt,
                    context={
                        "profile": profile,
                        "documents": documents,
                    },
                )
                if response:
                    print(f"[IBM Watson Orchestrate] Generated response successfully using Agent: {self.orchestrate_client.agent_id}")
                    return self._postprocess_reply(response, message, profile, history)
            except Exception as e:
                print(f"[IBM Watson Orchestrate] Connection error: {e}")
        
        print("[Fallback] IBM Watson Orchestrate call failed or not configured. Using local fallback.")
        return self._generate_with_local_fallback(message, profile, documents, history)

    def _build_prompt(self, message: str, profile: dict, documents: list[dict]) -> str:
        context_block = "\n".join(
            [
                f"- Topic: {document.get('topic', '')}\n  Question: {document.get('question', '')}\n  Suggested Answer: {document.get('answer', '')}"
                for document in documents
            ]
        ) or "No matching knowledge base context found."

        return (
            f"{AGENT_SYSTEM_PROMPT}\n\n"
            f"AGENT INSTRUCTIONS: {self.agent_instructions}\n"
            f"Candidate profile: {profile}\n"
            f"Knowledge base context (Only use if directly relevant to the user query): \n{context_block}\n\n"
            f"User message: {message}\n\n"
            "You are a dynamic and friendly conversational AI interview coach (like ChatGPT). "
            "Your response must directly address the user's message. "
            "If the user asks for questions (e.g., 'give interview question on ai', 'questions for Amazon', or 'coding questions'), "
            "generate highly relevant and challenging questions dynamically based on their request. "
            "If they ask for coding questions or technical challenges, generate clear coding questions (e.g., algorithm, data structure, or programming problems) and explain the expected inputs, outputs, and time complexity. Use standard Markdown code blocks (```python ... ```) to format any code snippets. "
            "Only reference the knowledge base context if it is directly relevant to what the user asked. "
            "Respond in a natural, friendly, and well-structured manner. Keep your response within 3-4 concise sentences, and guide the user in preparing for their interview step-by-step."
        )

    def _postprocess_reply(self, reply: str, message: str, profile: dict, history: list[dict]) -> str:
        cleaned = str(reply).strip()
        if not cleaned:
            return self._generate_with_local_fallback(message, profile, [], history)
        if len(cleaned) > 1500:
            cleaned = cleaned[:1497].rsplit(" ", 1)[0] + "..."
        return cleaned

    def _pick_variant(self, variants: list[str], message: str, history: list[dict]) -> str:
        seed = sum(ord(ch) for ch in self._normalize_text(message))
        seed += len(history) * 7
        index = seed % len(variants)
        return variants[index]

    def _normalize_text(self, text: str) -> str:
        return " ".join(str(text).lower().split())

    def _extract_topic(self, message: str, documents: list[dict]) -> str:
        lowered = message.lower()
        company_or_role_words = {
            "amazon",
            "google",
            "microsoft",
            "meta",
            "apple",
            "netflix",
            "ibm",
            "oracle",
            "salesforce",
            "adobe",
            "nvidia",
            "walmart",
            "uber",
            "airbnb",
        }

        for document in documents:
            topic = str(document.get("topic", "")).strip()
            if topic:
                return topic

        patterns = [
            r"(?:questions?|interview|prep|prepare|practice)\s+(?:on|for|about|around|regarding)\s+([a-z0-9 .+#/-]+)",
            r"(?:give|need|want|show|tell)\s+(?:me\s+)?(?:interview\s+)?(?:questions?|question)\s+(?:on|for|about|around|regarding)\s+([a-z0-9 .+#/-]+)",
            r"(?:about|on|for|regarding)\s+([a-z0-9 .+#/-]+)\s+(?:interview|questions?|prep)",
        ]

        for pattern in patterns:
            match = re.search(pattern, lowered)
            if match:
                candidate = match.group(1).strip()
                candidate = re.sub(r"\b(for|get|give|the|a|an)\b.*$", "", candidate).strip()
                if candidate and candidate not in company_or_role_words:
                    return candidate

        if " ai " in f" {lowered} " or lowered.endswith(" ai") or lowered.startswith("ai "):
            return "AI"
        if " machine learning " in f" {lowered} ":
            return "machine learning"
        if " data science " in f" {lowered} ":
            return "data science"
        return ""

    def _extract_company(self, message: str, profile: dict) -> str:
        lowered = message.lower()
        company_map = {
            "amazon": "Amazon",
            "google": "Google",
            "microsoft": "Microsoft",
            "meta": "Meta",
            "apple": "Apple",
            "netflix": "Netflix",
            "ibm": "IBM",
            "oracle": "Oracle",
            "salesforce": "Salesforce",
            "adobe": "Adobe",
            "nvidia": "NVIDIA",
            "walmart": "Walmart",
            "uber": "Uber",
            "airbnb": "Airbnb",
        }
        for key, value in company_map.items():
            if key in lowered:
                return value
        return profile.get("target_company", "the company")

    def _extract_role(self, message: str, profile: dict) -> str:
        lowered = message.lower()
        role_map = {
            "software engineer": "Software Engineer",
            "backend engineer": "Backend Engineer",
            "frontend engineer": "Frontend Engineer",
            "data scientist": "Data Scientist",
            "data engineer": "Data Engineer",
            "ai engineer": "AI Engineer",
            "machine learning engineer": "Machine Learning Engineer",
            "developer": "Developer",
        }
        for key, value in role_map.items():
            if key in lowered:
                return value
        return profile.get("target_role", "your target role")

    def _is_interview_related(self, message: str) -> bool:
        lowered = message.lower()
        keywords = [
            "interview",
            "resume",
            "mock",
            "question",
            "answer",
            "behavioral",
            "technical",
            "coding",
            "hr",
            "role",
            "company",
            "prepar",
            "feedback",
            "readiness",
        ]
        return any(keyword in lowered for keyword in keywords)

    def _looks_like_greeting(self, message: str) -> bool:
        lowered = message.lower().strip()
        return lowered in {"hi", "hello", "hey", "helo", "hii"}

    def _generate_model_answer(self, question: str, documents: list[dict]) -> str:
        if documents:
            return documents[0].get("answer", "Use a structured, relevant answer.")
        return f"Model answer guidance for: {question}. Use context, action, result, and concise technical detail."

    def _feedback_from_score(self, evaluation: dict) -> str:
        score = evaluation.get("overall_score", 0)
        if score >= 85:
            return "Excellent answer. Keep the same structure and add a bit more depth where needed."
        if score >= 70:
            return "Good answer with room for more specificity and impact."
        return "The answer needs more structure, detail, and role-specific evidence."
