import pytest
from pydantic import BaseModel

from app import llm


class Pong(BaseModel):
    answer: str
    number: int


def fake_chain(*answers):
    """Models that answer (or raise) in turn."""
    calls = []

    def model(name, outcome):
        def call(system, prompt, want_json):
            calls.append((name, prompt))
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return name, call
    return [model(f"m{i}", a) for i, a in enumerate(answers)], calls


def test_first_model_that_answers_wins(monkeypatch):
    chain, calls = fake_chain(RuntimeError("down"), '{"answer": "pong", "number": 7}')
    monkeypatch.setattr(llm, "_chain", lambda: chain)
    assert llm.complete_json("s", "p", Pong) == Pong(answer="pong", number=7)
    assert [c[0] for c in calls] == ["m0", "m1"]


def test_malformed_json_gets_one_retry_with_the_error(monkeypatch):
    answers = iter(['{"answer": "pong"}', '```json\n{"answer": "pong", "number": 7}\n```'])
    prompts = []
    monkeypatch.setattr(llm, "complete", lambda s, p, want_json=False: (prompts.append(p), next(answers))[1])
    assert llm.complete_json("s", "p", Pong).number == 7
    assert "number" in prompts[1] and "not valid" in prompts[1]  # the retry tells the model what was wrong


def test_schema_is_always_attached(monkeypatch):
    systems = []
    monkeypatch.setattr(llm, "complete", lambda s, p, want_json=False: (systems.append(s), '{"answer": "a", "number": 1}')[1])
    llm.complete_json("base", "p", Pong)
    assert '"number"' in systems[0] and systems[0].startswith("base")


def test_waits_and_retries_when_every_model_is_rate_limited(monkeypatch):
    state = {"n": 0}

    def flaky(system, prompt, want_json):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("Error code: 429 rate limit")
        return "ok"
    monkeypatch.setattr(llm, "_chain", lambda: [("only", flaky)])
    assert llm.complete("s", "p") == "ok" and state["n"] == 2


def test_all_models_failing_raises_one_clear_error(monkeypatch):
    chain, _ = fake_chain(RuntimeError("bad key"), RuntimeError("model gone"))
    monkeypatch.setattr(llm, "_chain", lambda: chain)
    with pytest.raises(llm.LLMError, match="bad key.*model gone"):
        llm.complete("s", "p")
