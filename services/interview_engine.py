from __future__ import annotations

import re
from typing import Any

from services.agent_config import AGENT_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Intent labels
# ---------------------------------------------------------------------------
INTENT_GREETING        = "GREETING"
INTENT_MOCK_START      = "MOCK_TEST_START"
INTENT_MOCK_ANSWER     = "MOCK_TEST_ANSWER"
INTENT_LIST_QUESTIONS  = "LIST_QUESTIONS"
INTENT_INFORMATIONAL   = "INFORMATIONAL"
INTENT_NAVIGATE        = "NAVIGATE"
INTENT_PROFILE_UPDATE  = "PROFILE_UPDATE"
INTENT_CHITCHAT        = "CHITCHAT"
INTENT_UNKNOWN         = "UNKNOWN"

# ---------------------------------------------------------------------------
# Topic keyword map (keyword -> canonical topic name for RAG lookup)
# ---------------------------------------------------------------------------
TOPIC_KEYWORDS = {
    "ai": "ai", "artificial intelligence": "ai", "llm": "ai", "nlp": "ai",
    "machine learning": "ai", "deep learning": "ai", "neural network": "ai",
    "transformer": "ai", "bert": "ai", "gpt": "ai",
    "data science": "data_science", "data analysis": "data_science",
    "statistics": "data_science", "pandas": "data_science",
    "dsa": "dsa", "algorithm": "dsa", "algorithms": "dsa",
    "data structure": "dsa", "data structures": "dsa",
    "binary search": "dsa", "sorting": "dsa", "recursion": "dsa",
    "linked list": "dsa", "tree": "dsa", "graph": "dsa", "stack": "dsa",
    "system design": "system_design", "design system": "system_design",
    "scalability": "system_design", "microservices": "system_design",
    "load balancer": "system_design", "caching": "system_design",
    "sql": "sql", "database": "sql", "mysql": "sql", "postgres": "sql",
    "queries": "sql", "joins": "sql", "dbms": "dbms", "normalization": "sql",
    "hr": "hr", "behavioural": "hr", "behavioral": "hr",
    "leadership": "hr", "teamwork": "hr", "soft skills": "hr",
    "tell me about yourself": "hr", "strengths": "hr", "weaknesses": "hr",
    "python": "python", "django": "python", "flask": "python",
    "javascript": "web", "react": "web", "node": "web", "angular": "web",
    "coding": "dsa", "programming": "dsa",
    "java": "java", "spring": "java", "jvm": "java",
    "oop": "oop", "object oriented": "oop", "design pattern": "oop",
    "solid": "oop", "inheritance": "oop", "polymorphism": "oop",
    "cloud": "cloud", "aws": "cloud", "azure": "cloud", "gcp": "cloud",
    "docker": "cloud", "kubernetes": "cloud", "devops": "cloud",
    "ci/cd": "cloud", "ci cd": "cloud", "terraform": "cloud",
    "networking": "networking", "network": "networking", "tcp": "networking",
    "udp": "networking", "dns": "networking", "http": "networking",
    "rest api": "networking", "api": "networking",
    "git": "git", "version control": "git", "github": "git",
    "web": "web", "html": "web", "css": "web", "frontend": "web",
    "backend": "web", "full stack": "web",
    "testing": "testing", "unit test": "testing", "tdd": "testing",
    "integration test": "testing", "qa": "testing",
    "security": "security", "cybersecurity": "security", "owasp": "security",
    "encryption": "security", "authentication": "security",
    "agile": "agile", "scrum": "agile", "kanban": "agile", "sprint": "agile",
    "os": "os", "operating system": "os", "process": "os", "thread": "os",
}


class InterviewEngine:
    def __init__(self, rag_service, score_service, agent_instructions: dict, orchestrate_client=None) -> None:
        self.rag_service = rag_service
        self.score_service = score_service
        self.agent_instructions = agent_instructions
        self.orchestrate_client = orchestrate_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        profile  = payload.get("profile", {})
        message  = payload.get("message", "")
        history  = payload.get("history", [])
        documents = self.rag_service.retrieve(message, profile=profile, top_k=5)
        answer   = self._generate_with_model_or_fallback(message, profile, documents, history)
        readiness = self.score_service.score_response(answer, [doc.get("answer", "") for doc in documents])
        return {
            "reply": answer,
            "sources": documents,
            "readiness": readiness,
            "history_count": len(history),
            "agent_instructions": self.agent_instructions,
        }

    def evaluate_answer(self, payload: dict[str, Any]) -> dict:
        answer   = payload.get("answer", "")
        question = payload.get("question", "")
        context  = self.rag_service.retrieve(question, profile=payload.get("profile", {}), top_k=5)
        expected_signals = [item.get("answer", "") for item in context]
        evaluation = self.score_service.score_response(answer, expected_signals)
        evaluation["model_answer"]    = self._generate_model_answer(question, context)
        evaluation["feedback"]        = self._feedback_from_score(evaluation)
        evaluation["recommendations"] = [
            "Add a concise situation-action-result structure",
            "Mention measurable outcomes",
            "Tie the response back to the target role",
        ]
        return evaluation

    # ------------------------------------------------------------------
    # Intent classification
    # ------------------------------------------------------------------

    def _classify_intent(self, message: str, history: list[dict]) -> str:
        msg = message.strip().lower()

        if self._looks_like_greeting(msg):
            return INTENT_GREETING

        # "give more", "more", "show more", "more questions" => list more on same topic
        more_triggers = ["give more", "show more", "more questions", "more please", "give me more"]
        if any(t in msg for t in more_triggers) or msg.strip() == "more":
            return INTENT_LIST_QUESTIONS

        if any(w in msg for w in ["next question", "next", "skip", "another question", "continue"]):
            if self._is_active_mock(history):
                return INTENT_NAVIGATE
            # Outside mock, treat "next" as wanting more questions
            return INTENT_LIST_QUESTIONS

        mock_triggers = ["mock test", "mock interview", "start mock", "test me", "quiz me",
                         "start test", "start interview", "practice interview", "start practice",
                         "interactive", "assess me", "ask me a question", "ask me questions"]
        if any(t in msg for t in mock_triggers):
            return INTENT_MOCK_START

        if self._is_active_mock(history) and not self._is_new_command(msg):
            return INTENT_MOCK_ANSWER

        info_triggers = ["what is", "what are", "how does", "how do", "how is", "why is",
                         "why does", "explain", "describe", "difference between",
                         "define", "tell me about", "what do you mean", "vs ", " vs"]
        if any(t in msg for t in info_triggers):
            return INTENT_INFORMATIONAL

        list_triggers = ["give me questions", "show me questions", "list questions",
                         "give questions", "questions on", "questions for",
                         "questions about", "interview questions", "some questions"]
        if any(t in msg for t in list_triggers):
            return INTENT_LIST_QUESTIONS

        if self._detect_topic(msg) and len(message.split()) <= 4:
            return INTENT_LIST_QUESTIONS

        role_words = ["engineer", "developer", "scientist", "analyst", "manager",
                      "programmer", "designer", "consultant", "architect"]
        exp_words  = ["entry", "mid", "senior", "junior", "fresher", "experienced"]
        if any(w in msg for w in role_words + exp_words):
            return INTENT_PROFILE_UPDATE

        chitchat = {"yes", "no", "ok", "okay", "sure", "thanks", "thank you", "fine",
                    "cool", "agree", "got it", "understood", "great", "nice", "good"}
        if msg.strip(".,!?") in chitchat or all(w in chitchat for w in msg.split()):
            return INTENT_CHITCHAT

        return INTENT_UNKNOWN

    def _is_active_mock(self, history: list[dict]) -> bool:
        mock_markers = [
            "here is your", "mock test", "question:", "first question",
            "next question", "behavioral question", "please type your answer",
            "type your answer", "your answer", "question 1", "question 2"
        ]
        end_markers = [
            "here is a list of", "here are", "tailored to your profile",
            "topics you can explore", "questions for you to practice"
        ]
        for h in reversed(history):
            if h.get("role") == "assistant":
                c = h.get("content", "").lower()
                if any(m in c for m in end_markers):
                    return False
                if any(m in c for m in mock_markers):
                    return True
                return False
        return False

    def _is_new_command(self, msg: str) -> bool:
        command_words = [
            "mock", "test", "list", "give", "show", "questions", "next",
            "skip", "start", "interview", "topic", "help", "sql", "ai",
            "dsa", "hr", "system design", "data science", "python"
        ]
        return any(w in msg for w in command_words) or len(msg.split()) <= 2

    # ------------------------------------------------------------------
    # Topic detection helpers
    # ------------------------------------------------------------------

    def _detect_topic(self, text: str) -> str:
        t = text.lower()
        for kw in sorted(TOPIC_KEYWORDS, key=len, reverse=True):
            if kw in t:
                return TOPIC_KEYWORDS[kw]
        return ""

    def _extract_topic(self, message: str, documents: list[dict]) -> str:
        for doc in documents:
            topic = str(doc.get("topic", "")).strip()
            if topic:
                return topic
        return self._detect_topic(message)

    # ------------------------------------------------------------------
    # Main fallback router
    # ------------------------------------------------------------------

    def _get_previous_topic(self, history: list[dict]) -> str:
        """Extract topic from the last assistant message that listed questions."""
        for h in reversed(history):
            if h.get("role") == "assistant":
                c = h.get("content", "").lower()
                # Look for topic labels like "DSA interview questions" or "**AI**"
                for kw in sorted(TOPIC_KEYWORDS, key=len, reverse=True):
                    if kw in c:
                        return TOPIC_KEYWORDS[kw]
                break
        return ""

    def _get_already_asked_questions(self, history: list[dict]) -> set:
        """Collect all questions already shown to avoid repetition."""
        asked = set()
        for h in history:
            if h.get("role") == "assistant":
                content = h.get("content", "").lower()
                for doc in self.rag_service.documents:
                    q = doc.get("question", "").lower()
                    if q and q in content:
                        asked.add(q)
        return asked

    def _generate_with_local_fallback(self, message: str, profile: dict, documents: list[dict], history: list[dict]) -> str:
        intent  = self._classify_intent(message, history)
        role    = self._extract_role(message, profile)
        company = self._extract_company(message, profile)
        topic   = self._extract_topic(message, documents)
        exp     = profile.get("experience_level", "your experience level")

        # If no topic detected from current message, use previous conversation topic
        if not topic:
            topic = self._get_previous_topic(history)

        if intent == INTENT_GREETING:
            name = profile.get("candidate_name", "")
            greeting = "Hi" + (", " + name if name else "") + "! 👋"
            return (
                greeting + " I'm your **AI Interview Trainer Agent** powered by RAG.\n\n"
                "I can help you:\n"
                "• 📋 **List interview questions** on any topic — just type *AI*, *SQL*, *DSA*, *HR*, *System Design*\n"
                "• 🎯 **Start a mock interview** — type *mock test* or *start interview*\n"
                "• 💡 **Explain concepts** — type *explain X* or *what is X*\n"
                "• 📄 **Analyze your resume** and tailor questions to your profile\n\n"
                "What would you like to do today?"
            )

        if intent == INTENT_LIST_QUESTIONS:
            # Get a bigger pool, then filter out already-asked questions
            docs = self.rag_service.retrieve(topic or "interview", profile=profile, top_k=20)
            if not docs:
                docs = self.rag_service.retrieve("interview", profile=profile, top_k=20)

            # Filter out questions already shown in conversation
            asked = self._get_already_asked_questions(history)
            fresh_docs = [d for d in docs if d.get("question", "").lower() not in asked]
            if not fresh_docs:
                fresh_docs = docs  # If all exhausted, cycle

            if fresh_docs:
                questions = ["**" + str(i+1) + ".** " + doc.get("question", "") for i, doc in enumerate(fresh_docs[:5])]
                topic_label = (topic or "Interview").upper()
                return (
                    "Here are **" + topic_label + "** interview questions tailored to your profile:\n\n"
                    + "\n".join(questions)
                    + "\n\n💬 Type **give more** for more questions, **mock test** to practice, or **explain** any question!"
                )
            return (
                "Here are some common interview questions to get you started:\n\n"
                "**1.** Tell me about yourself and your background.\n"
                "**2.** Describe a challenging project and how you handled it.\n"
                "**3.** How do you approach problem-solving under pressure?\n"
                "**4.** What are your key technical strengths?\n"
                "**5.** Where do you see yourself in 5 years?\n\n"
                "💬 Type a topic like *AI*, *DSA*, or *SQL* to get role-specific questions!"
            )

        if intent == INTENT_MOCK_START:
            docs = documents
            if not docs and topic:
                docs = self.rag_service.retrieve(topic, profile=profile, top_k=5)
            if not docs:
                docs = self.rag_service.retrieve("interview", profile=profile, top_k=5)

            selected = self._get_next_question_doc(docs, history)
            if selected:
                q_topic = selected.get("topic", topic or "interview").upper()
                return (
                    "🎯 **Mock Interview Started!**\n\n"
                    "I will ask you one question at a time and give detailed feedback on your answers.\n\n"
                    "**Topic:** " + q_topic + " | **Level:** " + exp + "\n\n"
                    "---\n\n"
                    "📝 **Question 1:** " + selected.get("question", "") + "\n\n"
                    "*Type your answer below — be as detailed as possible!*"
                )
            return (
                "🎯 **Mock Interview Started!**\n\n"
                "📝 **Question 1:** Tell me about yourself, your background, and why you are applying for this role.\n\n"
                "*Type your answer below — be as detailed as possible!*"
            )

        if intent == INTENT_MOCK_ANSWER:
            last_q_doc = self._find_last_asked_question(history)
            if last_q_doc:
                expected = last_q_doc.get("answer", "")
                eval_res = self.score_service.score_response(message, [expected])
                score    = eval_res.get("overall_score", 0)
                strengths  = ", ".join(eval_res.get("strengths", [])) or "Good effort!"
                weaknesses = ", ".join(eval_res.get("weaknesses", [])) or "Keep polishing your answers."
                emoji = "🟢" if score >= 75 else ("🟡" if score >= 50 else "🔴")
                return (
                    "**📊 Feedback on your answer:**\n\n"
                    + emoji + " **Score:** " + str(score) + "/100\n"
                    "✅ **Strengths:** " + strengths + "\n"
                    "⚠️ **Improve:** " + weaknesses + "\n\n"
                    "💡 **Model Answer:**\n> " + expected + "\n\n"
                    "---\n"
                    "Type **next** to get the next question, or ask me anything else!"
                )
            return (
                "I did not catch which question you were answering. "
                "Type **mock test** to restart, or ask me for a **list of questions** on a topic!"
            )

        if intent == INTENT_NAVIGATE:
            docs = documents
            if not docs:
                docs = self.rag_service.retrieve("interview", profile=profile, top_k=5)
            selected = self._get_next_question_doc(docs, history)
            if selected:
                q_topic = selected.get("topic", topic or "interview").upper()
                return (
                    "📝 **Next Question (" + q_topic + "):**\n\n"
                    "**" + selected.get("question", "") + "**\n\n"
                    "*Type your answer below!*"
                )
            return "🎉 You have completed all the questions! Great job. Type a topic to start fresh, or **mock test** for another round."

        if intent == INTENT_INFORMATIONAL:
            if documents:
                best = documents[0]
                q    = best.get("question", "")
                ans  = best.get("answer", "")
                extras = [d for d in documents[1:3]]
                response = "**" + q + "**\n\n" + ans
                if extras:
                    related = "\n".join("• **" + d.get("question","") + "**" for d in extras)
                    response += "\n\n**Related topics:**\n" + related
                response += "\n\n💬 Want to practice this? Type **mock test** to get started!"
                return response
            return (
                "Great question! Here is what I know about **" + (topic or "this topic") + "**:\n\n"
                "This is an important area in interviews. Review the fundamentals, practice coding problems if applicable, "
                "and prepare real-world examples from your experience.\n\n"
                "💡 Type a more specific topic like *AI*, *SQL*, *System Design*, or *DSA* and I will pull up targeted questions!"
            )

        if intent == INTENT_PROFILE_UPDATE:
            return (
                "Got it! 🎯 I will tailor everything for a **" + role + "** role at **" + company + "** — " + exp + " level.\n\n"
                "You can now:\n"
                "• Type a topic (e.g. *AI*, *SQL*) to get **" + role + "**-specific questions\n"
                "• Type **mock test** to start an interactive interview session\n"
                "• Upload your **resume** for a personalised readiness report"
            )

        if intent == INTENT_CHITCHAT:
            return (
                "Sure! 😊 Here is what you can do next:\n\n"
                "• Type a topic like **AI**, **SQL**, **DSA**, **HR**, or **System Design** for questions\n"
                "• Type **mock test** to start a practice interview\n"
                "• Type **explain [topic]** to understand a concept deeply\n\n"
                "What would you like to explore?"
            )

        if documents:
            best = documents[0]
            return (
                "Here is the most relevant information I found:\n\n"
                "**" + best.get("question","") + "**\n\n" + best.get("answer","") + "\n\n"
                "💬 Type a topic like *AI*, *SQL*, *DSA* to get a full question list, or **mock test** to start practising!"
            )
        return (
            "I am your **AI Interview Trainer Agent**! 🤖\n\n"
            "Try one of these:\n"
            "• Type **AI**, **SQL**, **DSA**, **HR**, or **System Design** to get interview questions\n"
            "• Type **mock test** to start a practice interview\n"
            "• Type **explain [anything]** to get a detailed explanation\n"
            "• Upload your **resume** for a personalised coaching plan"
        )

    # ------------------------------------------------------------------
    # Helper: find the question the bot last asked
    # ------------------------------------------------------------------

    def _find_last_asked_question(self, history: list[dict]) -> dict | None:
        for h in reversed(history):
            if h.get("role") == "assistant":
                assistant_text = h.get("content", "").lower()
                for doc in self.rag_service.documents:
                    q_text = doc.get("question", "").lower()
                    if q_text and q_text in assistant_text:
                        return doc
                return None
        return None

    def _get_next_question_doc(self, documents: list[dict], history: list[dict]) -> dict | None:
        if not documents:
            return None
        asked_questions = set()
        for h in history:
            content = h.get("content", "").lower()
            for doc in documents:
                q = doc.get("question", "").lower()
                if q and q in content:
                    asked_questions.add(doc.get("question"))
        for doc in documents:
            if doc.get("question") not in asked_questions:
                return doc
        return documents[0]

    # ------------------------------------------------------------------
    # Model / Orchestrate integration
    # ------------------------------------------------------------------

    def _generate_with_model_or_fallback(self, message: str, profile: dict, documents: list[dict], history: list[dict]) -> str:
        prompt = self._build_prompt(message, profile, documents)
        if self.orchestrate_client and self.orchestrate_client.configured:
            try:
                response = self.orchestrate_client.generate(
                    prompt,
                    context={"profile": profile, "documents": documents},
                )
                if response:
                    print(f"[IBM Watson Orchestrate] Generated response using Agent: {self.orchestrate_client.agent_id}")
                    return self._postprocess_reply(response, message, profile, history)
            except Exception as e:
                print(f"[IBM Watson Orchestrate] Connection error: {e}")

        print("[Fallback] IBM Watson Orchestrate not configured. Using local fallback.")
        return self._generate_with_local_fallback(message, profile, documents, history)

    def _build_prompt(self, message: str, profile: dict, documents: list[dict]) -> str:
        context_block = "\n".join(
            [
                "- Topic: " + doc.get("topic","") + "\n  Question: " + doc.get("question","") + "\n  Suggested Answer: " + doc.get("answer","")
                for doc in documents
            ]
        ) or "No matching knowledge base context found."

        return (
            str(AGENT_SYSTEM_PROMPT) + "\n\n"
            "AGENT INSTRUCTIONS: " + str(self.agent_instructions) + "\n"
            "Candidate profile: " + str(profile) + "\n"
            "Knowledge base context:\n" + context_block + "\n\n"
            "User message: " + message + "\n\n"
            "You are a dynamic and friendly conversational AI interview coach powered by RAG. "
            "Respond like ChatGPT: concise, helpful, and context-aware. "
            "1. If the user asks for questions, return a numbered list of 4-5 relevant questions. "
            "2. If the user wants a mock test, ask exactly one question at a time. "
            "3. If the user answers a question, evaluate and give structured feedback. "
            "4. If the user asks to explain something, give a clear explanation. "
            "Use Markdown formatting. Keep responses under 250 words unless listing questions."
        )

    def _postprocess_reply(self, reply: str, message: str, profile: dict, history: list[dict]) -> str:
        cleaned = str(reply).strip()
        if not cleaned:
            return self._generate_with_local_fallback(message, profile, [], history)
        if len(cleaned) > 1500:
            cleaned = cleaned[:1497].rsplit(" ", 1)[0] + "..."
        return cleaned

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _normalize_text(self, text: str) -> str:
        return " ".join(str(text).lower().split())

    def _extract_company(self, message: str, profile: dict) -> str:
        company_map = {
            "amazon": "Amazon", "google": "Google", "microsoft": "Microsoft",
            "meta": "Meta", "apple": "Apple", "netflix": "Netflix", "ibm": "IBM",
            "oracle": "Oracle", "salesforce": "Salesforce", "adobe": "Adobe",
            "nvidia": "NVIDIA", "walmart": "Walmart", "uber": "Uber", "airbnb": "Airbnb",
        }
        lowered = message.lower()
        for key, value in company_map.items():
            if key in lowered:
                return value
        return profile.get("target_company", "your target company")

    def _extract_role(self, message: str, profile: dict) -> str:
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
        lowered = message.lower()
        for key, value in role_map.items():
            if key in lowered:
                return value
        return profile.get("target_role", "your target role")

    def _looks_like_greeting(self, text: str) -> bool:
        clean = text.strip(".,!? ")
        return clean in {"hi", "hello", "hey", "helo", "hii", "hiya", "howdy", "greetings",
                         "good morning", "good evening", "good afternoon"}

    def _generate_model_answer(self, question: str, documents: list[dict]) -> str:
        if documents:
            return documents[0].get("answer", "Use a structured, relevant answer.")
        return "Model answer for: " + question + ". Use context, action, result, and concise technical detail."

    def _feedback_from_score(self, evaluation: dict) -> str:
        score = evaluation.get("overall_score", 0)
        if score >= 85:
            return "Excellent answer. Keep the same structure and add a bit more depth where needed."
        if score >= 70:
            return "Good answer with room for more specificity and impact."
        return "The answer needs more structure, detail, and role-specific evidence."
