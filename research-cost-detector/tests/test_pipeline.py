"""Tests for src/pipeline.py"""
import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.pipeline import PipelineConfig, PipelineResult, run_pipeline
from src.findings import Category


@pytest.fixture(scope="module")
def result(tmp_path_factory) -> PipelineResult:
    output_dir = tmp_path_factory.mktemp("pipeline_output")
    config = PipelineConfig(mode="demo", output_dir=output_dir)
    return run_pipeline(mode="demo", config=config)


def test_pipeline_returns_result(result):
    assert isinstance(result, PipelineResult)


def test_findings_json_written(tmp_path):
    config = PipelineConfig(mode="demo", output_dir=tmp_path)
    run_pipeline(mode="demo", config=config)
    findings_path = tmp_path / "findings.json"
    assert findings_path.exists(), "findings.json not written"


def test_findings_json_valid(tmp_path):
    config = PipelineConfig(mode="demo", output_dir=tmp_path)
    run_pipeline(mode="demo", config=config)
    raw = (tmp_path / "findings.json").read_text()
    parsed = json.loads(raw)
    assert isinstance(parsed, list)
    assert len(parsed) > 0


def test_findings_json_schema(tmp_path):
    """Each finding in JSON must have all required fields."""
    config = PipelineConfig(mode="demo", output_dir=tmp_path)
    run_pipeline(mode="demo", config=config)
    findings = json.loads((tmp_path / "findings.json").read_text())
    required_fields = {
        "finding_id", "severity", "category", "project_id",
        "title", "detail", "estimated_waste_usd", "detected_at",
    }
    for f in findings:
        assert required_fields <= set(f.keys()), f"Finding missing fields: {f}"


def test_all_four_categories_present(result):
    categories = {f.category for f in result.findings}
    expected = {Category.ANOMALY, Category.IDLE, Category.TAGGING, Category.BUDGET}
    assert expected <= categories, f"Missing categories: {expected - categories}"


def test_findings_sorted_critical_first(result):
    if len(result.findings) > 1:
        severities = [f.severity.value for f in result.findings]
        order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        for i in range(len(severities) - 1):
            assert order[severities[i]] <= order[severities[i + 1]], \
                f"Findings not sorted: {severities[i]} before {severities[i+1]}"


def test_kpis_structure(result):
    kpis = result.kpis()
    required = {
        "total_spend_usd", "finding_count", "critical_count", "high_count",
        "medium_count", "anomaly_count", "idle_count", "tagging_count",
        "budget_count", "total_estimated_waste_usd",
    }
    assert required <= set(kpis.keys())


def test_total_estimated_waste_positive(result):
    assert result.total_estimated_waste() > 0


def test_findings_by_category(result):
    by_cat = result.findings_by_category()
    # All four categories should be present
    for cat in ("ANOMALY", "IDLE", "TAGGING", "BUDGET"):
        assert cat in by_cat, f"Category {cat} missing"


def test_invalid_mode_raises():
    with pytest.raises(ValueError, match="Unknown mode"):
        run_pipeline(mode="invalid")
