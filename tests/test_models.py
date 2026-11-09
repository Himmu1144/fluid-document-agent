import pytest
from pydantic import ValidationError

from app.models import AgentRequest, Plan

TASK = {"id": 1, "title": "Summary", "tool": "write_section", "instruction": "x"}


def plan(**over):
    return {"document_type": "Proposal", "title": "T", "audience": "A", "tasks": [TASK, {**TASK, "id": 2}], **over}


def test_a_valid_plan_parses():
    assert len(Plan.model_validate(plan()).tasks) == 2


@pytest.mark.parametrize("bad", [{"tasks": []}, {"tasks": [{**TASK, "tool": "send_email"}, TASK]}])
def test_plans_with_no_tasks_or_unknown_tools_are_rejected(bad):
    with pytest.raises(ValidationError):
        Plan.model_validate(plan(**bad))


@pytest.mark.parametrize("text", ["hi", "          ", "x" * 2001])
def test_requests_must_be_meaningful(text):
    with pytest.raises(ValidationError):
        AgentRequest(request=text)
