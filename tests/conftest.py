"""No test may reach a real model: the model chain is emptied for every test, so a stray call fails loudly."""
import pytest

from app import llm


@pytest.fixture(autouse=True)
def no_real_models(monkeypatch):
    monkeypatch.setattr(llm, "_chain", lambda: [])
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
