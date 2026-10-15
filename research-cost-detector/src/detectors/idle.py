"""
idle.py — Idle compute and GPU resource detector.

Rules
-----
CPU idle (HIGH):
    Mean CPUUtilization < CPU_THRESHOLD (10%) for ≥ CPU_MIN_DAYS (5) consecutive days.

GPU idle (CRITICAL):
    Mean GPUUtilization < GPU_THRESHOLD (5%) for ≥ GPU_MIN_DAYS (3) consecutive days.
    GPU instances are expensive, so this has higher severity.

Estimated waste:
    Sum of daily cost for the resource over the idle period.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.findings import Category, Finding, Severity

CPU_THRESHOLD = 10.0    # percent
GPU_THRESHOLD = 5.0     # percent
CPU_MIN_DAYS = 5        # consecutive days below threshold
GPU_MIN_DAYS = 3        # consecutive days below threshold


def _consecutive_days_below(daily_mean: pd.Series, threshold: float) -> int:
    """Return the maximum consecutive-day run where value < threshold."""
    max_run = current_run = 0
    for val in daily_mean:
        if val < threshold:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run


class IdleDetector:
    """Flags compute and GPU resources that are consistently under-utilised."""

    def __init__(
        self,
        cpu_threshold: float = CPU_THRESHOLD,
        gpu_threshold: float = GPU_THRESHOLD,
        cpu_min_days: int = CPU_MIN_DAYS,
        gpu_min_days: int = GPU_MIN_DAYS,
    ) -> None:
        self.cpu_threshold = cpu_threshold
        self.gpu_threshold = gpu_threshold
        self.cpu_min_days = cpu_min_days
        self.gpu_min_days = gpu_min_days

    def detect(self, dataset) -> list[Finding]:
        """Run idle detection over a NormalizedDataset."""
        findings: list[Finding] = []

        hm = dataset.hourly_metrics.copy()
        # Build daily mean per (resource_id, metric_name)
        hm["day"] = hm["timestamp"].dt.normalize()
        daily_mean = (
            hm.groupby(["resource_id", "project_id", "metric_name", "day"])["value"]
            .mean()
            .reset_index()
        )

        # ── CPU idle ─────────────────────────────────────────────────────────
        cpu_data = daily_mean[daily_mean["metric_name"] == "CPUUtilization"]
        for (rid, pid), group in cpu_data.groupby(["resource_id", "project_id"]):
            group = group.sort_values("day")
            daily_series = group.set_index("day")["value"]

            run = _consecutive_days_below(daily_series, self.cpu_threshold)
            if run < self.cpu_min_days:
                continue

            waste = self._estimate_waste(dataset, rid, pid, run)
            findings.append(
                Finding(
                    severity=Severity.HIGH,
                    category=Category.IDLE,
                    project_id=str(pid),
                    resource_id=str(rid),
                    title=f"Idle compute resource: {rid}",
                    detail=(
                        f"CPU utilization has been below {self.cpu_threshold}% "
                        f"for {run} consecutive days. "
                        f"Mean daily CPU: {daily_series.mean():.1f}%.  "
                        f"Consider stopping or rightsizing this instance."
                    ),
                    estimated_waste_usd=waste,
                    detected_at=datetime.utcnow(),
                )
            )

        # ── GPU idle ─────────────────────────────────────────────────────────
        gpu_data = daily_mean[daily_mean["metric_name"] == "GPUUtilization"]
        for (rid, pid), group in gpu_data.groupby(["resource_id", "project_id"]):
            group = group.sort_values("day")
            daily_series = group.set_index("day")["value"]

            run = _consecutive_days_below(daily_series, self.gpu_threshold)
            if run < self.gpu_min_days:
                continue

            waste = self._estimate_waste(dataset, rid, pid, run)
            findings.append(
                Finding(
                    severity=Severity.CRITICAL,
                    category=Category.IDLE,
                    project_id=str(pid),
                    resource_id=str(rid),
                    title=f"Idle GPU resource: {rid}",
                    detail=(
                        f"GPU utilization has been below {self.gpu_threshold}% "
                        f"for {run} consecutive days on a GPU-class instance. "
                        f"GPU instances are expensive — this is high-priority waste.  "
                        f"Consider stopping, changing to a CPU instance, or validating "
                        f"the workload is actually using the GPU."
                    ),
                    estimated_waste_usd=waste,
                    detected_at=datetime.utcnow(),
                )
            )

        return findings

    def _estimate_waste(
        self,
        dataset,
        resource_id: str,
        project_id: str,
        idle_days: int,
    ) -> float:
        """Approximate daily resource cost × idle_days as waste estimate."""
        dc = dataset.daily_costs
        proj_costs = dc[dc["project_id"] == project_id]["cost_usd"]

        if proj_costs.empty:
            return 0.0

        # Resource share: assume uniform distribution across resources in project
        res_in_proj = dataset.resources[dataset.resources["project_id"] == project_id]
        n_resources = max(1, len(res_in_proj))
        avg_daily_proj = proj_costs.sum() / max(1, dc[dc["project_id"] == project_id]["date"].nunique())
        avg_daily_resource = avg_daily_proj / n_resources

        return round(avg_daily_resource * idle_days, 2)
