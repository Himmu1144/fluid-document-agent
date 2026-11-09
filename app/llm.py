"""One way to call a language model, whichever provider answers.

Gemini (free tier) is tried first; if it fails or is rate-limited, Groq answers instead.
`complete_json` also checks the answer against a Pydantic model and, if it doesn't fit,
asks once more with the error attached, so the rest of the agent only ever sees valid data.
"""
import json
import logging
from typing import TypeVar

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
    client = genai.Client(api_key=config.GEMINI_API_KEY)
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


def _groq(system: str, prompt: str, want_json: bool) -> str:
    client = Groq(api_key=config.GROQ_API_KEY)
    reply = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"} if want_json else None,
    )
    return reply.choices[0].message.content or ""


PROVIDERS = [("gemini", _gemini), ("groq", _groq)]


def complete(system: str, prompt: str, want_json: bool = False) -> str:
    """The first provider that answers wins; each failure is logged, not hidden."""
    errors = []
    for name, call in PROVIDERS:
        if name in config.SKIP_PROVIDERS:
            continue
        try:
            text = call(system, prompt, want_json)
            if text.strip():
                log.info("llm: answered by %s", name)
                return text
            errors.append(f"{name}: empty answer")
        except Exception as exc:  # any SDK, network or quota error moves on to the next provider
            log.warning("llm: %s failed (%s), trying the next provider", name, type(exc).__name__)
            errors.append(f"{name}: {exc}")
    raise LLMError("No language model answered: " + " | ".join(errors))


def complete_json(system: str, prompt: str, model: type[T]) -> T:
    """Ask for JSON matching `model`. A malformed answer gets one retry, with the error shown to the model."""
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
