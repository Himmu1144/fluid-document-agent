"""Step 2 of the agent: run the plan's tasks in order.

Each task sees the request, the plan, the facts found so far and the sections already written, so later
steps build on earlier ones. A task that fails is recorded and skipped; the rest of the document still gets
written, and the failure shows up in the task report and the self-check.
"""
import json
import logging
import time

from app.models import Plan, Section, Task, TaskReport
from app.tools import TOOLS

log = logging.getLogger("agent.executor")

SECTION_PREVIEW = 600  # characters of each earlier section passed on, to keep prompts small


def build_context(request: str, plan: Plan, facts: dict, sections: list[Section]) -> str:
    parts = [
        f"Request:\n{request}",
        f"Document: {plan.document_type}, \"{plan.title}\", for {plan.audience}",
    ]
    if plan.assumptions:
        parts.append("Assumptions to follow:\n" + "\n".join(f"- {a}" for a in plan.assumptions))
    if plan.conflicts:
        parts.append("Conflicts and how to handle them:\n" + "\n".join(f"- {c}" for c in plan.conflicts))
    if facts:
        parts.append("Facts from the company records:\n" + json.dumps(facts, ensure_ascii=False))
    if sections:
        written = []
        for s in sections:
            body = s.text[:SECTION_PREVIEW]
            if s.table:
                body += f"\n[table: {', '.join(s.table.columns)}; {len(s.table.rows)} rows]"
                last = s.table.rows[-1] if s.table.rows else []
                if last and str(last[0]).lower().startswith("total"):  # later sections must quote the real total
                    body += f"\n[{' | '.join(c for c in last if c)}]"
            written.append(f"## {s.heading}\n{body}")
        parts.append("Sections already written (stay consistent with them):\n" + "\n\n".join(written))
    return "\n\n".join(parts)


def execute(request: str, plan: Plan) -> tuple[list[Section], dict, list[TaskReport]]:
    facts: dict = {}
    sections: list[Section] = []
    reports: list[TaskReport] = []
    # Lookups are cheap and change nothing, so they run first whatever order the plan gave:
    # every section is then written with the facts in hand.
    lookups = [t for t in plan.tasks if t.tool == "lookup_mock_data"]
    if not lookups:  # the prompt asks for one, but the code makes sure: facts are never left to chance
        lookups = [Task(id=0, title="Company records (added by the agent)", tool="lookup_mock_data",
                        instruction="Find the company records relevant to this request")]
        log.info("plan had no lookup task; the agent added one")
    # A summary is written last, from the finished sections, so it can't promise what they don't say;
    # it still appears where the plan put it.
    writing = [t for t in plan.tasks if t.tool != "lookup_mock_data"]
    ordered = lookups + [t for t in writing if not is_summary(t.title)] + [t for t in writing if is_summary(t.title)]
    for n, task in enumerate(ordered, 1):
        started = time.perf_counter()
        context = build_context(request, plan, facts, sections)
        try:
            result = TOOLS[task.tool](task, context if task.tool != "lookup_mock_data" else request)
            if isinstance(result, dict):  # a lookup: facts for later tasks, not a section
                facts.update(result)
                note = f"found {len(result)} record(s)" if result else "no matching records; later steps rely on assumptions"
            else:
                sections.append(result)
                note = f"wrote \"{result.heading}\"" + (f" with a {len(result.table.rows)}-row table" if result.table else "")
            reports.append(TaskReport(id=task.id, title=task.title, tool=task.tool, status="done", note=note))
            log.info("task %d/%d [%s] %s: %s (%.1fs)", n, len(ordered), task.tool, task.title, note,
                     time.perf_counter() - started)
        except Exception as exc:  # one bad step shouldn't sink the whole document
            reports.append(TaskReport(id=task.id, title=task.title, tool=task.tool, status="failed",
                                      note=f"{type(exc).__name__}: {str(exc)[:200]}"))
            log.warning("task %d/%d [%s] %s FAILED: %s", n, len(ordered), task.tool, task.title, exc)
    position = {t.id: i for i, t in enumerate(plan.tasks)}
    sections.sort(key=lambda s: position.get(s.task_id, len(position)))  # document order = the plan's order
    reports.sort(key=lambda r: position.get(r.id, -1))
    return sections, facts, reports


def is_summary(title: str) -> bool:
    """'Executive Summary', 'Summary', 'Introduction': sections that sum up the others ('Discussion Summary' doesn't)."""
    t = title.lower().strip()
    return t in {"summary", "executive summary", "introduction", "overview"} or t.startswith("executive summary")
