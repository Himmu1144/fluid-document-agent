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
