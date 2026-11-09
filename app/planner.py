"""Step 1 of the agent: read the request and decide what to do.

The planner writes the agent's own TODO list. It decides the kind of document, fills gaps with
stated assumptions, names conflicts and how it will handle them, and picks a tool for every task.
It doesn't write any of the document itself.
"""
import json
import logging

from app.llm import complete_json
from app.models import Plan

log = logging.getLogger("agent.planner")

TOOLS = {
    "write_section": "Write prose for one section (summary, background, approach, risks, next steps…).",
    "make_table": "Produce a table (timeline, action items, responsibilities, comparison…).",
    "lookup_mock_data": "Fetch internal facts from the company's mock records: team members, past meetings, "
                        "product facts, standard costs. Use it whenever the document needs facts about the organisation.",
    "calculate": "Work out numbers: cost breakdowns, totals, timelines, staffing. Use it instead of guessing figures.",
}

SYSTEM = f"""You are the planning step of an autonomous document agent for a company that builds AI agents
for banks and insurers. You receive a plain-English request for a business document and return a plan.

Rules:
- Decide the document type and a specific title.
- Facts about the company itself (its teams, people, meetings, products, costs) must come from the records:
  plan a lookup_mock_data task for them before the sections that use them. Never invent them.
- If information is still missing, do not ask questions: make a reasonable assumption and list it under "assumptions".
- If requirements conflict (for example a deadline that is too short for the scope), list each conflict under
  "conflicts" together with how the document will handle it.
- Write 4 to 8 tasks, in the order the document should read. Each task produces one section.
- For every task choose exactly one tool:
{json.dumps(TOOLS, indent=2)}
- Don't add tasks for a title page, an assumptions section or a self-review: the agent adds those itself.
- Return only JSON that matches this schema:
{json.dumps(Plan.model_json_schema())}"""


def make_plan(request: str) -> Plan:
    plan = complete_json(SYSTEM, f"Request:\n{request}", Plan)
    log.info("plan: %s, %s, %d tasks, %d assumptions, %d conflicts",
             plan.document_type, plan.title, len(plan.tasks), len(plan.assumptions), len(plan.conflicts))
    for task in plan.tasks:
        log.info("  task %d [%s] %s", task.id, task.tool, task.title)
    return plan
