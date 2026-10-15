"""
normalizer.py — Transforms raw collector output into a stable NormalizedDataset.

The NormalizedDataset is the contract between collectors and detectors.
Detectors never import from collectors; they only ever see NormalizedDataset.

Expected raw dict keys (produced by any AbstractCollector):
    "projects"      list[dict]  — project metadata & budgets
    "resources"     list[dict]  — resource inventory
    "daily_costs"   list[dict]  — one row per (date, project_id, service)
    "hourly_metrics" list[dict] — one row per (timestamp, resource_id, metric_name)

DataFrame column contracts
--------------------------
daily_costs:
    date            datetime64[ns]   — UTC midnight
    project_id      str
    service         str              — e.g. "Amazon EC2"
    cost_usd        float64

hourly_metrics:
    timestamp       datetime64[ns]   — UTC, hourly
    resource_id     str
    project_id      str
    metric_name     str              — e.g. "CPUUtilization", "GPUUtilization"
    value           float64

resources:
    resource_id     str
    project_id      str
    service         str
    instance_type   str
    region          str
    tags            object           — Python dict
    state           str              — e.g. "running", "stopped"

budgets:
    project_id          str
    monthly_budget_usd  float64
    period_start        datetime64[ns]
    period_end          datetime64[ns]
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


# ---------------------------------------------------------------------------
# Schema definitions (column → dtype) used for validation
# ---------------------------------------------------------------------------

_DAILY_COSTS_COLS: dict[str, str] = {
    "date": "datetime64[ns]",
    "project_id": "object",
    "service": "object",
    "cost_usd": "float64",
}

_HOURLY_METRICS_COLS: dict[str, str] = {
    "timestamp": "datetime64[ns]",
    "resource_id": "object",
    "project_id": "object",
    "metric_name": "object",
    "value": "float64",
}

_RESOURCES_COLS: dict[str, str] = {
    "resource_id": "object",
    "project_id": "object",
    "service": "object",
    "instance_type": "object",
    "region": "object",
    "tags": "object",
    "state": "object",
}

_BUDGETS_COLS: dict[str, str] = {
    "project_id": "object",
    "monthly_budget_usd": "float64",
    "period_start": "datetime64[ns]",
    "period_end": "datetime64[ns]",
}


@dataclass
class NormalizedDataset:
    """The normalised representation of all collected data.

    Instances of this class are passed to every detector.
    """

    daily_costs: pd.DataFrame
    hourly_metrics: pd.DataFrame
    resources: pd.DataFrame
    budgets: pd.DataFrame

    def __post_init__(self) -> None:
        _validate_frame(self.daily_costs, _DAILY_COSTS_COLS, "daily_costs")
        _validate_frame(self.hourly_metrics, _HOURLY_METRICS_COLS, "hourly_metrics")
        _validate_frame(self.resources, _RESOURCES_COLS, "resources")
        _validate_frame(self.budgets, _BUDGETS_COLS, "budgets")


def _validate_frame(
    df: pd.DataFrame,
    required_cols: dict[str, str],
    name: str,
) -> None:
    """Raise ValueError if required columns are missing."""
    missing = set(required_cols.keys()) - set(df.columns)
    if missing:
        raise ValueError(
            f"NormalizedDataset.{name} is missing required columns: {sorted(missing)}"
        )


def normalize(raw: dict) -> NormalizedDataset:
    """Transform a raw collector dict into a NormalizedDataset.

    Parameters
    ----------
    raw:
        Output of any AbstractCollector.collect().

    Returns
    -------
    NormalizedDataset
    """
    for key in ("projects", "resources", "daily_costs", "hourly_metrics"):
        if key not in raw:
            raise ValueError(f"Raw data is missing required key: '{key}'")

    # ------------------------------------------------------------------ #
    # daily_costs                                                          #
    # ------------------------------------------------------------------ #
    dc = pd.DataFrame(raw["daily_costs"])
    dc["date"] = pd.to_datetime(dc["date"], utc=False).dt.normalize()
    dc["cost_usd"] = dc["cost_usd"].astype("float64")
    dc["project_id"] = dc["project_id"].astype(str)
    dc["service"] = dc["service"].astype(str)
    dc = dc[list(_DAILY_COSTS_COLS.keys())]

    # ------------------------------------------------------------------ #
    # hourly_metrics                                                       #
    # ------------------------------------------------------------------ #
    if raw["hourly_metrics"]:
        hm = pd.DataFrame(raw["hourly_metrics"])
        hm["timestamp"] = pd.to_datetime(hm["timestamp"], utc=False)
        hm["value"] = hm["value"].astype("float64")
        hm["resource_id"] = hm["resource_id"].astype(str)
        hm["project_id"] = hm["project_id"].astype(str)
        hm["metric_name"] = hm["metric_name"].astype(str)
        hm = hm[list(_HOURLY_METRICS_COLS.keys())]
    else:
        hm = pd.DataFrame(columns=list(_HOURLY_METRICS_COLS.keys()))
        hm["timestamp"] = pd.to_datetime(hm["timestamp"])
        hm["value"] = hm["value"].astype("float64")

    # ------------------------------------------------------------------ #
    # resources                                                            #
    # ------------------------------------------------------------------ #
    res = pd.DataFrame(raw["resources"])
    for col in ("resource_id", "project_id", "service", "instance_type", "region", "state"):
        res[col] = res[col].astype(str)
    if "tags" not in res.columns:
        res["tags"] = [{}] * len(res)
    res = res[list(_RESOURCES_COLS.keys())]

    # ------------------------------------------------------------------ #
    # budgets — derived from projects list                                 #
    # ------------------------------------------------------------------ #
    budgets_rows = []
    for proj in raw["projects"]:
        budgets_rows.append(
            {
                "project_id": proj["project_id"],
                "monthly_budget_usd": float(proj["monthly_budget_usd"]),
                "period_start": pd.to_datetime(proj["period_start"]),
                "period_end": pd.to_datetime(proj["period_end"]),
            }
        )
    bud = pd.DataFrame(budgets_rows)
    bud["period_start"] = pd.to_datetime(bud["period_start"])
    bud["period_end"] = pd.to_datetime(bud["period_end"])

    return NormalizedDataset(
        daily_costs=dc,
        hourly_metrics=hm,
        resources=res,
        budgets=bud,
    )
