"""Tests for src/findings.py"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from src.findings import Finding, Severity, Category, FindingEncoder, findings_to_json


def _make_finding(**kwargs) -> Finding:
    defaults = dict(
        severity=Severity.HIGH,
        category=Category.ANOMALY,
        project_id="proj-genomics",
        resource_id="i-0abc123",
        title="Cost spike detected",
        detail="Daily cost rose by 5× above rolling mean.",
        estimated_waste_usd=412.50,
        detected_at=datetime(2026, 10, 15, 3, 0, 0),
    )
    defaults.update(kwargs)
    return Finding(**defaults)


def test_finding_round_trip():
    f = _make_finding()
    d = f.to_dict()
    as_json = json.dumps(d)
    reloaded = json.loads(as_json)

    assert reloaded["severity"] == "HIGH"
    assert reloaded["category"] == "ANOMALY"
    assert reloaded["project_id"] == "proj-genomics"
    assert reloaded["resource_id"] == "i-0abc123"
    assert reloaded["title"] == "Cost spike detected"
    assert reloaded["estimated_waste_usd"] == 412.50
    assert reloaded["detected_at"] == "2026-10-15T03:00:00"
    assert len(reloaded["finding_id"]) == 16


def test_finding_id_is_deterministic():
    f1 = _make_finding()
    f2 = _make_finding()
    assert f1.finding_id == f2.finding_id


def test_finding_id_differs_for_different_resources():
    f1 = _make_finding(resource_id="i-aaa")
    f2 = _make_finding(resource_id="i-bbb")
    assert f1.finding_id != f2.finding_id


def test_severity_enum_coercion():
    f = Finding(
        severity="CRITICAL",  # type: ignore[arg-type]
        category="BUDGET",  # type: ignore[arg-type]
        project_id="proj-x",
        title="Over budget",
        detail="Project has exceeded budget.",
    )
    assert f.severity is Severity.CRITICAL
    assert f.category is Category.BUDGET


def test_estimated_waste_defaults_to_zero():
    f = Finding(
        severity=Severity.MEDIUM,
        category=Category.TAGGING,
        project_id="proj-x",
        title="Missing tag",
        detail="Resource is missing CostCentre tag.",
    )
    assert f.estimated_waste_usd == 0.0


def test_findings_to_json_list():
    findings = [_make_finding(), _make_finding(resource_id="i-999", title="Other")]
    result = findings_to_json(findings)
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) == 2


def test_finding_encoder():
    f = _make_finding()
    result = json.dumps(f, cls=FindingEncoder)
    parsed = json.loads(result)
    assert parsed["severity"] == "HIGH"
