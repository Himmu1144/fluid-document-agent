from app import executor
from app.models import Plan, Section


def make_plan(*tools):
    return Plan(document_type="D", title="T", audience="A",
                tasks=[{"id": i, "title": f"S{i}", "tool": t, "instruction": "x"} for i, t in enumerate(tools, 1)])


def test_lookups_run_first_and_one_is_added_if_the_plan_forgot(monkeypatch):
    order = []
    monkeypatch.setitem(executor.TOOLS, "lookup_mock_data", lambda task, ctx: (order.append("lookup"), {"rec": 1})[1])
    monkeypatch.setitem(executor.TOOLS, "write_section",
                        lambda task, ctx: (order.append(task.title), Section(task_id=task.id, heading=task.title))[1])
    sections, facts, reports = executor.execute("req", make_plan("write_section", "write_section"))
    assert order == ["lookup", "S1", "S2"] and facts == {"rec": 1}
    assert reports[0].title.startswith("Company records")


def test_the_summary_is_written_last_but_stays_in_its_place(monkeypatch):
    order = []
    monkeypatch.setitem(executor.TOOLS, "lookup_mock_data", lambda task, ctx: {})
    monkeypatch.setitem(executor.TOOLS, "write_section",
                        lambda task, ctx: (order.append(task.title), Section(task_id=task.id, heading=task.title))[1])
    plan = Plan(document_type="D", title="T", audience="A", tasks=[
        {"id": 1, "title": "Executive Summary", "tool": "write_section", "instruction": "x"},
        {"id": 2, "title": "Scope", "tool": "write_section", "instruction": "x"},
        {"id": 3, "title": "Risks", "tool": "write_section", "instruction": "x"}])
    sections, _, _ = executor.execute("req", plan)
    assert order == ["Scope", "Risks", "Executive Summary"]
    assert [s.heading for s in sections] == ["Executive Summary", "Scope", "Risks"]


def test_a_failing_step_is_recorded_and_the_rest_still_run(monkeypatch):
    def write(task, ctx):
        if task.id == 2:
            raise RuntimeError("boom")
        return Section(task_id=task.id, heading=task.title)
    monkeypatch.setitem(executor.TOOLS, "lookup_mock_data", lambda task, ctx: {})
    monkeypatch.setitem(executor.TOOLS, "write_section", write)
    sections, _, reports = executor.execute("req", make_plan("lookup_mock_data", "write_section", "write_section"))
    assert [s.heading for s in sections] == ["S3"]
    assert [(r.id, r.status) for r in reports] == [(1, "done"), (2, "failed"), (3, "done")]


def test_later_steps_see_the_budget_total_not_just_the_table_size():
    # From a rehearsal run: the summary kept an old total because the preview showed only "[table: …; 6 rows]".
    from app.models import Table
    budget = Section(task_id=5, heading="Budget", text="Basis.",
                     table=Table(columns=["Item", "Amount"], rows=[["Engineering", "₹2,37,000"], ["Total", "₹2,60,700"]]))
    assert "Total | ₹2,60,700" in executor.build_context("req", make_plan("write_section", "write_section"), {}, [budget])
