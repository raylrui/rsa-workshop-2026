"""Tests for src/collectors/demo.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collectors.demo import DemoCollector


def _collect():
    return DemoCollector().collect()


def test_raw_keys_present():
    d = _collect()
    assert set(d.keys()) == {"projects", "resources", "daily_costs", "hourly_metrics"}


def test_exactly_10_projects():
    d = _collect()
    assert len(d["projects"]) == 10


def test_at_least_50_resources():
    d = _collect()
    assert len(d["resources"]) >= 50


def test_daily_cost_series_length():
    """Each (project, service) pair should have 90 rows → 10 projects × 5 services × 90 days."""
    d = _collect()
    # Quick check: total rows = 10 * 5 * 90
    assert len(d["daily_costs"]) == 10 * 5 * 90


def test_daily_cost_row_schema():
    d = _collect()
    row = d["daily_costs"][0]
    assert {"date", "project_id", "service", "cost_usd"} <= set(row.keys())
    assert row["cost_usd"] >= 0


def test_hourly_metrics_168_points_per_compute_resource():
    """Each EC2 / SageMaker resource must have exactly 168 CPU data points."""
    d = _collect()
    from collections import Counter
    cpu_counts = Counter(
        r["resource_id"]
        for r in d["hourly_metrics"]
        if r["metric_name"] == "CPUUtilization"
    )
    # All compute resources should have exactly 168 hourly CPU readings
    for rid, count in cpu_counts.items():
        assert count == 168, f"{rid} has {count} CPU readings, expected 168"


def test_deterministic_output():
    d1 = DemoCollector(seed=42).collect()
    d2 = DemoCollector(seed=42).collect()
    # Check a few values are identical
    assert d1["daily_costs"][0]["cost_usd"] == d2["daily_costs"][0]["cost_usd"]
    assert len(d1["resources"]) == len(d2["resources"])


def test_different_seed_gives_different_costs():
    d1 = DemoCollector(seed=42).collect()
    d2 = DemoCollector(seed=99).collect()
    costs1 = [r["cost_usd"] for r in d1["daily_costs"]]
    costs2 = [r["cost_usd"] for r in d2["daily_costs"]]
    assert costs1 != costs2


def test_idle_cpu_resources_present():
    """Verify the 3 injected idle EC2 resources exist."""
    d = _collect()
    idle_ids = {r["resource_id"] for r in d["resources"] if r["resource_id"].startswith("i-idle-ec2-")}
    assert len(idle_ids) == 3


def test_idle_gpu_resource_present():
    """Verify the injected idle GPU SageMaker resource exists."""
    d = _collect()
    idle_gpu = [r for r in d["resources"] if r["resource_id"] == "sagemaker-gpu-idle"]
    assert len(idle_gpu) == 1


def test_idle_cpu_metrics_below_5_percent():
    """The 3 idle EC2 instances must have CPU < 5% for all 168 hours."""
    d = _collect()
    for rid in ["i-idle-ec2-1", "i-idle-ec2-2", "i-idle-ec2-3"]:
        cpu_vals = [
            r["value"]
            for r in d["hourly_metrics"]
            if r["resource_id"] == rid and r["metric_name"] == "CPUUtilization"
        ]
        assert len(cpu_vals) == 168
        assert all(v < 5.0 for v in cpu_vals), f"{rid} has CPU ≥ 5%: {max(cpu_vals):.2f}"


def test_idle_gpu_metrics_zero():
    """The idle GPU SageMaker resource must have GPUUtilization = 0 for all hours."""
    d = _collect()
    gpu_vals = [
        r["value"]
        for r in d["hourly_metrics"]
        if r["resource_id"] == "sagemaker-gpu-idle" and r["metric_name"] == "GPUUtilization"
    ]
    assert len(gpu_vals) == 168
    assert all(v == 0.0 for v in gpu_vals)


def test_ml_training_spike_on_day_75():
    """proj-ml-training must have a 5× spike on day index 74 (0-based)."""
    d = _collect()
    from collections import defaultdict
    import datetime

    project_daily = defaultdict(float)
    for row in d["daily_costs"]:
        if row["project_id"] == "proj-ml-training":
            project_daily[row["date"]] += row["cost_usd"]

    sorted_dates = sorted(project_daily.keys())
    spike_date = sorted_dates[74]
    spike_cost = project_daily[spike_date]

    # Normal days should be ~350; spike should be ~1750 (5×)
    normal_costs = [project_daily[d] for i, d in enumerate(sorted_dates) if i not in (74,)]
    avg_normal = sum(normal_costs) / len(normal_costs)
    assert spike_cost > avg_normal * 3.0, f"Spike too small: {spike_cost:.2f} vs avg {avg_normal:.2f}"


def test_untagged_resources_present():
    """At least 8 resources must be missing at least one required tag."""
    d = _collect()
    required = {"CostCentre", "ProjectID", "Owner"}
    missing_count = sum(
        1 for r in d["resources"]
        if required - set(r["tags"].keys())
    )
    assert missing_count >= 8, f"Only {missing_count} under-tagged resources found"


def test_project_budget_fields():
    d = _collect()
    for proj in d["projects"]:
        assert "project_id" in proj
        assert "monthly_budget_usd" in proj
        assert "period_start" in proj
        assert "period_end" in proj
        assert proj["monthly_budget_usd"] > 0
