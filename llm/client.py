"""
Unified LLM client that supports Ollama (local Qwen) and OpenAI-compatible APIs.
Provides a single interface for all LLM calls in the system.
"""

import json
import logging
import httpx

import config

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified client for LLM inference via Ollama or OpenAI-compatible endpoints."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.provider = provider or config.LLM_PROVIDER
        self.model = model or config.LLM_MODEL
        self.base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key or config.LLM_API_KEY
        self.temperature = config.LLM_TEMPERATURE
        self.max_tokens = config.LLM_MAX_TOKENS

    def _build_url(self) -> str:
        if self.provider == "ollama":
            return f"{self.base_url}/api/chat"
        else:
            # OpenAI-compatible (OpenRouter, DeepSeek, vLLM, etc.)
            return f"{self.base_url}/v1/chat/completions"

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_payload(self, messages: list[dict], json_mode: bool = False) -> dict:
        if self.provider == "ollama":
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            }
            if json_mode:
                payload["format"] = "json"
            return payload
        else:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            return payload

    def _extract_content(self, response_data: dict) -> str:
        if self.provider == "ollama":
            return response_data.get("message", {}).get("content", "")
        else:
            choices = response_data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""

    async def chat(
        self,
        messages: list[dict],
        json_mode: bool = False,
        timeout: float = 120.0,
    ) -> str:
        """Send a chat completion request and return the response text."""
        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages, json_mode)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = self._extract_content(data)
                logger.debug(f"LLM response length: {len(content)} chars")
                return content
            except httpx.HTTPStatusError as e:
                logger.error(f"LLM API error {e.response.status_code}: {e.response.text[:500]}")
                raise
            except httpx.ConnectError:
                logger.error(
                    f"Cannot connect to LLM at {url}. "
                    f"Is Ollama running? Try: ollama serve"
                )
                raise

    async def chat_json(
        self,
        messages: list[dict],
        timeout: float = 120.0,
    ) -> dict:
        """Send a chat request expecting JSON output. Parses and returns dict."""
        raw = await self.chat(messages, json_mode=True, timeout=timeout)

        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines[1:] if not l.strip() == "```"]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM JSON output, attempting repair...")
            # Try to find JSON object/array in the text
            for start_char, end_char in [("{", "}"), ("[", "]")]:
                start = cleaned.find(start_char)
                end = cleaned.rfind(end_char)
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(cleaned[start : end + 1])
                    except json.JSONDecodeError:
                        continue
            logger.error(f"Could not parse LLM output as JSON: {raw[:300]}")
            raise ValueError(f"LLM did not return valid JSON: {raw[:300]}")


# Module-level singleton for convenience
_default_client: LLMClient | None = None


def get_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
