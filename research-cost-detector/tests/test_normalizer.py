"""Tests for src/transforms/normalizer.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytest
from src.collectors.demo import DemoCollector
from src.transforms.normalizer import normalize, NormalizedDataset


@pytest.fixture(scope="module")
def dataset() -> NormalizedDataset:
    raw = DemoCollector().collect()
    return normalize(raw)


def test_returns_normalized_dataset(dataset):
    assert isinstance(dataset, NormalizedDataset)


# ── daily_costs ──────────────────────────────────────────────────────────────

def test_daily_costs_required_columns(dataset):
    expected = {"date", "project_id", "service", "cost_usd"}
    assert expected <= set(dataset.daily_costs.columns)


def test_daily_costs_no_null_project_id(dataset):
    assert dataset.daily_costs["project_id"].notna().all()


def test_daily_costs_date_is_datetime(dataset):
    assert pd.api.types.is_datetime64_any_dtype(dataset.daily_costs["date"])


def test_daily_costs_cost_usd_non_negative(dataset):
    assert (dataset.daily_costs["cost_usd"] >= 0).all()


def test_daily_costs_shape(dataset):
    # 10 projects × 5 services × 90 days
    assert len(dataset.daily_costs) == 10 * 5 * 90


# ── hourly_metrics ───────────────────────────────────────────────────────────

def test_hourly_metrics_required_columns(dataset):
    expected = {"timestamp", "resource_id", "project_id", "metric_name", "value"}
    assert expected <= set(dataset.hourly_metrics.columns)


def test_hourly_metrics_no_null_resource_id(dataset):
    assert dataset.hourly_metrics["resource_id"].notna().all()


def test_hourly_metrics_timestamp_is_datetime(dataset):
    assert pd.api.types.is_datetime64_any_dtype(dataset.hourly_metrics["timestamp"])


def test_hourly_metrics_metric_names(dataset):
    valid_metrics = {"CPUUtilization", "GPUUtilization"}
    assert set(dataset.hourly_metrics["metric_name"].unique()) <= valid_metrics


# ── resources ────────────────────────────────────────────────────────────────

def test_resources_required_columns(dataset):
    expected = {"resource_id", "project_id", "service", "instance_type", "region", "tags", "state"}
    assert expected <= set(dataset.resources.columns)


def test_resources_no_null_project_id(dataset):
    assert dataset.resources["project_id"].notna().all()


def test_resources_tags_are_dicts(dataset):
    for tags in dataset.resources["tags"]:
        assert isinstance(tags, dict)


def test_resources_at_least_50(dataset):
    assert len(dataset.resources) >= 50


# ── budgets ──────────────────────────────────────────────────────────────────

def test_budgets_required_columns(dataset):
    expected = {"project_id", "monthly_budget_usd", "period_start", "period_end"}
    assert expected <= set(dataset.budgets.columns)


def test_budgets_10_projects(dataset):
    assert len(dataset.budgets) == 10


def test_budgets_period_start_is_datetime(dataset):
    assert pd.api.types.is_datetime64_any_dtype(dataset.budgets["period_start"])


def test_budgets_all_positive(dataset):
    assert (dataset.budgets["monthly_budget_usd"] > 0).all()


# ── validation errors ────────────────────────────────────────────────────────

def test_normalize_raises_on_missing_key():
    with pytest.raises(ValueError, match="missing required key"):
        normalize({"projects": [], "resources": [], "daily_costs": []})
        # missing "hourly_metrics"


def test_normalize_raises_on_empty_resources_missing_columns():
    """Passing a resources list with wrong keys should propagate a normalizer error."""
    raw = DemoCollector().collect()
    # corrupt the resources list
    raw["resources"] = [{"bad_field": 1}]
    with pytest.raises((ValueError, KeyError)):
        normalize(raw)
