"""Tests for src/detectors/idle.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta
import pandas as pd
import pytest

from src.collectors.demo import DemoCollector
from src.transforms.normalizer import normalize, NormalizedDataset
from src.detectors.idle import IdleDetector
from src.findings import Severity, Category


def _build_metric_rows(
    resource_id: str,
    project_id: str,
    metric_name: str,
    value: float,
    days: int = 7,
) -> list[dict]:
    rows = []
    start = datetime(2026, 10, 8)  # 7 days before "today" Oct 15
    for d in range(days):
        for h in range(24):
            ts = start + timedelta(days=d, hours=h)
            rows.append({
                "timestamp": ts.isoformat(),
                "resource_id": resource_id,
                "project_id": project_id,
                "metric_name": metric_name,
                "value": float(value),
            })
    return rows


def _make_dataset(metric_rows: list[dict]) -> NormalizedDataset:
    project_id = metric_rows[0]["project_id"] if metric_rows else "proj-test"
    resource_id = metric_rows[0]["resource_id"] if metric_rows else "i-test"

    hm = pd.DataFrame(metric_rows)
    hm["timestamp"] = pd.to_datetime(hm["timestamp"])
    hm["value"] = hm["value"].astype("float64")

    # Minimal daily_costs
    dc_rows = []
    for d in range(90):
        dc_rows.append({
            "date": (datetime(2026, 7, 17) + timedelta(days=d)).isoformat(),
            "project_id": project_id, "service": "Amazon EC2", "cost_usd": 50.0,
        })
    dc = pd.DataFrame(dc_rows)
    dc["date"] = pd.to_datetime(dc["date"])
    dc["cost_usd"] = dc["cost_usd"].astype("float64")

    res = pd.DataFrame([{
        "resource_id": resource_id, "project_id": project_id,
        "service": "Amazon EC2", "instance_type": "m5.xlarge",
        "region": "us-east-1", "tags": {}, "state": "running",
    }])
    bud = pd.DataFrame([{
        "project_id": project_id, "monthly_budget_usd": 5000.0,
        "period_start": pd.Timestamp("2026-10-01"),
        "period_end": pd.Timestamp("2026-10-31"),
    }])

    return NormalizedDataset(daily_costs=dc, hourly_metrics=hm, resources=res, budgets=bud)


def test_idle_cpu_flagged():
    rows = _build_metric_rows("i-idle", "proj-test", "CPUUtilization", 2.0, days=7)
    ds = _make_dataset(rows)
    findings = IdleDetector().detect(ds)
    assert any(f.resource_id == "i-idle" for f in findings)


def test_idle_cpu_severity_high():
    rows = _build_metric_rows("i-idle", "proj-test", "CPUUtilization", 2.0, days=7)
    ds = _make_dataset(rows)
    findings = IdleDetector().detect(ds)
    idle_f = [f for f in findings if f.resource_id == "i-idle"]
    assert idle_f[0].severity == Severity.HIGH


def test_busy_cpu_not_flagged():
    rows = _build_metric_rows("i-busy", "proj-test", "CPUUtilization", 80.0, days=7)
    ds = _make_dataset(rows)
    findings = IdleDetector().detect(ds)
    assert not any(f.resource_id == "i-busy" for f in findings)


def test_idle_gpu_severity_critical():
    rows = _build_metric_rows("gpu-idle", "proj-test", "GPUUtilization", 0.0, days=7)
    rows += _build_metric_rows("gpu-idle", "proj-test", "CPUUtilization", 30.0, days=7)
    ds = _make_dataset(rows)
    findings = IdleDetector().detect(ds)
    gpu_f = [f for f in findings if f.resource_id == "gpu-idle" and f.category == Category.IDLE]
    assert any(f.severity == Severity.CRITICAL for f in gpu_f)


def test_idle_category():
    rows = _build_metric_rows("i-idle", "proj-test", "CPUUtilization", 1.0, days=7)
    ds = _make_dataset(rows)
    findings = IdleDetector().detect(ds)
    for f in findings:
        assert f.category == Category.IDLE


def test_estimated_waste_positive():
    rows = _build_metric_rows("i-idle", "proj-test", "CPUUtilization", 1.0, days=7)
    ds = _make_dataset(rows)
    findings = IdleDetector().detect(ds)
    idle_f = [f for f in findings if f.resource_id == "i-idle"]
    assert idle_f[0].estimated_waste_usd > 0


def test_demo_idle_ec2_instances_detected():
    raw = DemoCollector().collect()
    ds = normalize(raw)
    findings = IdleDetector().detect(ds)
    idle_ids = {f.resource_id for f in findings}
    for i in range(1, 4):
        assert f"i-idle-ec2-{i}" in idle_ids, f"i-idle-ec2-{i} not found in findings"


def test_demo_idle_gpu_detected():
    raw = DemoCollector().collect()
    ds = normalize(raw)
    findings = IdleDetector().detect(ds)
    gpu_findings = [f for f in findings if f.resource_id == "sagemaker-gpu-idle"]
    assert len(gpu_findings) >= 1, "sagemaker-gpu-idle not found in findings"
    assert gpu_findings[0].severity == Severity.CRITICAL
