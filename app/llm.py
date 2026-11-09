"""One way to call a language model, whichever provider answers.

Models are tried in order: each Groq model in GROQ_MODELS (each has its own free limit), then Gemini.
If one fails or is rate-limited, the next answers; if all are rate-limited, it waits 3 s and goes round once more.
`complete_json` also checks the answer against a Pydantic model and, if it doesn't fit,
asks once more with the error attached, so the rest of the agent only ever sees valid data.
"""
import json
import logging
import time
from functools import partial
from typing import Callable, TypeVar

from google import genai
from google.genai import types
from groq import Groq
from pydantic import BaseModel, ValidationError

from app import config

log = logging.getLogger("agent.llm")
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Every provider failed."""


def _gemini(system: str, prompt: str, want_json: bool) -> str:
    client = genai.Client(api_key=config.GEMINI_API_KEY,
                          http_options=types.HttpOptions(timeout=config.LLM_TIMEOUT_S * 1000))  # milliseconds
    reply = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,
            response_mime_type="application/json" if want_json else "text/plain",
        ),
    )
    return reply.text or ""


def _groq(model: str, system: str, prompt: str, want_json: bool) -> str:
    # max_retries=0: on a rate limit the SDK would otherwise wait and retry quietly (8-12 s each);
    # failing fast hands the call to the next model instead.
    client = Groq(api_key=config.GROQ_API_KEY, max_retries=0, timeout=config.LLM_TIMEOUT_S)
    reply = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"} if want_json else None,
        # gpt-oss "thinks" before answering, and those tokens count against the free tier's 8,000 per minute
        reasoning_effort="low" if model.startswith("openai/gpt-oss") else None,
    )
    return reply.choices[0].message.content or ""


def _chain() -> list[tuple[str, Callable[[str, str, bool], str]]]:
    """The models to try, in order: every Groq model (each has its own free limit), then Gemini."""
    chain: list[tuple[str, Callable[[str, str, bool], str]]] = []
    for provider in config.LLM_ORDER:
        if provider in config.SKIP_PROVIDERS:
            continue
        if provider == "groq":
            chain += [(f"groq/{m}", partial(_groq, m)) for m in config.GROQ_MODELS]
        elif provider == "gemini":
            chain.append(("gemini", _gemini))
    return chain


RATE_LIMIT_WAITS_S = (3, 8)  # free-tier limits reset within seconds; Groq's own errors say "try again in 0.7-3 s"


def complete(system: str, prompt: str, want_json: bool = False) -> str:
    """The first model that answers wins. If every model is rate-limited at once, wait briefly and go round again
    (up to two more times). Each failure is logged with its reason, never hidden."""
    errors: list[str] = []
    for round_no in range(len(RATE_LIMIT_WAITS_S) + 1):
        rate_limited = False
        for name, call in _chain():
            started = time.perf_counter()
            try:
                text = call(system, prompt, want_json)
                if text.strip():
                    log.info("llm: answered by %s (%.1fs)", name, time.perf_counter() - started)
                    return text
                errors.append(f"{name}: empty answer")
            except Exception as exc:  # any SDK, network, timeout or quota error moves on to the next model
                rate_limited |= _is_rate_limit(exc)
                log.warning("llm: %s failed after %.1fs (%s), trying the next model",
                            name, time.perf_counter() - started, type(exc).__name__)
                errors.append(f"{name}: {str(exc)[:300]}")
        if not rate_limited or round_no == len(RATE_LIMIT_WAITS_S):
            break
        wait = RATE_LIMIT_WAITS_S[round_no]
        log.warning("llm: every model is rate-limited; waiting %ss and trying again", wait)
        time.sleep(wait)
    raise LLMError("No language model answered: " + " | ".join(errors))


def _is_rate_limit(exc: Exception) -> bool:
    return "429" in str(exc) or "rate limit" in str(exc).lower() or "RESOURCE_EXHAUSTED" in str(exc)


def complete_json(system: str, prompt: str, model: type[T]) -> T:
    """Ask for JSON matching `model`. A malformed answer gets one retry, with the error shown to the model.

    The model's JSON schema is always attached here, so no caller can forget to say what shape it wants."""
    system = f"{system}\n\nReturn only JSON matching this schema:\n{json.dumps(model.model_json_schema())}"
    text = complete(system, prompt, want_json=True)
    try:
        return model.model_validate_json(_strip_fences(text))
    except (ValidationError, json.JSONDecodeError) as first:
        log.warning("llm: answer didn't match %s, retrying once", model.__name__)
        retry = (f"{prompt}\n\nYour previous answer was not valid for the required format.\n"
                 f"Error: {first}\nReturn only corrected JSON.")
        return model.model_validate_json(_strip_fences(complete(system, retry, want_json=True)))


def _strip_fences(text: str) -> str:
    """Some models wrap JSON in ```json fences even when asked not to."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()
