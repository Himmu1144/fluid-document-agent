"""Step 3 of the agent: the self-check (the one engineering improvement).

After the draft is written, the agent reviews it against the request, like an editor would: is everything
the request asked for covered, are the figures consistent between sections, does it contradict the facts?
Each issue comes with a fix (add a section, or revise one), and the fixes are applied with the same writing
tools. It is bounded on purpose: one review, at most five fixes, so cost and time stay predictable.
"""
import json
import logging
import re

from app.executor import build_context, is_summary
from app.llm import complete_json
from app.models import Fix, Plan, Review, ReviewIssue, Section, SelfCheck, Task, TaskReport
from app.tools import TOOLS

log = logging.getLogger("agent.reviewer")

MAX_FIXES = 5  # the reviewer reports at most 5 issues, so every verified one can be fixed

REVIEWER = """You are a strict senior reviewer checking a draft business document before it goes to a client.
Check the draft against the request:
1. Coverage: every thing the request explicitly asks for has a section or is clearly addressed.
2. Consistency: figures, dates, names and budgets agree between sections and with the company records.
3. Honesty: conflicts in the request are acknowledged, not silently ignored.
The agent adds the title page and an "Assumptions and open questions" section itself, so don't ask for those.
The plan's resolutions of the conflicts are deliberate (for example a phased scope, or a total that is honestly
over the budget and says so): don't report them as problems; do report sections that contradict them.
Prefer revise_section: use add_section only when nothing in the draft covers the point, and never add a section that
repeats or extends an existing one (revise that one instead).
Report only real, specific problems (at most 5), each with a fix. For a problem in the draft, copy the exact words
that show it into "evidence" (verbatim from the draft, a few words from one sentence or one table row);
leave evidence empty only when something is entirely missing.
If the draft is good, return passed=true and no issues."""


def self_check(request: str, plan: Plan, facts: dict, sections: list[Section],
               reports: list[TaskReport]) -> tuple[list[Section], SelfCheck]:
    draft = "\n\n".join(f"## {s.heading}\n{_as_text(s)}" for s in sections)  # tables as plain "a | b | c" rows
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

    # The reviewer is a model too and can be wrong: an issue that quotes the draft must quote it truthfully.
    verified, rejected = [], []
    for issue in review.issues:
        if issue.evidence and not _quoted(issue.evidence, draft):
            rejected.append(f"{issue.problem} (quoted \"{issue.evidence}\", which isn't in the draft)")
            log.warning("self-check: dropped an unverified issue: %r is not in the draft", issue.evidence)
        else:
            verified.append(issue)
    review.issues = verified

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
    changes: list[Fix] = []
    for issue in list(merged.values())[:MAX_FIXES]:
        index = next((i for i, s in enumerate(sections) if s.heading.lower() == issue.heading.lower()), None)
        if index is None:  # "add" a section that overlaps an existing one → revise that one instead of duplicating it
            index = next((i for i, s in enumerate(sections) if _overlaps(s.heading, issue.heading)), None)
        # A section is redone by the tool that made it (found by its task id): a wrong total is recomputed by
        # `calculate` in Python, not papered over by rewriting the text. A new section gets the tool its content
        # needs, and anything about money always goes to `calculate`, so the model never does arithmetic.
        planned = next((t for t in plan.tasks if index is not None and t.id == sections[index].task_id), None)
        tool = planned.tool if planned and planned.tool != "lookup_mock_data" else _tool_for(issue.heading)
        instruction = f"{issue.instruction}\n(Reviewer's reason: {issue.problem})"
        if index is not None and tool == "write_section":
            instruction += f"\n\nCurrent text to improve, keeping what is right:\n{sections[index].text}"
        task = Task(id=planned.id if planned else 100 + len(fixes), title=issue.heading, tool=tool, instruction=instruction)
        try:
            context = build_context(request, plan, facts, [s for i, s in enumerate(sections) if i != index])
            redone = TOOLS[tool](task, context)
            redone.heading = sections[index].heading if index is not None else issue.heading
            before = _as_text(sections[index]) if index is not None else ""
            if index is not None:
                sections[index] = redone
                fixes.append(f"Redid \"{redone.heading}\" with {tool}: {issue.problem}")
            else:
                sections.insert(_new_section_position(sections), redone)
                fixes.append(f"Added \"{redone.heading}\": {issue.problem}")
            changes.append(Fix(section=redone.heading, problem=issue.problem, evidence=issue.evidence,
                               before=before, after=_as_text(redone)))
        except Exception as exc:
            log.warning("self-check: couldn't apply fix for %r: %s", issue.heading, exc)

    # A fix can change the scope, timeline or budget, and then a summary written before it would contradict the
    # fixed sections. So after any fix, the summary is brought in line (one more call; it isn't counted as a fix).
    changed = {c.section.lower() for c in changes}
    summary = next((i for i, s in enumerate(sections) if is_summary(s.heading) and s.heading.lower() not in changed), None)
    if changes and summary is not None:
        old = sections[summary]
        planned = next((t for t in plan.tasks if t.id == old.task_id), None)
        tool = planned.tool if planned and planned.tool in ("write_section", "make_table") else "write_section"
        task = Task(id=old.task_id, title=old.heading, tool=tool,
                    instruction="Rewrite this summary so it matches the sections already written exactly (scope, "
                                "languages, timeline, budget); state nothing they don't.\n\nCurrent text:\n" + old.text)
        try:
            redone = TOOLS[tool](task, build_context(request, plan, facts, [s for i, s in enumerate(sections) if i != summary]))
            redone.heading = old.heading
            sections[summary] = redone
            fixes.append(f"Updated \"{old.heading}\" to match the fixed sections")
            changes.append(Fix(section=old.heading, problem="The fixes above changed sections this summary describes",
                               before=_as_text(old), after=_as_text(redone)))
        except Exception as exc:
            log.warning("self-check: couldn't update %r after the fixes: %s", old.heading, exc)
    for f in fixes:
        log.info("self-check: %s", f)

    passed = not issues and not skipped and not rejected
    log.info("self-check: %s, %d issue(s), %d fix(es)", "passed" if passed else "found problems", len(issues), len(fixes))
    return sections, SelfCheck(passed=not issues and not skipped, issues=[i.problem for i in issues] + ([skipped] if skipped else []),
                               fixes=fixes, rejected=rejected, changes=changes)


STOPWORDS = {"and", "the", "of", "for", "a", "an", "to", "&", "–", "-", "on", "in", "proposed"}
CLOSING = ("next step", "next meeting", "conclusion", "approval", "sign-off", "way forward")


def _overlaps(existing: str, new: str) -> bool:
    """'Next Meeting – Agenda (proposed)' overlaps 'Next Meeting': most of the existing heading's words reappear."""
    words = lambda h: {w for w in re.findall(r"[a-z]+", h.lower()) if w not in STOPWORDS}
    old, fresh = words(existing), words(new)
    return bool(old) and len(old & fresh) / len(old) >= 0.6


def _new_section_position(sections: list[Section]) -> int:
    """New sections go before a closing section like 'Next steps', not after it."""
    if sections and any(c in sections[-1].heading.lower() for c in CLOSING):
        return len(sections) - 1
    return len(sections)


def _tool_for(heading: str) -> str:
    h = heading.lower()
    if any(w in h for w in ("budget", "cost", "price", "pricing", "estimate", "financial")):
        return "calculate"
    if any(w in h for w in ("table", "timeline", "schedule", "action items", "matrix", "rollout", "plan")):
        return "make_table"
    return "write_section"


def _quoted(evidence: str, draft: str) -> bool:
    """True if the quote is in the draft. A quote with "..." (e.g. across table cells) counts if every piece is."""
    text = _normalise(draft)
    evidence = re.sub(r'"\s*,\s*"', " | ", evidence)  # "Status","Completed" → Status | Completed
    pieces = [p.strip(" \"'|,:") for p in re.split(r"\.\.\.|…|\|", _normalise(evidence))]
    pieces = [p for p in pieces if len(p) >= 3]
    return bool(pieces) and all(p in text for p in pieces)


def _normalise(text: str) -> str:
    """Compare quotes loosely: case, spacing, dashes and markdown don't count."""
    text = re.sub(r"[\"“”‘’`]", "", text.lower().replace("**", "")).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    return " ".join(text.replace("\u202f", " ").replace("\u00a0", " ").split())


def _as_text(section: Section) -> str:
    rows = "\n".join(" | ".join(r) for r in [section.table.columns, *section.table.rows]) if section.table else ""
    return f"{section.text}\n{rows}".strip()
