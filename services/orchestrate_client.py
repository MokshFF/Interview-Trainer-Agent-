from __future__ import annotations

import os
import time
from typing import Any

import requests


class OrchestrateClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("ORCHESTRATE_APIKEY", "")
        self.iam_api_key = os.getenv("ORCHESTRATE_IAM_APIKEY", self.api_key)
        self.url = os.getenv("ORCHESTRATE_URL", "")
        self.auth_type = os.getenv("ORCHESTRATE_AUTH_TYPE", "iam")
        self.agent_id = os.getenv("ORCHESTRATE_AGENT_ID", "")
        self.invoke_path = os.getenv("ORCHESTRATE_INVOKE_PATH", "")
        
        self._cached_token = None
        self._token_expires_at = 0

    @property
    def configured(self) -> bool:
        return bool((self.api_key or self.iam_api_key) and self.url)

    @property
    def can_invoke_agent(self) -> bool:
        # If not explicitly configured, we can discover agent id/path dynamically if configured
        return bool(self.configured and (self.invoke_path or self.agent_id or not self.agent_id))

    def _get_iam_token(self) -> str:
        if self._cached_token and time.time() < self._token_expires_at:
            return self._cached_token

        token_url = "https://iam.cloud.ibm.com/identity/token"
        payload = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": self.iam_api_key
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        response = requests.post(token_url, data=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        self._cached_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in - 60
        return self._cached_token

    def discover_agent_if_needed(self) -> None:
        if not self.configured:
            return
        
        if self.agent_id and self.agent_id != "your_agent_id" and self.invoke_path:
            return
            
        try:
            token = self._get_iam_token()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            agents_url = f"{self.url.rstrip('/')}/v1/orchestrate/agents"
            response = requests.get(agents_url, headers=headers, timeout=15)
            if response.status_code == 200:
                agents = response.json()
                if isinstance(agents, list) and len(agents) > 0:
                    target_agent = None
                    # First search for AskOrchestrate which has an active LLM configuration
                    for agent in agents:
                        if agent.get("name") == "AskOrchestrate" and agent.get("state") == "active":
                            target_agent = agent
                            break
                    if not target_agent:
                        for agent in agents:
                            if agent.get("state") == "active":
                                target_agent = agent
                                break
                    if not target_agent:
                        target_agent = agents[0]
                        
                    self.agent_id = target_agent.get("id")
                    self.invoke_path = f"v1/orchestrate/{self.agent_id}/chat/completions"
        except Exception as e:
            # Silently log or print
            print(f"Agent discovery failed: {e}")

    def generate(self, prompt: str, context: dict[str, Any] | None = None) -> str:
        self.discover_agent_if_needed()

        if not self.agent_id:
            return (
                "IBM watson Orchestrate credentials are loaded, but no active agent could be discovered. "
                "Please configure ORCHESTRATE_AGENT_ID and ORCHESTRATE_INVOKE_PATH."
            )

        endpoint = self._build_endpoint()
        headers = self._build_headers()
        
        # Build wxO chat completions payload
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False
        }
        
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict):
            choices = data.get("choices")
            if isinstance(choices, list) and len(choices) > 0:
                msg = choices[0].get("message", {})
                content = msg.get("content")
                if content:
                    return content

            # Fallback parser
            for key in ("output", "reply", "response", "message", "generated_text"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        return str(data)

    def _build_endpoint(self) -> str:
        path = self.invoke_path
        if not path and self.agent_id:
            path = f"v1/orchestrate/{self.agent_id}/chat/completions"
        return f"{self.url.rstrip('/')}/{path.lstrip('/')}"

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_type.lower() == "iam" and self.iam_api_key:
            try:
                token = self._get_iam_token()
                headers["Authorization"] = f"Bearer {token}"
            except Exception:
                headers["Authorization"] = f"Bearer {self.iam_api_key}"
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers