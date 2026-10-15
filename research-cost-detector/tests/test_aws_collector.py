"""Tests for src/collectors/aws.py — all boto3 calls are mocked."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from src.collectors.aws import AWSCollector


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _ce_response(project_id: str = "proj-test", service: str = "Amazon EC2", cost: float = 100.0) -> dict:
    """Minimal Cost Explorer get_cost_and_usage response."""
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-10-01", "End": "2026-10-02"},
                "Groups": [
                    {
                        "Keys": [f"ProjectID${project_id}", service],
                        "Metrics": {"UnblendedCost": {"Amount": str(cost), "Unit": "USD"}},
                    }
                ],
            }
        ],
    }


def _tagging_response(resource_arn: str, tags: list[dict]) -> dict:
    return {
        "ResourceTagMappingList": [
            {"ResourceARN": resource_arn, "Tags": tags}
        ],
        "PaginationToken": "",
    }


def _cloudwatch_response(value: float = 55.0) -> dict:
    return {
        "Datapoints": [
            {
                "Timestamp": datetime(2026, 10, 10, 12, 0),
                "Average": value,
                "Unit": "Percent",
            }
        ]
    }


def _make_collector() -> AWSCollector:
    with patch("boto3.Session"):
        return AWSCollector(tag_key="ProjectID", region="us-east-1")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_collect_returns_required_keys():
    collector = _make_collector()
    collector._collect_cost_explorer = MagicMock(return_value={
        "daily_costs": [{"date": "2026-10-01", "project_id": "proj-test",
                         "service": "Amazon EC2", "cost_usd": 100.0}],
        "project_ids": {"proj-test"},
    })
    collector._collect_resources = MagicMock(return_value=[{
        "resource_id": "i-abc", "project_id": "proj-test", "service": "Amazon EC2",
        "instance_type": "m5.xlarge", "region": "us-east-1", "tags": {}, "state": "running",
    }])
    collector._collect_cloudwatch_metrics = MagicMock(return_value=[])
    collector._collect_budgets = MagicMock(return_value={})

    raw = collector.collect()
    assert set(raw.keys()) == {"projects", "resources", "daily_costs", "hourly_metrics"}


def test_collect_daily_costs_have_correct_keys():
    collector = _make_collector()
    collector._collect_cost_explorer = MagicMock(return_value={
        "daily_costs": [{"date": "2026-10-01", "project_id": "proj-test",
                         "service": "Amazon EC2", "cost_usd": 100.0}],
        "project_ids": {"proj-test"},
    })
    collector._collect_resources = MagicMock(return_value=[])
    collector._collect_cloudwatch_metrics = MagicMock(return_value=[])
    collector._collect_budgets = MagicMock(return_value={})

    raw = collector.collect()
    for row in raw["daily_costs"]:
        assert {"date", "project_id", "service", "cost_usd"} <= set(row.keys())


def test_collect_projects_list_derived_from_ce():
    collector = _make_collector()
    collector._collect_cost_explorer = MagicMock(return_value={
        "daily_costs": [],
        "project_ids": {"proj-a", "proj-b"},
    })
    collector._collect_resources = MagicMock(return_value=[])
    collector._collect_cloudwatch_metrics = MagicMock(return_value=[])
    collector._collect_budgets = MagicMock(return_value={})

    raw = collector.collect()
    pids = {p["project_id"] for p in raw["projects"]}
    assert "proj-a" in pids
    assert "proj-b" in pids


def test_collect_projects_have_required_budget_fields():
    collector = _make_collector()
    collector._collect_cost_explorer = MagicMock(return_value={
        "daily_costs": [],
        "project_ids": {"proj-test"},
    })
    collector._collect_resources = MagicMock(return_value=[])
    collector._collect_cloudwatch_metrics = MagicMock(return_value=[])
    collector._collect_budgets = MagicMock(return_value={
        "proj-test": {
            "monthly_budget_usd": 5000.0,
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
        }
    })

    raw = collector.collect()
    proj = next(p for p in raw["projects"] if p["project_id"] == "proj-test")
    assert proj["monthly_budget_usd"] == 5000.0
    assert "period_start" in proj
    assert "period_end" in proj


def test_ce_response_parsed_correctly():
    collector = _make_collector()
    mock_ce = MagicMock()
    mock_ce.get_cost_and_usage.return_value = _ce_response(
        project_id="proj-genomics", service="Amazon EC2", cost=250.0
    )
    collector._client = MagicMock(return_value=mock_ce)

    result = collector._collect_cost_explorer()
    assert len(result["daily_costs"]) == 1
    row = result["daily_costs"][0]
    assert row["project_id"] == "proj-genomics"
    assert row["service"] == "Amazon EC2"
    assert row["cost_usd"] == 250.0
    assert "proj-genomics" in result["project_ids"]


def test_tagging_response_parsed_correctly():
    collector = _make_collector()
    mock_rta = MagicMock()
    mock_rta.get_resources.return_value = _tagging_response(
        "arn:aws:ec2:us-east-1:123456789:instance/i-0abc123",
        [{"Key": "ProjectID", "Value": "proj-test"}, {"Key": "Owner", "Value": "alice@uni.edu"}],
    )
    collector._client = MagicMock(return_value=mock_rta)

    resources = collector._collect_resources()
    assert len(resources) == 1
    res = resources[0]
    assert res["resource_id"] == "i-0abc123"
    assert res["service"] == "Amazon EC2"
    assert res["tags"]["ProjectID"] == "proj-test"


def test_cloudwatch_metrics_collected():
    collector = _make_collector()
    mock_cw = MagicMock()
    mock_cw.get_metric_statistics.return_value = _cloudwatch_response(65.0)
    collector._client = MagicMock(return_value=mock_cw)

    resources = [{
        "resource_id": "i-test123",
        "project_id": "proj-test",
        "service": "Amazon EC2",
        "instance_type": "m5.xlarge",
        "region": "us-east-1",
        "tags": {},
        "state": "running",
    }]
    metrics = collector._collect_cloudwatch_metrics(resources)
    assert len(metrics) >= 1
    assert metrics[0]["metric_name"] == "CPUUtilization"
    assert metrics[0]["value"] == 65.0


def test_map_service_name():
    collector = _make_collector()
    assert collector._map_service_name("ec2") == "Amazon EC2"
    assert collector._map_service_name("sagemaker") == "Amazon SageMaker"
    assert collector._map_service_name("s3") == "Amazon S3"
    assert collector._map_service_name("unknown-svc") == "unknown-svc"


def test_normalizer_accepts_aws_collector_output():
    """The normalizer should accept AWSCollector output without errors."""
    from src.transforms.normalizer import normalize

    collector = _make_collector()
    collector._collect_cost_explorer = MagicMock(return_value={
        "daily_costs": [
            {"date": "2026-10-01", "project_id": "proj-test",
             "service": "Amazon EC2", "cost_usd": 100.0},
        ],
        "project_ids": {"proj-test"},
    })
    collector._collect_resources = MagicMock(return_value=[{
        "resource_id": "i-abc", "project_id": "proj-test", "service": "Amazon EC2",
        "instance_type": "m5.xlarge", "region": "us-east-1", "tags": {}, "state": "running",
    }])
    collector._collect_cloudwatch_metrics = MagicMock(return_value=[])
    collector._collect_budgets = MagicMock(return_value={
        "proj-test": {
            "monthly_budget_usd": 5000.0,
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
        }
    })

    raw = collector.collect()
    dataset = normalize(raw)
    assert len(dataset.daily_costs) == 1
    assert len(dataset.resources) == 1
    assert len(dataset.budgets) == 1
