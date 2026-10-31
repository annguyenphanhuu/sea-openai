"""Bounded OpenAI structured reviews; credentials and raw errors never enter traces."""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import time

import httpx


DEFAULT_MODEL = "gpt-5.4-mini"
SETTING_NAMES = frozenset({"OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_REVIEW_MODEL"})


def load_openai_env(path: Path) -> None:
    """Load an allowlist only, preserving explicitly supplied process settings."""
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() in SETTING_NAMES:
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def object_schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def validate_schema(value: object, schema: dict) -> None:
    """Validate the small closed JSON schema subset used by these reviewers."""
    kind = schema["type"]
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "boolean": type(value) is bool,
             "integer": type(value) is int}.get(kind, False)
    if not valid or ("enum" in schema and value not in schema["enum"]):
        raise ValueError("model_schema_invalid")
    if kind == "object":
        if set(value) != set(schema["properties"]):
            raise ValueError("model_schema_invalid")
        for key, field in schema["properties"].items():
            validate_schema(value[key], field)
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 50):
            raise ValueError("model_schema_invalid")
        for item in value:
            validate_schema(item, schema["items"])
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 1500):
            raise ValueError("model_schema_invalid")


@dataclass(frozen=True, slots=True)
class ReviewResult:
    status: str
    model: str
    data: dict | None = None
    code: str | None = None
    response_id: str | None = None
    duration_ms: float = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def trace(self) -> dict:
        return {"status": self.status, "model": self.model, "code": self.code,
                "response_id": self.response_id, "duration_ms": round(self.duration_ms, 1),
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens}


class StructuredReviewer:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, *,
                 timeout: float = 30, transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("openai_configuration_missing")
        if not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError("model_timeout_invalid")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self._transport = transport

    async def review(self, *, name: str, instructions: str, context: dict,
                     schema: dict, validate: Callable[[dict], None] | None = None) -> ReviewResult:
        started = time.monotonic()
        code = "model_output_rejected"
        try:
            content = json.dumps(context, ensure_ascii=False, allow_nan=False)
            if len(content.encode("utf-8")) > 48000:
                raise ValueError("model_context_too_large")
            payload = {
                "model": self.model, "store": False, "instructions": instructions,
                "input": [{"role": "user", "content": content}],
                "text": {"format": {"type": "json_schema", "name": name,
                                    "strict": True, "schema": schema}},
                "max_output_tokens": 3000,
            }
            if self.model.startswith("gpt-5"):
                payload["reasoning"] = {"effort": "low"}
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(transport=self._transport, timeout=self.timeout,
                                             follow_redirects=False, trust_env=False) as client:
                    response = await client.post("https://api.openai.com/v1/responses",
                        headers={"Authorization": "Bearer " + self._api_key}, json=payload)
                    response.raise_for_status()
                    if len(response.content) > 100000:
                        raise ValueError("model_output_too_large")
                    body = response.json()
            if body.get("status") != "completed":
                raise ValueError("model_incomplete")
            parts = [part for item in body["output"] if item.get("type") == "message"
                     for part in item.get("content", [])]
            if any(part.get("type") == "refusal" for part in parts):
                raise ValueError("model_refused")
            texts = [part["text"] for part in parts if part.get("type") == "output_text"]
            if len(texts) != 1:
                raise ValueError("model_output_missing")
            data = json.loads(texts[0])
            validate_schema(data, schema)
            if validate:
                validate(data)
            usage = body.get("usage") or {}
            counts = [usage.get(key, 0) for key in ("input_tokens", "output_tokens")]
            if any(type(count) is not int or count < 0 for count in counts):
                raise ValueError("model_usage_invalid")
            response_id = body.get("id")
            if response_id is not None and (not isinstance(response_id, str) or len(response_id) > 200):
                raise ValueError("model_id_invalid")
            return ReviewResult("succeeded", self.model, data=data, response_id=response_id,
                                duration_ms=(time.monotonic() - started) * 1000,
                                input_tokens=counts[0], output_tokens=counts[1])
        except (TimeoutError, httpx.TimeoutException):
            code = "model_timeout"
        except httpx.HTTPStatusError as error:
            code = "model_http_" + str(error.response.status_code)
        except httpx.RequestError:
            code = "model_network_error"
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            pass
        return ReviewResult("fallback", self.model, code=code,
                            duration_ms=(time.monotonic() - started) * 1000)


def reviewer_from_env(environ: Mapping[str, str] | None = None) -> StructuredReviewer | None:
    environment = os.environ if environ is None else environ
    key = environment.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    return StructuredReviewer(key, environment.get("OPENAI_REVIEW_MODEL")
                              or environment.get("OPENAI_MODEL", DEFAULT_MODEL))
