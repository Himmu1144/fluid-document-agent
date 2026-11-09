from app import tools
from app.models import Task


def test_rupees_use_indian_grouping_and_keep_paise_on_small_rates():
    assert [tools._inr(v) for v in (0.6, 999, 123456, 1234567)] == ["₹0.60", "₹999", "₹1,23,456", "₹12,34,567"]


def test_calculate_lets_python_do_the_sums_and_checks_the_budget(monkeypatch):
    estimate = tools._Estimate(heading="Cost", text="Basis.", budget_limit_inr=500000, contingency_percent=10, items=[
        tools.LineItem(item="Engineering", quantity=20, unit="days", unit_cost_inr=9000),
        tools.LineItem(item="Speech", quantity=100000, unit="minutes", unit_cost_inr=1.4)])
    monkeypatch.setattr(tools, "complete_json", lambda *a, **k: estimate)
    section = tools.calculate(Task(id=1, title="Cost", tool="calculate", instruction="x"), "ctx")
    assert section.table.rows[-1] == ["Total", "", "", "₹3,52,000"]   # (1,80,000 + 1,40,000) × 1.10
    assert "within the stated budget" in section.text


def test_a_contingency_line_from_the_model_is_dropped_so_it_is_not_counted_twice(monkeypatch):
    # From a rehearsal run: the model added "Contingency (10%)" worth ₹1,70,000 as an item, and Python added 10% on top.
    estimate = tools._Estimate(heading="Budget", text="Basis.", budget_limit_inr=500000, contingency_percent=10, items=[
        tools.LineItem(item="Engineering", quantity=20, unit="days", unit_cost_inr=9000),
        tools.LineItem(item="Contingency (10%)", quantity=1, unit="lump_sum", unit_cost_inr=170000)])
    monkeypatch.setattr(tools, "complete_json", lambda *a, **k: estimate)
    section = tools.calculate(Task(id=1, title="Budget", tool="calculate", instruction="x"), "ctx")
    assert [r[0] for r in section.table.rows] == ["Engineering", "Contingency (10%)", "Total"]
    assert section.table.rows[-1][-1] == "₹1,98,000"   # 1,80,000 × 1.10


def test_lookup_matches_the_request_not_only_the_task_title():
    found = tools.lookup_mock_data(Task(id=1, title="Resource lookup", tool="lookup_mock_data", instruction="records"),
                                   "Proposal for a voice bot for our claims line")
    assert "Existing voice AI platform" in found and "Insurance claims line: current state" in found


def test_a_total_written_by_the_model_is_removed_and_only_pythons_total_remains(monkeypatch):
    estimate = tools._Estimate(heading="Budget", text="The total estimated cost of ₹2,72,600 covers the team. "
                               "Telephony at ₹0.60 per minute is excluded.", budget_limit_inr=500000, items=[
        tools.LineItem(item="Engineering", quantity=10, unit="days", unit_cost_inr=9000)])
    monkeypatch.setattr(tools, "complete_json", lambda *a, **k: estimate)
    text = tools.calculate(Task(id=1, title="Budget", tool="calculate", instruction="x"), "ctx").text
    assert "2,72,600" not in text and "₹0.60 per minute" in text and "The total of ₹90,000 is within" in text
