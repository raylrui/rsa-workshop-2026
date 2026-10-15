"""
anomaly.py — Cost anomaly detector using a rolling z-score.

Algorithm
---------
For each project, aggregate daily total cost from daily_costs, then compute a
7-day rolling mean and standard deviation.  A day is flagged when its
z-score exceeds the threshold (default 3.0).

    z = (cost - rolling_mean) / rolling_std

Severity mapping:
    z > 5  →  CRITICAL
    z > 3  →  HIGH
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.findings import Category, Finding, Severity

# Default rolling window (days)
_WINDOW = 7
# z-score threshold to flag an anomaly
_THRESHOLD = 3.0
# Minimum number of non-NaN observations in the window before flagging
_MIN_PERIODS = 3


class AnomalyDetector:
    """Detects statistically unusual daily cost increases per project."""

    def __init__(
        self,
        window: int = _WINDOW,
        threshold: float = _THRESHOLD,
    ) -> None:
        self.window = window
        self.threshold = threshold

    def detect(self, dataset) -> list[Finding]:
        """Run detection over a NormalizedDataset.

        Parameters
        ----------
        dataset:
            A NormalizedDataset instance.

        Returns
        -------
        list[Finding]
        """
        findings: list[Finding] = []
        dc = dataset.daily_costs.copy()

        # Aggregate all services into a single daily total per project
        daily = (
            dc.groupby(["project_id", "date"])["cost_usd"]
            .sum()
            .reset_index()
            .sort_values(["project_id", "date"])
        )

        for project_id, group in daily.groupby("project_id"):
            group = group.set_index("date").sort_index()
            series = group["cost_usd"]

            # Shift by 1 so the rolling stats are computed on the PRIOR window,
            # excluding the current day.  This prevents the spike from inflating
            # its own mean/std, making extreme values detectable.
            shifted = series.shift(1)
            rolling_mean = shifted.rolling(window=self.window, min_periods=_MIN_PERIODS).mean()
            rolling_std = shifted.rolling(window=self.window, min_periods=_MIN_PERIODS).std()

            # Avoid divide-by-zero: skip days with zero std
            for date, cost in series.items():
                mean = rolling_mean.get(date)
                std = rolling_std.get(date)

                if mean is None or std is None or pd.isna(mean) or pd.isna(std):
                    continue
                if pd.isna(mean) or mean < 1e-6:
                    continue

                if std < 1e-6:
                    # Flat baseline: use a ratio fallback — flag if cost > threshold × mean
                    ratio = cost / mean
                    if ratio <= self.threshold:
                        continue
                    # Map ratio to a synthetic z-score for severity
                    z = ratio  # ratio of 5 → treated as z=5
                else:
                    z = (cost - mean) / std
                    if z <= self.threshold:
                        continue

                severity = Severity.CRITICAL if z > 5.0 else Severity.HIGH
                excess = max(0.0, cost - mean)

                # Use date as string for finding_id stability
                date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)

                findings.append(
                    Finding(
                        severity=severity,
                        category=Category.ANOMALY,
                        project_id=str(project_id),
                        resource_id="",
                        title=f"Cost anomaly on {date_str} for {project_id}",
                        detail=(
                            f"Daily spend of ${cost:,.2f} is {z:.1f}σ above the "
                            f"{self.window}-day rolling mean of ${mean:,.2f} "
                            f"(σ={std:,.2f}).  Excess spend: ${excess:,.2f}."
                        ),
                        estimated_waste_usd=excess,
                        detected_at=datetime.utcnow(),
                    )
                )

        return findings
