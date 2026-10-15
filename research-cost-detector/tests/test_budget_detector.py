"""Tests for src/detectors/budget.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
import pandas as pd
import pytest

from src.collectors.demo import DemoCollector
from src.transforms.normalizer import normalize, NormalizedDataset
from src.detectors.budget import BudgetDetector
from src.findings import Severity, Category


def _make_dataset(
    project_id: str,
    daily_spend: float,
    days_elapsed: int,
    monthly_budget: float,
    period_days: int = 31,
) -> NormalizedDataset:
    period_start = datetime(2026, 10, 1)
    period_end = datetime(2026, 10, 31)
    rows = []
    for d in range(days_elapsed):
        rows.append({
            "date": (period_start + timedelta(days=d)).isoformat(),
            "project_id": project_id,
            "service": "Amazon EC2",
            "cost_usd": daily_spend,
        })

    dc = pd.DataFrame(rows)
    dc["date"] = pd.to_datetime(dc["date"])
    dc["cost_usd"] = dc["cost_usd"].astype("float64")

    hm = pd.DataFrame(columns=["timestamp", "resource_id", "project_id", "metric_name", "value"])
    hm["timestamp"] = pd.to_datetime(hm["timestamp"])
    hm["value"] = hm["value"].astype("float64")

    res = pd.DataFrame([{
        "resource_id": "i-test", "project_id": project_id,
        "service": "Amazon EC2", "instance_type": "m5.xlarge",
        "region": "us-east-1", "tags": {}, "state": "running",
    }])

    bud = pd.DataFrame([{
        "project_id": project_id,
        "monthly_budget_usd": monthly_budget,
        "period_start": pd.Timestamp(period_start),
        "period_end": pd.Timestamp(period_end),
    }])

    return NormalizedDataset(daily_costs=dc, hourly_metrics=hm, resources=res, budgets=bud)


def test_over_budget_detected():
    """Spending $110/day for 10 days against a $500 budget = $1100 > $500."""
    ds = _make_dataset("proj-over", daily_spend=110.0, days_elapsed=10, monthly_budget=500.0)
    findings = BudgetDetector().detect(ds)
    over = [f for f in findings if "exceeded" in f.title.lower() or "Budget exceeded" in f.title]
    assert len(over) >= 1


def test_over_budget_severity_critical():
    ds = _make_dataset("proj-over", daily_spend=110.0, days_elapsed=10, monthly_budget=500.0)
    findings = BudgetDetector().detect(ds)
    critical = [f for f in findings if f.severity == Severity.CRITICAL]
    assert len(critical) >= 1


def test_over_budget_waste_positive():
    ds = _make_dataset("proj-over", daily_spend=110.0, days_elapsed=10, monthly_budget=500.0)
    findings = BudgetDetector().detect(ds)
    for f in findings:
        if f.severity == Severity.CRITICAL:
            assert f.estimated_waste_usd > 0


def test_at_risk_detected():
    """$40/day for 10 days = $400; forecast for 31-day month = $1240; budget = $1300 → 95.4% → AT_RISK."""
    ds = _make_dataset("proj-risk", daily_spend=40.0, days_elapsed=10, monthly_budget=1300.0)
    findings = BudgetDetector().detect(ds)
    at_risk = [f for f in findings if f.severity == Severity.HIGH and f.category == Category.BUDGET]
    assert len(at_risk) >= 1


def test_at_risk_severity_high():
    ds = _make_dataset("proj-risk", daily_spend=40.0, days_elapsed=10, monthly_budget=1300.0)
    findings = BudgetDetector().detect(ds)
    high = [f for f in findings if f.severity == Severity.HIGH]
    assert len(high) >= 1


def test_on_track_no_finding():
    """$10/day for 10 days = $100; forecast = $310; budget = $5000 → well under."""
    ds = _make_dataset("proj-ok", daily_spend=10.0, days_elapsed=10, monthly_budget=5000.0)
    findings = BudgetDetector().detect(ds)
    assert findings == []


def test_category_is_budget():
    ds = _make_dataset("proj-over", daily_spend=110.0, days_elapsed=10, monthly_budget=500.0)
    findings = BudgetDetector().detect(ds)
    for f in findings:
        assert f.category == Category.BUDGET


def test_demo_climate_over_budget():
    """proj-climate is injected to be 20% over budget."""
    raw = DemoCollector().collect()
    ds = normalize(raw)
    findings = BudgetDetector().detect(ds)
    climate_critical = [
        f for f in findings
        if f.project_id == "proj-climate" and f.severity == Severity.CRITICAL
    ]
    assert len(climate_critical) >= 1, "proj-climate should be CRITICAL (over budget)"


def test_demo_bioinformatics_at_risk():
    """proj-bioinformatics is injected to forecast > 90% budget."""
    raw = DemoCollector().collect()
    ds = normalize(raw)
    findings = BudgetDetector().detect(ds)
    bio = [f for f in findings if f.project_id == "proj-bioinformatics"]
    assert len(bio) >= 1, "proj-bioinformatics should have a budget finding"
