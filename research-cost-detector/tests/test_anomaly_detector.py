"""Tests for src/detectors/anomaly.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
import pandas as pd
import pytest

from src.collectors.demo import DemoCollector
from src.transforms.normalizer import normalize, NormalizedDataset
from src.detectors.anomaly import AnomalyDetector
from src.findings import Severity, Category


def _make_dataset_with_spike(spike_multiplier: float = 10.0) -> NormalizedDataset:
    """Minimal dataset: one project, 30 days of stable cost + one big spike."""
    base_cost_per_service = 100.0
    services = ["Amazon EC2"]
    project_id = "proj-test"
    rows = []
    start = datetime(2026, 9, 1)

    for day in range(30):
        cost = base_cost_per_service
        if day == 25:
            cost = base_cost_per_service * spike_multiplier
        rows.append({"date": (start + timedelta(days=day)).isoformat(),
                     "project_id": project_id, "service": "Amazon EC2", "cost_usd": cost})

    dc = pd.DataFrame(rows)
    dc["date"] = pd.to_datetime(dc["date"])
    dc["cost_usd"] = dc["cost_usd"].astype("float64")

    # Minimal other frames
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
        "monthly_budget_usd": 10000.0,
        "period_start": pd.Timestamp("2026-09-01"),
        "period_end": pd.Timestamp("2026-09-30"),
    }])

    return NormalizedDataset(daily_costs=dc, hourly_metrics=hm, resources=res, budgets=bud)


def test_spike_detected():
    ds = _make_dataset_with_spike(spike_multiplier=10.0)
    findings = AnomalyDetector().detect(ds)
    assert len(findings) >= 1
    titles = [f.title for f in findings]
    assert any("proj-test" in t for t in titles)


def test_spike_severity_critical():
    ds = _make_dataset_with_spike(spike_multiplier=10.0)
    findings = AnomalyDetector().detect(ds)
    # 10× spike should be CRITICAL (z > 5)
    assert any(f.severity == Severity.CRITICAL for f in findings)


def test_no_findings_for_flat_series():
    ds = _make_dataset_with_spike(spike_multiplier=1.0)  # no spike
    findings = AnomalyDetector().detect(ds)
    assert findings == []


def test_estimated_waste_positive():
    ds = _make_dataset_with_spike(spike_multiplier=10.0)
    findings = AnomalyDetector().detect(ds)
    for f in findings:
        assert f.estimated_waste_usd > 0


def test_category_is_anomaly():
    ds = _make_dataset_with_spike(spike_multiplier=10.0)
    findings = AnomalyDetector().detect(ds)
    for f in findings:
        assert f.category == Category.ANOMALY


def test_demo_ml_training_spike_detected():
    """The injected 5× spike in proj-ml-training must be flagged."""
    raw = DemoCollector().collect()
    ds = normalize(raw)
    findings = AnomalyDetector().detect(ds)
    ml_findings = [f for f in findings if f.project_id == "proj-ml-training"]
    assert len(ml_findings) >= 1, "No anomaly found for proj-ml-training"


def test_demo_ml_training_spike_is_critical():
    raw = DemoCollector().collect()
    ds = normalize(raw)
    findings = AnomalyDetector().detect(ds)
    ml_critical = [
        f for f in findings
        if f.project_id == "proj-ml-training" and f.severity == Severity.CRITICAL
    ]
    assert len(ml_critical) >= 1, "Expected CRITICAL anomaly for proj-ml-training"


def test_configurable_threshold():
    """A very high threshold should suppress findings."""
    ds = _make_dataset_with_spike(spike_multiplier=5.0)
    findings = AnomalyDetector(threshold=100.0).detect(ds)
    assert findings == []
