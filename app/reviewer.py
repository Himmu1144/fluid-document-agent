"""Step 3 of the agent: the self-check (the one engineering improvement).

After the draft is written, the agent reviews it against the request, like an editor would: is everything
the request asked for covered, are the figures consistent between sections, does it contradict the facts?
Each issue comes with a fix (add a section, or revise one), and the fixes are applied with the same writing
tools. It is bounded on purpose: one review, at most three fixes, so cost and time stay predictable.
"""
import json
import logging

from app.executor import build_context
from app.llm import complete_json
from app.models import Plan, Review, ReviewIssue, Section, SelfCheck, Task, TaskReport
from app.tools import TOOLS

log = logging.getLogger("agent.reviewer")

MAX_FIXES = 3

REVIEWER = """You are a strict senior reviewer checking a draft business document before it goes to a client.
Check the draft against the request:
1. Coverage: every thing the request explicitly asks for has a section or is clearly addressed.
2. Consistency: figures, dates, names and budgets agree between sections and with the company records.
3. Honesty: conflicts in the request are acknowledged, not silently ignored.
The agent adds the title page and an "Assumptions and open questions" section itself, so don't ask for those.
Report only real, specific problems (at most 5), each with a fix. If the draft is good, return passed=true and no issues."""


def self_check(request: str, plan: Plan, facts: dict, sections: list[Section],
               reports: list[TaskReport]) -> tuple[list[Section], SelfCheck]:
    draft = "\n\n".join(f"## {s.heading}\n{s.text}" + (f"\n[table] {json.dumps(s.table.model_dump())}" if s.table else "")
                        for s in sections)
    try:
        review = complete_json(REVIEWER, f"Request:\n{request}\n\nConflicts the plan identified:\n"
                                         f"{json.dumps(plan.conflicts)}\n\nCompany records:\n{json.dumps(facts)}\n\n"
                                         f"Draft:\n{draft}", Review)
    except Exception as exc:  # the review must never cost the user a finished draft
        log.warning("self-check: the review couldn't run (%s); keeping the draft as it is", type(exc).__name__)
        review = Review(passed=False, issues=[])
        skipped = f"The self-check could not run ({type(exc).__name__}); the draft was not reviewed."
    else:
        skipped = ""

    # Checks in code, not left to the model: a step that failed during execution must be written now.
    issues = [ReviewIssue(problem=f"Step {r.id} \"{r.title}\" failed while drafting ({r.note[:80]})",
                          action="add_section", heading=r.title, instruction=f"Write the \"{r.title}\" section.")
              for r in reports if r.status == "failed"] + review.issues

    # One fix per section: issues about the same heading are merged into one instruction.
    merged: dict[str, ReviewIssue] = {}
    for issue in issues:
        key = issue.heading.lower()
        if key in merged:
            merged[key].instruction += f"\nAlso: {issue.instruction} (reason: {issue.problem})"
        else:
            merged[key] = issue.model_copy()

    fixes: list[str] = []
    for issue in list(merged.values())[:MAX_FIXES]:
        index = next((i for i, s in enumerate(sections) if s.heading.lower() == issue.heading.lower()), None)
        planned = next((t for t in plan.tasks if t.title.lower() == issue.heading.lower()), None)
        # A section is redone by the tool that made it: a wrong total is recomputed by `calculate` in Python,
        # not papered over by rewriting the text around the old table.
        tool = planned.tool if planned and planned.tool != "lookup_mock_data" else "write_section"
        instruction = f"{issue.instruction}\n(Reviewer's reason: {issue.problem})"
        if index is not None and tool == "write_section":
            instruction += f"\n\nCurrent text to improve, keeping what is right:\n{sections[index].text}"
        task = Task(id=planned.id if planned else 100 + len(fixes), title=issue.heading, tool=tool, instruction=instruction)
        try:
            context = build_context(request, plan, facts, [s for i, s in enumerate(sections) if i != index])
            redone = TOOLS[tool](task, context)
            redone.heading = sections[index].heading if index is not None else issue.heading
            if index is not None:
                sections[index] = redone
                fixes.append(f"Redid \"{redone.heading}\" with {tool}: {issue.problem}")
            else:
                sections.append(redone)
                fixes.append(f"Added \"{redone.heading}\": {issue.problem}")
        except Exception as exc:
            log.warning("self-check: couldn't apply fix for %r: %s", issue.heading, exc)
    for f in fixes:
        log.info("self-check: %s", f)

    passed = not issues and not skipped
    log.info("self-check: %s, %d issue(s), %d fix(es)", "passed" if passed else "found problems", len(issues), len(fixes))
    return sections, SelfCheck(passed=passed, issues=[i.problem for i in issues] + ([skipped] if skipped else []), fixes=fixes)
