import json
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings

T = TypeVar("T", bound=BaseModel)
ModelTask = Literal[
    "INTENT_PARSING",
    "NORMAL_CHAT",
    "NEGOTIATION",
    "CAMPAIGN_COPY",
    "COMPLEX_CAMPAIGN_REASONING",
    "LONG_CONTEXT",
    "VERY_COMPLEX_REASONING",
    "RED_TEAM",
]


@dataclass(frozen=True)
class ModelCallTrace:
    provider: str
    model: str
    latency_ms: int
    status: str
    task: str = "INTENT_PARSING"
    attempt: int = 1


class ModelProvider(Protocol):
    name: str
    model: str

    async def structured(
        self, prompt: str, json_schema: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        url: str,
        api_key: str,
        model: str,
        timeout: float,
        max_tokens: int,
        *,
        strict_json_schema: bool = False,
        reasoning_effort: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ):
        self.name = name
        self.url = url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.strict_json_schema = strict_json_schema
        self.reasoning_effort = reasoning_effort
        self.extra_body = extra_body or {}

    async def structured(
        self, prompt: str, json_schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response_format: dict[str, Any] = {"type": "json_object"}
        if self.strict_json_schema and json_schema:
            strict_schema = self._strict_schema(json_schema)
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "sentinelpay_structured_result",
                    "strict": True,
                    "schema": strict_schema,
                },
            }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only valid JSON matching the requested schema. "
                        "Never invent money limits, credentials, payment authority, or catalog facts."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": response_format,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            **self.extra_body,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if isinstance(content, dict):
                return content
            return json.loads(content)

    @staticmethod
    def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
        """Normalize Pydantic schemas for providers enforcing strict object output."""
        normalized = deepcopy(schema)

        def visit(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") == "object" or "properties" in node:
                    node["additionalProperties"] = False
                    node["required"] = list(node.get("properties", {}).keys())
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(normalized)
        return normalized


class MockModelProvider:
    name, model = "mock", "deterministic-v1"

    def __init__(self, responses: list[dict[str, Any] | Exception]):
        self.responses = responses

    async def structured(
        self, prompt: str, json_schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        del prompt, json_schema
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ModelGateway:
    """Task-aware structured routing with deterministic validation and fail-closed fallback."""

    def __init__(
        self,
        providers: list[ModelProvider],
        max_retries: int = 0,
        task: ModelTask = "INTENT_PARSING",
    ):
        self.providers = providers
        self.traces: list[ModelCallTrace] = []
        self.max_retries = max_retries
        self.task = task

    @staticmethod
    def _provider_specs(settings: Settings, task: ModelTask) -> list[tuple]:
        groq_fast = (
            "groq",
            settings.groq_api_key,
            "https://api.groq.com/openai/v1/chat/completions",
            settings.groq_fast_model,
            True,
            "medium",
            {},
        )
        groq_reasoning = (
            "groq",
            settings.groq_api_key,
            "https://api.groq.com/openai/v1/chat/completions",
            settings.groq_reasoning_model,
            True,
            "medium",
            {},
        )
        nvidia_agent = (
            "nvidia_nim",
            settings.nvidia_nim_api_key,
            "https://integrate.api.nvidia.com/v1/chat/completions",
            settings.nvidia_agent_model,
            False,
            None,
            {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 2048},
        )
        nvidia_ultra = (
            "nvidia_nim",
            settings.nvidia_nim_api_key,
            "https://integrate.api.nvidia.com/v1/chat/completions",
            settings.nvidia_ultra_model,
            False,
            None,
            {"chat_template_kwargs": {"enable_thinking": True}},
        )
        if task in {"COMPLEX_CAMPAIGN_REASONING", "LONG_CONTEXT"}:
            return [nvidia_agent, groq_reasoning]
        if task == "VERY_COMPLEX_REASONING":
            return [groq_reasoning, nvidia_ultra]
        if task == "RED_TEAM":
            return [nvidia_agent, groq_reasoning]
        return [groq_fast, nvidia_agent]

    @classmethod
    def from_settings(
        cls, settings: Settings, task: ModelTask = "INTENT_PARSING"
    ) -> "ModelGateway":
        providers: list[ModelProvider] = []
        for name, key, url, model, strict, reasoning, extra_body in cls._provider_specs(
            settings, task
        ):
            if key:
                providers.append(
                    OpenAICompatibleProvider(
                        name,
                        url,
                        key.get_secret_value(),
                        model,
                        settings.model_timeout_seconds,
                        settings.model_max_completion_tokens,
                        strict_json_schema=strict,
                        reasoning_effort=reasoning,
                        extra_body=extra_body,
                    )
                )
        return cls(providers, settings.model_max_retries, task)

    async def parse(self, prompt: str, schema: type[T]) -> tuple[T, ModelCallTrace]:
        if not self.providers:
            raise RuntimeError("No model provider configured; request denied")
        schema_json = schema.model_json_schema()
        for provider in self.providers:
            for attempt in range(1, self.max_retries + 2):
                started = time.perf_counter()
                try:
                    result = schema.model_validate(
                        await provider.structured(prompt, schema_json)
                    )
                    trace = ModelCallTrace(
                        provider.name,
                        provider.model,
                        int((time.perf_counter() - started) * 1000),
                        "SUCCESS",
                        self.task,
                        attempt,
                    )
                    self.traces.append(trace)
                    return result, trace
                except (
                    httpx.HTTPError,
                    KeyError,
                    json.JSONDecodeError,
                    ValidationError,
                    RuntimeError,
                ) as exc:
                    self.traces.append(
                        ModelCallTrace(
                            provider.name,
                            provider.model,
                            int((time.perf_counter() - started) * 1000),
                            type(exc).__name__,
                            self.task,
                            attempt,
                        )
                    )
        raise RuntimeError("All configured model providers failed; request denied")
