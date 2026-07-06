from __future__ import annotations

import json
from pathlib import Path


class RAGService:
    def __init__(self, kb_path: Path, collection_name: str = "interview_knowledge") -> None:
        self.kb_path = kb_path
        self.collection_name = collection_name
        self.documents = self._load_documents()

    def _load_documents(self) -> list[dict]:
        documents: list[dict] = []
        for path in self.kb_path.glob("*.json"):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, list):
                    documents.extend(payload)
            except Exception:
                continue
        return documents

    def document_count(self) -> int:
        return len(self.documents)

    def retrieve(self, query: str, profile: dict | None = None, top_k: int = 5) -> list[dict]:
        import re
        
        # Split query and profile into clean whole-words
        query_words = set(re.findall(r'[a-z0-9.+#/-]+', query.lower()))
        
        # Filter out common prepositions, conjunctions, pronouns, verbs, and helper words to prevent false-positive matches
        stop_words = {
            "a", "an", "the", "and", "or", "but", "if", "then", "of", "at", "by", "for", 
            "with", "about", "to", "in", "on", "from", "give", "me", "show", "get", "i", 
            "want", "questions", "question", "based", "tell", "ask", "please", "find", 
            "you", "your", "my", "we", "us", "they", "them", "he", "she", "it", "is", 
            "are", "am", "was", "were", "be", "been", "do", "does", "did", "have", "has", 
            "had", "can", "could", "would", "should", "some", "any", "more", "next", "like"
        }
        query_words = query_words - stop_words
        
        # Map multi-word phrases to keywords used in the database
        query_lower = query.lower()
        if "artificial intelligence" in query_lower:
            query_words.add("ai")
        if "machine learning" in query_lower:
            query_words.add("ml")
            query_words.add("ai")
        if "system design" in query_lower:
            query_words.add("system_design")
        if "data science" in query_lower:
            query_words.add("data_science")
        
        profile_words = set()
        if profile:
            profile_words.update(re.findall(r'[a-z0-9.+#/-]+', str(profile.get("target_role", "")).lower()))
            profile_words.update(re.findall(r'[a-z0-9.+#/-]+', str(profile.get("target_company", "")).lower()))
            for skill in profile.get("skills", []):
                profile_words.update(re.findall(r'[a-z0-9.+#/-]+', str(skill).lower()))
        profile_words = profile_words - stop_words

        scored: list[tuple[int, dict]] = []
        for document in self.documents:
            doc_text = " ".join(
                [
                    str(document.get("topic", "")),
                    str(document.get("question", "")),
                    str(document.get("answer", "")),
                    " ".join(document.get("tags", [])),
                ]
            ).lower()
            doc_words = set(re.findall(r'[a-z0-9.+#/-]+', doc_text))
            
            # Count keyword matches
            query_match_count = sum(term in doc_words for term in query_words)
            profile_match_count = sum(term in doc_words for term in profile_words)
            
            # Enforce relevance threshold: must match at least one user query keyword
            # If the user query is very short or generic (empty query_words), we allow profile matches
            if query_match_count > 0 or (not query_words and profile_match_count > 0):
                score = query_match_count * 2 + profile_match_count
                scored.append((score, document))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

