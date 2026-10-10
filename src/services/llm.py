"""Single OpenAI access point for every agent.

Agents must import these helpers. They must not import the OpenAI SDK.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Sequence, TypeVar

from openai import OpenAI
from pydantic import BaseModel, Field

from src.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """User-safe failure from an LLM call."""


def _structured_once(
    client: OpenAI,
    *,
    system: str,
    user: str,
    schema: type[T],
    agent_name: str,
    model: str,
) -> T:
    messages = [
        {"role": "system", "content": f"[{agent_name}]\n{system}"},
        {"role": "user", "content": user},
    ]
    parse = getattr(client.chat.completions, "parse", None)
    if parse is not None:
        try:
            response = parse(
                model=model,
                messages=messages,
                response_format=schema,
            )
            parsed = response.choices[0].message.parsed
            if parsed is not None:
                return parsed
        except Exception:
            pass
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"[{agent_name}]\n{system}\n"
                    "Return only valid JSON that matches the requested schema."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{user}\n\nRespond with JSON only. Schema:\n"
                    f"{schema.model_json_schema()}"
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise LLMError("empty structured response")
    return schema.model_validate_json(raw)


class _Classification(BaseModel):
    label: str = Field(description="One of the allowed classification labels")


def _configure_langsmith(settings) -> None:
    if not settings.langchain_tracing_v2:
        return
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if settings.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    if settings.langchain_project:
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project


def _is_openrouter(settings) -> bool:
    if "openrouter.ai" in (settings.openai_base_url or "").lower():
        return True
    return settings.openai_api_key.startswith("sk-or-")


def _base_url(settings) -> str | None:
    if settings.openai_base_url:
        return settings.openai_base_url
    if _is_openrouter(settings):
        return "https://openrouter.ai/api/v1"
    return None


def _model_name(settings) -> str:
    model = settings.openai_model
    if _is_openrouter(settings) and "/" not in model:
        return f"openai/{model}"
    return model


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    settings = get_settings()
    _configure_langsmith(settings)
    if not settings.openai_api_key:
        raise LLMError("Unable to generate content. Please retry.")
    kwargs: dict = {"api_key": settings.openai_api_key}
    base_url = _base_url(settings)
    if base_url:
        kwargs["base_url"] = base_url
    if _is_openrouter(settings):
        kwargs["default_headers"] = {
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "AWS ISV Campaign Studio",
        }
    client = OpenAI(**kwargs)
    if settings.langchain_tracing_v2:
        try:
            from langsmith.wrappers import wrap_openai

            return wrap_openai(client)
        except Exception:
            return client
    return client


def generate_structured(
    system: str,
    user: str,
    schema: type[T],
    *,
    agent_name: str,
) -> T:
    """Return a Pydantic instance. Retry once on parse/API failure."""
    settings = get_settings()
    client = _client()
    last_error: Exception | None = None
    for _ in range(2):
        try:
            return _structured_once(
                client,
                system=system,
                user=user,
                schema=schema,
                agent_name=agent_name,
                model=_model_name(settings),
            )
        except LLMError:
            raise
        except Exception as exc:
            last_error = exc
            continue
    raise LLMError("Unable to generate content. Please retry.") from last_error


def generate_text(system: str, user: str, *, agent_name: str) -> str:
    settings = get_settings()
    client = _client()
    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = client.chat.completions.create(
                model=_model_name(settings),
                messages=[
                    {"role": "system", "content": f"[{agent_name}]\n{system}"},
                    {"role": "user", "content": user},
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise LLMError("empty text response")
            return text
        except LLMError:
            raise
        except Exception as exc:
            last_error = exc
            continue
    raise LLMError("Unable to generate content. Please retry.") from last_error


def classify(
    system: str,
    user: str,
    labels: Sequence[str],
    *,
    agent_name: str,
) -> str:
    allowed = {label.strip() for label in labels}
    result = generate_structured(
        system + f"\n\nYou must set label to one of: {sorted(allowed)}",
        user,
        _Classification,
        agent_name=agent_name,
    )
    if result.label not in allowed:
        raise LLMError("Unable to generate content. Please retry.")
    return result.label
