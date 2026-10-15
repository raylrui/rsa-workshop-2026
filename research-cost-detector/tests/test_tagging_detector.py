"""Tests for src/detectors/tagging.py"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytest

from src.collectors.demo import DemoCollector
from src.transforms.normalizer import normalize, NormalizedDataset
from src.detectors.tagging import TaggingDetector, DEFAULT_REQUIRED_TAGS
from src.findings import Severity, Category


def _make_dataset(resources: list[dict]) -> NormalizedDataset:
    res = pd.DataFrame(resources)
    for col in ("resource_id", "project_id", "service", "instance_type", "region", "state"):
        if col not in res.columns:
            res[col] = "test"
    if "tags" not in res.columns:
        res["tags"] = [{}] * len(res)

    hm = pd.DataFrame(columns=["timestamp", "resource_id", "project_id", "metric_name", "value"])
    hm["timestamp"] = pd.to_datetime(hm["timestamp"])
    hm["value"] = hm["value"].astype("float64")

    dc = pd.DataFrame([{
        "date": "2026-10-01", "project_id": "proj-test",
        "service": "Amazon EC2", "cost_usd": 100.0,
    }])
    dc["date"] = pd.to_datetime(dc["date"])
    dc["cost_usd"] = dc["cost_usd"].astype("float64")

    bud = pd.DataFrame([{
        "project_id": "proj-test", "monthly_budget_usd": 1000.0,
        "period_start": pd.Timestamp("2026-10-01"),
        "period_end": pd.Timestamp("2026-10-31"),
    }])

    return NormalizedDataset(daily_costs=dc, hourly_metrics=hm, resources=res, budgets=bud)


def _res(resource_id="i-test", project_id="proj-test", tags=None) -> dict:
    return {
        "resource_id": resource_id,
        "project_id": project_id,
        "service": "Amazon EC2",
        "instance_type": "m5.xlarge",
        "region": "us-east-1",
        "state": "running",
        "tags": tags or {},
    }


def test_fully_tagged_resource_no_finding():
    full_tags = {"CostCentre": "CC-001", "ProjectID": "proj-test", "Owner": "researcher@lab.edu"}
    ds = _make_dataset([_res(tags=full_tags)])
    findings = TaggingDetector().detect(ds)
    assert findings == []


def test_missing_single_tag_flagged():
    partial_tags = {"ProjectID": "proj-test", "Owner": "researcher@lab.edu"}
    # Missing CostCentre
    ds = _make_dataset([_res(tags=partial_tags)])
    findings = TaggingDetector().detect(ds)
    assert len(findings) == 1
    assert "CostCentre" in findings[0].title


def test_missing_all_tags_one_finding_per_resource():
    ds = _make_dataset([_res(tags={})])
    findings = TaggingDetector().detect(ds)
    # One finding per resource (listing all missing tags)
    assert len(findings) == 1
    for required in DEFAULT_REQUIRED_TAGS:
        assert required in findings[0].detail


def test_multiple_resources_independent():
    full = {"CostCentre": "CC-001", "ProjectID": "proj-test", "Owner": "x@y.com"}
    partial = {"ProjectID": "proj-test"}
    ds = _make_dataset([_res("i-full", tags=full), _res("i-partial", tags=partial)])
    findings = TaggingDetector().detect(ds)
    assert len(findings) == 1
    assert findings[0].resource_id == "i-partial"


def test_severity_is_medium():
    ds = _make_dataset([_res(tags={})])
    findings = TaggingDetector().detect(ds)
    assert all(f.severity == Severity.MEDIUM for f in findings)


def test_category_is_tagging():
    ds = _make_dataset([_res(tags={})])
    findings = TaggingDetector().detect(ds)
    assert all(f.category == Category.TAGGING for f in findings)


def test_estimated_waste_is_zero():
    ds = _make_dataset([_res(tags={})])
    findings = TaggingDetector().detect(ds)
    assert all(f.estimated_waste_usd == 0.0 for f in findings)


def test_custom_required_tags():
    ds = _make_dataset([_res(tags={"MyCustomTag": "value"})])
    findings = TaggingDetector(required_tags=["MyCustomTag"]).detect(ds)
    assert findings == []

    findings2 = TaggingDetector(required_tags=["MyCustomTag", "AnotherTag"]).detect(ds)
    assert len(findings2) == 1
    assert "AnotherTag" in findings2[0].title


def test_demo_8_untagged_resources_detected():
    raw = DemoCollector().collect()
    ds = normalize(raw)
    findings = TaggingDetector().detect(ds)
    assert len(findings) >= 8, f"Expected ≥8 tagging findings, got {len(findings)}"
