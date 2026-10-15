"""
budget.py — Budget overrun and at-risk forecast detector.

Rules
-----
OVER_BUDGET (CRITICAL):
    Actual spend in the current budget period > 100% of monthly_budget_usd.

AT_RISK (HIGH):
    Forecast full-period spend > 90% of monthly_budget_usd.

Forecast method:
    forecast = (actual_spend / elapsed_days) * total_days_in_period

Estimated waste (only for over-budget):
    actual_spend - monthly_budget_usd
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.findings import Category, Finding, Severity

_AT_RISK_THRESHOLD = 0.90   # forecast / budget ratio to flag AT_RISK
_OVER_BUDGET_THRESHOLD = 1.00


class BudgetDetector:
    """Flags projects that have exceeded or are forecast to exceed budget."""

    def __init__(
        self,
        at_risk_threshold: float = _AT_RISK_THRESHOLD,
        over_budget_threshold: float = _OVER_BUDGET_THRESHOLD,
    ) -> None:
        self.at_risk_threshold = at_risk_threshold
        self.over_budget_threshold = over_budget_threshold

    def detect(self, dataset) -> list[Finding]:
        """Run budget detection over a NormalizedDataset."""
        findings: list[Finding] = []
        dc = dataset.daily_costs
        budgets = dataset.budgets

        for _, brow in budgets.iterrows():
            pid = str(brow["project_id"])
            budget = float(brow["monthly_budget_usd"])
            period_start = pd.Timestamp(brow["period_start"])
            period_end = pd.Timestamp(brow["period_end"])

            # Filter costs within the budget period
            mask = (
                (dc["project_id"] == pid)
                & (dc["date"] >= period_start)
                & (dc["date"] <= period_end)
            )
            period_costs = dc[mask]

            if period_costs.empty:
                continue

            actual_spend = float(period_costs["cost_usd"].sum())

            # Elapsed and total days
            max_date = period_costs["date"].max()
            elapsed_days = max(1, (max_date - period_start).days + 1)
            total_days = max(1, (period_end - period_start).days + 1)
            forecast = (actual_spend / elapsed_days) * total_days

            pct_actual = actual_spend / budget
            pct_forecast = forecast / budget

            if pct_actual > self.over_budget_threshold:
                waste = actual_spend - budget
                findings.append(
                    Finding(
                        severity=Severity.CRITICAL,
                        category=Category.BUDGET,
                        project_id=pid,
                        resource_id="",
                        title=f"Budget exceeded: {pid}",
                        detail=(
                            f"Project {pid} has spent ${actual_spend:,.2f} against a "
                            f"monthly budget of ${budget:,.2f} "
                            f"({pct_actual * 100:.1f}% consumed). "
                            f"Over-spend: ${waste:,.2f}.  "
                            f"Elapsed: {elapsed_days} of {total_days} days in period."
                        ),
                        estimated_waste_usd=waste,
                        detected_at=datetime.utcnow(),
                    )
                )
            elif pct_forecast > self.at_risk_threshold:
                findings.append(
                    Finding(
                        severity=Severity.HIGH,
                        category=Category.BUDGET,
                        project_id=pid,
                        resource_id="",
                        title=f"Budget at risk: {pid}",
                        detail=(
                            f"Project {pid} has spent ${actual_spend:,.2f} so far "
                            f"({pct_actual * 100:.1f}% of ${budget:,.2f} budget). "
                            f"At current burn rate, forecast spend is ${forecast:,.2f} "
                            f"({pct_forecast * 100:.1f}% of budget) by end of period.  "
                            f"Elapsed: {elapsed_days} of {total_days} days."
                        ),
                        estimated_waste_usd=0.0,
                        detected_at=datetime.utcnow(),
                    )
                )

        return findings
