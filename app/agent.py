"""The agent: plan → execute → self-check → write the Word document."""
import logging
import time
import uuid

from app import config
from app.docx_writer import write_docx
from app.executor import execute
from app.models import AgentResponse, SelfCheck
from app.planner import make_plan
from app.reviewer import self_check

log = logging.getLogger("agent")


def run(request: str) -> AgentResponse:
    started = time.perf_counter()
    log.info("request: %s", request)

    plan = make_plan(request)                                        # 1. its own TODO list
    sections, facts, reports = execute(request, plan)                # 2. each step, with tools
    sections, check = self_check(request, plan, facts, sections, reports)  # 3. review and fix its own draft

    doc_id = uuid.uuid4().hex[:12]
    write_docx(config.OUTPUT_DIR / f"{doc_id}.docx", plan, sections, reports, check)  # 4. the Word document

    seconds = round(time.perf_counter() - started, 1)
    done = sum(r.status == "done" for r in reports)
    log.info("finished in %.1fs: %d sections, %d/%d steps done, self-check %s", seconds, len(sections), done,
             len(reports), "passed" if check.passed else f"{len(check.fixes)} fix(es)")
    return AgentResponse(
        summary=_summary(plan, len(sections), done, len(reports), check),
        document_type=plan.document_type, title=plan.title, tasks=reports,
        assumptions=plan.assumptions, conflicts=plan.conflicts, self_check=check,
        document_url=f"/documents/{doc_id}", seconds=seconds,
    )


def _summary(plan, n_sections: int, done: int, total: int, check: SelfCheck) -> str:
    text = (f"Created a {plan.document_type.lower()}, \"{plan.title}\", with {n_sections} sections. "
            f"Planned {total} steps and completed {done}.")
    if plan.assumptions:
        text += f" Made {len(plan.assumptions)} assumption(s) where the request was silent."
    if plan.conflicts:
        text += f" Found {len(plan.conflicts)} conflicting requirement(s) and explained how they're handled."
    text += (" The self-check found no problems." if check.passed else
             f" The self-check found {len(check.issues)} issue(s) and fixed {len(check.fixes)}.")
    return text
