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

    def _get_next_question_doc(self, documents: list[dict], history: list[dict]) -> dict | None:
        if not documents:
            return None
        asked_questions = set()
        for h in history:
            content = h.get("content", "").lower()
            for doc in documents:
                q = doc.get("question", "").lower()
                if q in content:
                    asked_questions.add(doc.get("question"))
        for doc in documents:
            if doc.get("question") not in asked_questions:
                return doc
        return documents[0]

    def _generate_with_local_fallback(self, message: str, profile: dict, documents: list[dict], history: list[dict]) -> str:
        if not self._is_interview_related(message, history):
            return "I only answer interview-preparation questions. Tell me your target role, company, or interview type."

        role = self._extract_role(message, profile)
        company = self._extract_company(message, profile)
        topic = self._extract_topic(message, documents)
        experience = profile.get("experience_level", "your experience level")
        
        # 1. Check if the user is answering a question we previously asked
        last_question_doc = None
        if history:
            for h in reversed(history):
                if h.get("role") == "assistant":
                    assistant_text = h.get("content", "").lower()
                    # Look up if this text matches any of our RAG documents' questions
                    for doc in self.rag_service.documents:
                        q_text = doc.get("question", "").lower()
                        if q_text and q_text in assistant_text:
                            last_question_doc = doc
                            break
                    break
        
        is_greeting = self._looks_like_greeting(message)
        is_navigating = any(word in message.lower() for word in ["next", "more", "continue", "another", "skip"])
        
        # If the user is submitting an answer to a question we asked, evaluate it
        if last_question_doc and not is_greeting and not is_navigating and len(message.split()) > 3:
            expected_answer = last_question_doc.get("answer", "")
            eval_res = self.score_service.score_response(message, [expected_answer])
            strengths_str = ", ".join(eval_res.get("strengths", []))
            weaknesses_str = ", ".join(eval_res.get("weaknesses", []))
            
            return (
                f"Thank you for your response! Here is my feedback on your answer:\n\n"
                f"📊 **Score**: {eval_res['overall_score']}/100\n"
                f"✅ **Strengths**: {strengths_str or 'None identified'}\n"
                f"❌ **Areas for Improvement**: {weaknesses_str or 'Keep up the good work!'}\n\n"
                f"💡 **Suggested Answer Guide**: {expected_answer}\n\n"
                f"Would you like to try another question? You can ask for a topic (e.g., 'give me a question on AI' or 'system design')."
            )

        # 2. Greeting Handler (Only if first message or explicitly a greeting)
        if is_greeting or not history:
            return self._pick_variant(
                [
                    f"Hi there! What role at {company} are you preparing for, and what is your experience level?",
                    f"Hello! Tell me the job role you want and your experience level, and I'll tailor the prep for {company}.",
                    f"Hi! What job are you targeting at {company}, and how many years of experience do you have?",
                ],
                message,
                history,
            )

        # 3. Informational / Q&A Query Handler (Respond like ChatGPT using RAG context)
        is_informational = any(word in message.lower() for word in [
            "what", "how", "why", "explain", "describe", "difference", "define", "concept", "versus", "vs", "tell"
        ])
        if is_informational and documents:
            best_doc = documents[0]
            return (
                f"Here is the explanation for **{best_doc.get('question')}**:\n\n"
                f"{best_doc.get('answer')}\n\n"
                f"Hope this helps! Let me know if you want to practice mock questions on this topic."
            )

        # 4. Question Request Handler
        is_requesting_question = is_navigating or any(word in message.lower() for word in ["question", "interview", "mock", "questions", "test", "practice"])
        if is_requesting_question:
            retrieved_docs = documents
            if not retrieved_docs and topic:
                retrieved_docs = self.rag_service.retrieve(topic, profile=profile, top_k=5)
            if not retrieved_docs:
                retrieved_docs = self.rag_service.retrieve("", profile=profile, top_k=5)
                
            selected_doc = self._get_next_question_doc(retrieved_docs, history)
            if selected_doc:
                topic_label = selected_doc.get("topic", topic or "interview").upper()
                return (
                    f"Here is a **{topic_label}** question for you:\n\n"
                    f"👉 **{selected_doc.get('question')}**\n\n"
                    f"Take your time to formulate an answer and type it below. I will evaluate your response!"
                )
            
            return (
                "Here is a behavioral question for you:\n\n"
                "👉 **Tell me about a time you solved a challenging technical problem.**\n\n"
                "Type your response below and I'll grade it!"
            )

        # 5. General Acknowledgment / Short Chat Handler
        if len(message.split()) <= 3 and any(word in message.lower() for word in ["yes", "no", "ok", "okay", "sure", "thanks", "thank you", "fine", "cool", "agree"]):
            return "Great! Let's keep moving. What topic or question would you like to focus on next? (e.g. AI, System Design, behavioral, etc.)"

        # 6. Profile / Job Update Handler
        role_keywords = ["engineer", "developer", "scientist", "analyst", "manager", "programmer", "designer", "consultant", "architect", "tech", "eng"]
        is_job_update = any(word in message.lower() for word in role_keywords) or role != profile.get("target_role")
        
        if is_job_update:
            return f"Got it! I will tailor the interview coaching for a {role} role at {company} ({experience}). Would you like to start a mock interview? Just type 'ask me a question' or select a topic to begin."
        else:
            return f"I see. Let's keep practicing! Would you like a question on a technical topic, HR, or behavioral scenarios? Tell me what you'd like to do next."



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

    def _is_interview_related(self, message: str, history: list[dict] | None = None) -> bool:
        if history and len(history) > 0:
            return True
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
            "hi",
            "hello",
            "hey",
            "start",
            "go",
            "next",
            "more",
            "yes",
            "no",
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
