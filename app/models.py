"""The shapes of the data that move through the agent.

The planner's JSON is parsed into these models before anything runs, so a plan that names a tool
that doesn't exist, or has no tasks, is rejected at the edge instead of failing halfway through.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# The tools the planner may choose from (implemented in app/tools.py).
ToolName = Literal["write_section", "make_table", "lookup_mock_data", "calculate"]


class AgentRequest(BaseModel):
    request: str = Field(min_length=10, max_length=2000, examples=["Write meeting minutes for our weekly KYC onboarding sync"])

    @field_validator("request")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("describe the document you need in at least a few words")
        return value


class Task(BaseModel):
    """One step of the agent's own TODO list."""
    id: int
    title: str = Field(description="The section heading exactly as it should appear in the document, e.g. 'Action items' "
                                   "(a short noun phrase, not an instruction like 'Create action items table')")
    tool: ToolName
    instruction: str = Field(description="What the tool should do for this step")


class Plan(BaseModel):
    """What the planner decides before doing anything."""
    document_type: str = Field(description="e.g. Meeting minutes, Project proposal, SOP")
    title: str
    audience: str
    assumptions: list[str] = Field(default_factory=list, description="Gaps in the request, filled with stated assumptions")
    conflicts: list[str] = Field(default_factory=list, description="Requirements that can't all be met, and how they're handled")
    tasks: list[Task] = Field(min_length=2, max_length=10)


class Table(BaseModel):
    columns: list[str] = Field(min_length=1)
    rows: list[list[str]]


class Section(BaseModel):
    """The output of one task: a heading with text, a table, or both."""
    task_id: int
    heading: str
    text: str = ""
    table: Table | None = None


class SelfCheck(BaseModel):
    """The reviewer's verdict on the draft (the agent's one engineering improvement)."""
    passed: bool
    issues: list[str] = Field(default_factory=list)
    fixes: list[str] = Field(default_factory=list, description="What was changed in response")


class TaskReport(BaseModel):
    id: int
    title: str
    tool: ToolName
    status: Literal["done", "failed"]
    note: str = ""


class AgentResponse(BaseModel):
    summary: str
    document_type: str
    title: str
    tasks: list[TaskReport]
    assumptions: list[str]
    conflicts: list[str]
    self_check: SelfCheck
    document_url: str
    seconds: float
