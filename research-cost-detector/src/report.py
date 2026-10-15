"""
report.py — Standalone HTML report generator.

generate_report(result, output_path, narrative) → None

Produces a self-contained HTML file with:
  • KPI header bar
  • Four Chart.js charts (daily cost line, severity doughnut, waste bar, category bar)
  • Sortable and filterable findings table with detail toggles
  • Optional Bedrock narrative section
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from src.pipeline import PipelineResult

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_TEMPLATE_NAME = "report.html.j2"

# Keep last 30 days for the line chart to avoid massive JSON
_LINE_CHART_DAYS = 30


def generate_report(
    result: "PipelineResult",
    output_path: "str | Path",
    narrative: "str | None" = None,
) -> None:
    """Generate a standalone HTML report from a PipelineResult.

    Parameters
    ----------
    result:
        Output of run_pipeline().
    output_path:
        Path to write the HTML file to.
    narrative:
        Optional plain-English text from Bedrock; inserted into the report
        when provided.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kpis = result.kpis()
    chart_data = _build_chart_data(result)
    findings_dicts = [f.to_dict() for f in result.findings]

    # Convert Finding objects to simple namespace for template access
    findings_for_template = [_FindingProxy(f) for f in result.findings]

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(_TEMPLATE_NAME)

    html = template.render(
        kpis=_DictProxy(kpis),
        findings=findings_for_template,
        chart_data_json=json.dumps(chart_data),
        bedrock_narrative=narrative,
    )

    output_path.write_text(html, encoding="utf-8")


def _build_chart_data(result: "PipelineResult") -> dict:
    """Build the JSON data structure consumed by Chart.js in the template."""
    dc = result.dataset.daily_costs.copy()
    dc["date"] = pd.to_datetime(dc["date"])

    # Filter last N days
    cutoff = dc["date"].max() - pd.Timedelta(days=_LINE_CHART_DAYS - 1)
    recent = dc[dc["date"] >= cutoff]

    # Aggregate daily total per (date, project)
    daily_proj = (
        recent.groupby(["date", "project_id"])["cost_usd"]
        .sum()
        .reset_index()
        .sort_values("date")
    )

    all_dates = sorted(daily_proj["date"].dt.strftime("%Y-%m-%d").unique().tolist())
    projects = sorted(daily_proj["project_id"].unique().tolist())

    # Build per-project cost series (aligned to all_dates)
    date_to_idx = {d: i for i, d in enumerate(all_dates)}
    costs_by_project: dict[str, list[float]] = {}
    for proj in projects:
        series = [0.0] * len(all_dates)
        proj_data = daily_proj[daily_proj["project_id"] == proj]
        for _, row in proj_data.iterrows():
            d = row["date"].strftime("%Y-%m-%d")
            series[date_to_idx[d]] = round(float(row["cost_usd"]), 2)
        costs_by_project[proj] = series

    # Severity counts
    severity_counts = {
        "CRITICAL": result.kpis()["critical_count"],
        "HIGH":     result.kpis()["high_count"],
        "MEDIUM":   result.kpis()["medium_count"],
        "LOW":      result.kpis()["low_count"],
    }

    # Waste by category
    waste_by_category: dict[str, float] = {}
    for f in result.findings:
        waste_by_category[f.category.value] = round(
            waste_by_category.get(f.category.value, 0.0) + f.estimated_waste_usd, 2
        )

    # Category counts
    category_counts = {
        "ANOMALY": result.kpis()["anomaly_count"],
        "IDLE":    result.kpis()["idle_count"],
        "TAGGING": result.kpis()["tagging_count"],
        "BUDGET":  result.kpis()["budget_count"],
    }

    return {
        "daily_dates":             all_dates,
        "daily_projects":          projects,
        "daily_costs_by_project":  costs_by_project,
        "severity_counts":         severity_counts,
        "waste_by_category":       waste_by_category,
        "category_counts":         category_counts,
    }


class _DictProxy:
    """Allows template to access dict keys as attributes (kpis.total_spend_usd)."""

    def __init__(self, d: dict) -> None:
        self.__dict__.update(d)


class _FindingProxy:
    """Thin wrapper around a Finding dict for template attribute access."""

    def __init__(self, finding) -> None:
        d = finding.to_dict()
        self.__dict__.update(d)
