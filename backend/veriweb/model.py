import json
import time

import httpx
from pydantic import BaseModel, Field

from veriweb.config import Settings
from veriweb.schemas import QuestionRequirements


class CompletionMessage(BaseModel):
    content: str


class CompletionChoice(BaseModel):
    message: CompletionMessage


class Usage(BaseModel):
    completion_tokens: int = Field(default=0, ge=0)


class Completion(BaseModel):
    choices: list[CompletionChoice] = Field(min_length=1)
    usage: Usage = Field(default_factory=Usage)


class QueryPlan(QuestionRequirements):
    queries: list[str] = Field(min_length=3, max_length=4)


class ModelClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client
        self.last_seconds: float | None = None
        self.last_tps: float | None = None
        self.completion_tokens = 0

    @property
    def headers(self) -> dict[str, str]:
        key = self.settings.model_key.get_secret_value()
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def available(self) -> bool:
        if not self.settings.model_url:
            return False
        try:
            response = await self.client.get(
                f"{self.settings.model_url}/models", headers=self.headers, timeout=3
            )
            response.raise_for_status()
            payload = response.json()
            return (
                isinstance(payload, dict)
                and isinstance(payload.get("data"), list)
                and len(payload["data"]) > 0
            )
        except (httpx.HTTPError, ValueError):
            return False

    async def complete(
        self,
        system: str,
        content: str,
        max_tokens: int = 1600,
        schema: dict[str, object] | None = None,
    ) -> str:
        if not self.settings.model_url:
            raise ValueError("No inference endpoint configured")
        start = time.perf_counter()
        response = await self.client.post(
            f"{self.settings.model_url}/chat/completions",
            headers=self.headers,
            timeout=self.settings.model_timeout,
            json={
                "model": self.settings.model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.1,
                "max_tokens": max_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "research_output", "strict": True, "schema": schema},
                }
                if schema
                else {"type": "json_object"},
                "stream": False,
            },
        )
        response.raise_for_status()
        result = Completion.model_validate(response.json())
        self.completion_tokens += result.usage.completion_tokens
        self.last_seconds = time.perf_counter() - start
        self.last_tps = (
            round(result.usage.completion_tokens / self.last_seconds, 2)
            if result.usage.completion_tokens
            else None
        )
        return result.choices[0].message.content


def parse_object(text: str) -> object:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)
