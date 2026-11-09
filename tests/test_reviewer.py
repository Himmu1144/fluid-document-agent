from app import reviewer
from app.models import Plan, Review, ReviewIssue, Section, Table, TaskReport

PLAN = Plan(document_type="Minutes", title="T", audience="A",
            tasks=[{"id": 1, "title": "Summary", "tool": "write_section", "instruction": "x"},
                   {"id": 2, "title": "Actions", "tool": "make_table", "instruction": "x"}])
DRAFT = [Section(task_id=1, heading="Summary", text="The sync was held on Wednesday 6 November 2026."),
         Section(task_id=2, heading="Actions", text="Agreed.", table=Table(columns=["Action", "Status"], rows=[["Release v4.12", "Completed"]]))]


def issue(evidence, heading="Summary"):
    return ReviewIssue(problem="p", evidence=evidence, action="revise_section", heading=heading, instruction="fix it")


def run_with(review, monkeypatch, reports=()):
    monkeypatch.setattr(reviewer, "complete_json", lambda *a, **k: review)
    monkeypatch.setitem(reviewer.TOOLS, "write_section", lambda task, ctx: Section(task_id=task.id, heading=task.title, text="fixed"))
    return reviewer.self_check("req", PLAN, {}, [s.model_copy() for s in DRAFT], list(reports))


def test_an_issue_whose_quote_is_not_in_the_draft_is_rejected(monkeypatch):
    sections, check = run_with(Review(passed=False, issues=[issue("held on Friday 7 November")]), monkeypatch)
    assert check.rejected and not check.fixes and sections[0].text == DRAFT[0].text


def test_a_verified_issue_is_fixed_with_before_and_after(monkeypatch):
    sections, check = run_with(Review(passed=False, issues=[issue("Wednesday 6 November 2026")]), monkeypatch)
    assert check.fixes and check.changes[0].before.startswith("The sync was held") and sections[0].text == "fixed"


def test_quotes_across_table_cells_are_checked_piece_by_piece():
    text = "\n".join(f"## {s.heading}\n{reviewer._as_text(s)}" for s in DRAFT)
    assert reviewer._quoted('Release v4.12 ... "Status","Completed"', text)
    assert not reviewer._quoted('Release v4.12 ... "Status","Pending"', text)


def test_a_step_that_failed_while_drafting_is_written_by_the_self_check(monkeypatch):
    failed = TaskReport(id=3, title="Next steps", tool="write_section", status="failed", note="LLMError")
    sections, check = run_with(Review(passed=True), monkeypatch, reports=[failed])
    assert sections[-1].heading == "Next steps" and check.fixes


def test_the_draft_survives_when_the_review_cannot_run(monkeypatch):
    def down(*a, **k):
        raise RuntimeError("no model")
    monkeypatch.setattr(reviewer, "complete_json", down)
    sections, check = reviewer.self_check("req", PLAN, {}, list(DRAFT), [])
    assert sections == DRAFT and not check.passed and "could not run" in check.issues[0]


def test_a_missing_budget_section_is_added_with_calculate_not_prose(monkeypatch):
    used = []
    monkeypatch.setattr(reviewer, "complete_json", lambda *a, **k: Review(passed=False, issues=[
        ReviewIssue(problem="No cost breakdown", evidence="", action="add_section", heading="Budget Breakdown", instruction="Add it")]))
    monkeypatch.setitem(reviewer.TOOLS, "calculate", lambda task, ctx: (used.append("calculate"), Section(task_id=task.id, heading=task.title))[1])
    monkeypatch.setitem(reviewer.TOOLS, "write_section", lambda task, ctx: (used.append("write_section"), Section(task_id=task.id, heading=task.title))[1])
    reviewer.self_check("req", PLAN, {}, [s.model_copy() for s in DRAFT], [])
    assert used == ["calculate"]


def test_an_add_that_overlaps_an_existing_section_revises_it_instead(monkeypatch):
    draft = [Section(task_id=1, heading="Summary", text="x"), Section(task_id=7, heading="Next Meeting", text="Thursday 12 Nov")]
    monkeypatch.setattr(reviewer, "complete_json", lambda *a, **k: Review(passed=False, issues=[
        ReviewIssue(problem="agenda missing", evidence="", action="add_section", heading="Next Meeting – Agenda (proposed)", instruction="add agenda")]))
    monkeypatch.setitem(reviewer.TOOLS, "write_section", lambda task, ctx: Section(task_id=task.id, heading=task.title, text="with agenda"))
    sections, check = reviewer.self_check("req", PLAN, {}, draft, [])
    assert [s.heading for s in sections] == ["Summary", "Next Meeting"] and sections[1].text == "with agenda"


def test_a_new_section_goes_before_the_closing_one(monkeypatch):
    draft = [Section(task_id=1, heading="Summary", text="x"), Section(task_id=8, heading="Next steps", text="y")]
    monkeypatch.setattr(reviewer, "complete_json", lambda *a, **k: Review(passed=False, issues=[
        ReviewIssue(problem="no risks", evidence="", action="add_section", heading="Risks", instruction="add risks")]))
    monkeypatch.setitem(reviewer.TOOLS, "write_section", lambda task, ctx: Section(task_id=task.id, heading=task.title, text="r"))
    sections, _ = reviewer.self_check("req", PLAN, {}, draft, [])
    assert [s.heading for s in sections] == ["Summary", "Risks", "Next steps"]
