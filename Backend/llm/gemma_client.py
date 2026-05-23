import os
from urllib.parse import urljoin

import requests


SYSTEM_PROMPT = (
    "You are INGRES, an Indian groundwater intelligence assistant. "
    "Answer only from the verified evidence supplied by the backend. "
    "Do not invent statistics, causes, citations, schemes, or locations. "
    "Keep the answer concise, practical, and suitable for farmers, students, "
    "and local water officials."
)


class GemmaEndpointClient:
    def __init__(self, url, api_key="", endpoint_format="openai", model="ingres-gemma"):
        self.url = (url or "").strip()
        self.api_key = (api_key or "").strip()
        self.endpoint_format = (endpoint_format or "openai").strip().lower()
        self.model = model
        self.timeout = float(os.getenv("GEMMA_TIMEOUT_SECONDS", "45"))

    @classmethod
    def from_env(cls):
        return cls(
            url=os.getenv("GEMMA_ENDPOINT_URL", ""),
            api_key=os.getenv("GEMMA_API_KEY", ""),
            endpoint_format=os.getenv("GEMMA_ENDPOINT_FORMAT", "openai"),
            model=os.getenv("GEMMA_MODEL", "ingres-gemma"),
        )

    @property
    def is_configured(self):
        return bool(self.url)

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def complete(self, messages, max_tokens=300, temperature=0.25):
        if not self.is_configured:
            return ""

        if self.endpoint_format == "ollama":
            return self._complete_ollama(messages, max_tokens, temperature)
        if self.endpoint_format in {"tgi", "hf_tgi"}:
            return self._complete_tgi(messages, max_tokens, temperature)
        return self._complete_openai(messages, max_tokens, temperature)

    def _complete_openai(self, messages, max_tokens, temperature):
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        data = self._post_json(self.url, payload)
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content", "")

    def _complete_ollama(self, messages, max_tokens, temperature):
        endpoint = self.url if self.url.endswith("/api/chat") else urljoin(self.url.rstrip("/") + "/", "api/chat")
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        data = self._post_json(endpoint, payload)
        message = data.get("message") or {}
        return message.get("content", "")

    def _complete_tgi(self, messages, max_tokens, temperature):
        endpoint = self.url if self.url.endswith("/generate") else urljoin(self.url.rstrip("/") + "/", "generate")
        prompt = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages) + "\n\nASSISTANT:"
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "return_full_text": False,
            },
        }
        data = self._post_json(endpoint, payload)
        if isinstance(data, list) and data:
            return data[0].get("generated_text", "")
        return data.get("generated_text", "")

    def _post_json(self, url, payload):
        response = requests.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
