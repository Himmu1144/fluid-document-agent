from app.models import Plan
from app.planner import one_budget_section


def titles(plan):
    return [t.title for t in plan.tasks]


def test_one_budget_section_after_the_framing_sections():
    # The real plan from a rehearsal run: the budget table opened the document and a prose "Cost Estimate"
    # did its own arithmetic next to it.
    plan = Plan(document_type="Proposal", title="T", audience="A", tasks=[
        {"id": i, "title": title, "tool": tool, "instruction": "x"} for i, (title, tool) in enumerate([
            ("Platform capabilities", "lookup_mock_data"), ("Cost estimate calculation", "calculate"),
            ("Executive Summary", "write_section"), ("Scope and Objectives", "write_section"),
            ("Project Timeline", "make_table"), ("Cost Estimate", "write_section"),
            ("Risks and Mitigations", "write_section")], 1)])
    assert titles(one_budget_section(plan)) == ["Platform capabilities", "Executive Summary", "Scope and Objectives",
                                                "Project Timeline", "Cost estimate calculation", "Risks and Mitigations"]


def test_a_plan_without_a_budget_is_left_alone():
    plan = Plan(document_type="Minutes", title="T", audience="A", tasks=[
        {"id": 1, "title": "Overview", "tool": "write_section", "instruction": "x"},
        {"id": 2, "title": "Action items", "tool": "make_table", "instruction": "x"}])
    assert one_budget_section(plan) == plan
