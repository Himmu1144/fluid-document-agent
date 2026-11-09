"""The four tools the planner chooses from.

Each tool gets the task and the context so far (the request, the plan, facts found, earlier sections).
`lookup_mock_data` returns facts for later tasks; the other three return a section of the document.
Two tools don't trust the model with everything: the lookup is plain Python (no LLM), and `calculate`
lets the model choose the line items but does the arithmetic in Python.
"""
import logging
import re

from pydantic import BaseModel, Field

from app.llm import complete_json
from app.mock_data import RECORDS
from app.models import Section, Table, Task

log = logging.getLogger("agent.tools")

WRITER = """You write one section of a polished business document for a bank and insurance company.
Use the facts and earlier sections in the context; never invent names, dates or figures that contradict them.
Be specific and concise: short paragraphs, and bullet points starting with "- " where they help.
Return only JSON with "heading" and "text" (and "table" only if asked)."""


def lookup_mock_data(task: Task, context: str) -> dict:
    """Plain Python, no LLM: returns the records whose tags match words in the task."""
    words = set(re.findall(r"[a-z]+", f"{task.title} {task.instruction}".lower()))
    found = {r["title"]: r["data"] for r in RECORDS if words & set(r["tags"])}
    log.info("lookup: %d record(s): %s", len(found), ", ".join(found) or "none")
    return found


def write_section(task: Task, context: str) -> Section:
    out = complete_json(WRITER, f"{context}\n\nWrite this section.\nHeading: {task.title}\nInstruction: {task.instruction}", _Prose)
    return Section(task_id=task.id, heading=out.heading, text=out.text)


def make_table(task: Task, context: str) -> Section:
    out = complete_json(WRITER, f"{context}\n\nWrite this section as a table, with one or two sentences of text above it."
                                f"\nHeading: {task.title}\nInstruction: {task.instruction}", _WithTable)
    return Section(task_id=task.id, heading=out.heading, text=out.text, table=out.table)


class LineItem(BaseModel):
    item: str
    quantity: float = Field(ge=0)
    unit: str = Field(description="e.g. days, minutes, licences")
    unit_cost_inr: float = Field(ge=0)


class _Estimate(BaseModel):
    heading: str
    text: str = Field(description="One or two sentences on what the estimate covers and its basis")
    items: list[LineItem] = Field(min_length=1)
    budget_limit_inr: float | None = Field(default=None, description="The budget stated in the request, if any")
    contingency_percent: float = Field(default=0, ge=0, le=50)


def calculate(task: Task, context: str) -> Section:
    """The model picks the line items and quantities from the facts; Python does every sum."""
    est = complete_json(WRITER, f"{context}\n\nBuild a cost estimate as line items (quantity × unit cost in INR), "
                                f"using the rates in the facts. Do not compute totals yourself.\n"
                                f"Heading: {task.title}\nInstruction: {task.instruction}", _Estimate)
    rows, subtotal = [], 0.0
    for li in est.items:
        amount = li.quantity * li.unit_cost_inr
        subtotal += amount
        quantity = _group(li.quantity) if li.quantity == round(li.quantity) else f"{li.quantity:g}"
        rows.append([li.item, f"{quantity} {li.unit}", _inr(li.unit_cost_inr), _inr(amount)])
    contingency = subtotal * est.contingency_percent / 100
    total = subtotal + contingency
    if contingency:
        rows.append([f"Contingency ({est.contingency_percent:g}%)", "", "", _inr(contingency)])
    rows.append(["Total", "", "", _inr(total)])
    text = est.text
    if est.budget_limit_inr:
        gap = est.budget_limit_inr - total
        text += (f"\n\nThe total of {_inr(total)} is within the stated budget of {_inr(est.budget_limit_inr)} "
                 f"({_inr(gap)} to spare)." if gap >= 0 else
                 f"\n\nThe total of {_inr(total)} is {_inr(-gap)} over the stated budget of {_inr(est.budget_limit_inr)}.")
    log.info("calculate: %d items, total %s", len(est.items), _inr(total))
    return Section(task_id=task.id, heading=est.heading, text=text,
                   table=Table(columns=["Item", "Quantity", "Unit cost", "Amount"], rows=rows))


TOOLS = {"lookup_mock_data": lookup_mock_data, "write_section": write_section,
         "make_table": make_table, "calculate": calculate}


class _Prose(BaseModel):
    heading: str
    text: str


class _WithTable(_Prose):
    table: Table


def _inr(value: float) -> str:
    """Rupees with Indian digit grouping: 1234567 → ₹12,34,567; small rates keep paise: 0.6 → ₹0.60."""
    if value < 100 and value != round(value):
        return f"₹{value:.2f}"
    return f"₹{_group(round(value))}"


def _group(number: float) -> str:
    """Indian digit grouping without a symbol: 105000 → 1,05,000."""
    whole = f"{round(number):d}"
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        whole = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head) + "," + tail
    return whole
