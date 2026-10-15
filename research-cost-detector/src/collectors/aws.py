"""
aws.py — Real AWS data collector.

AWSCollector uses boto3 to pull data from:
  1. Cost Explorer  — 90-day daily costs grouped by TAG:{tag_key} and SERVICE
  2. CloudWatch     — CPU/GPU utilisation for EC2 and SageMaker resources (7 days)
  3. Resource Tagging API — sweep all tagged resources for tag compliance
  4. AWS Budgets    — account-level budgets for project comparison

All API calls are paginated.  Transient errors (throttling, retries) are
handled with exponential back-off via botocore's built-in retry config.

The returned dict follows the exact same schema as DemoCollector so the
normalizer is fully shared.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
_LOOKBACK_DAYS = 90
_METRICS_DAYS = 7
_REQUIRED_TAGS = ["CostCentre", "ProjectID", "Owner"]


class AWSCollector:
    """Collects cost and utilisation data from real AWS APIs.

    Parameters
    ----------
    tag_key:
        The tag key used to identify research projects (e.g. "ProjectID").
        Cost Explorer groups by this tag; tag compliance checks this tag.
    profile:
        Optional AWS profile name from ~/.aws/credentials.
    region:
        AWS region for all API calls.
    """

    def __init__(
        self,
        tag_key: str = "ProjectID",
        profile: "str | None" = None,
        region: str = "us-east-1",
    ) -> None:
        self.tag_key = tag_key
        self.profile = profile
        self.region = region
        self._session = self._make_session()

    def _make_session(self):
        import boto3
        from botocore.config import Config

        kwargs: dict[str, Any] = {"region_name": self.region}
        if self.profile:
            kwargs["profile_name"] = self.profile
        return boto3.Session(**kwargs)

    def _client(self, service: str):
        from botocore.config import Config

        cfg = Config(retries={"max_attempts": 5, "mode": "adaptive"})
        return self._session.client(service, config=cfg)

    # ──────────────────────────────────────────────────────────────────────────

    def collect(self) -> dict[str, Any]:
        """Run all collectors and return the combined raw data dict."""
        logger.info("Collecting cost data from Cost Explorer…")
        ce_data = self._collect_cost_explorer()

        logger.info("Collecting resource inventory from Resource Tagging API…")
        resources = self._collect_resources()

        logger.info("Collecting CloudWatch utilisation metrics…")
        hourly_metrics = self._collect_cloudwatch_metrics(resources)

        logger.info("Collecting Budgets…")
        budgets_by_project = self._collect_budgets()

        # Build projects list (union of CE-discovered projects and Budgets)
        projects = self._build_projects(ce_data, budgets_by_project)

        return {
            "projects": projects,
            "resources": resources,
            "daily_costs": ce_data["daily_costs"],
            "hourly_metrics": hourly_metrics,
        }

    # ── Cost Explorer ────────────────────────────────────────────────────────

    def _collect_cost_explorer(self) -> dict[str, Any]:
        ce = self._client("ce")
        end = datetime.utcnow().date()
        start = end - timedelta(days=_LOOKBACK_DAYS)

        rows: list[dict] = []
        project_ids: set[str] = set()

        paginator_token: "str | None" = None
        while True:
            kwargs: dict[str, Any] = dict(
                TimePeriod={
                    "Start": start.strftime("%Y-%m-%d"),
                    "End": end.strftime("%Y-%m-%d"),
                },
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
                GroupBy=[
                    {"Type": "TAG", "Key": self.tag_key},
                    {"Type": "DIMENSION", "Key": "SERVICE"},
                ],
            )
            if paginator_token:
                kwargs["NextPageToken"] = paginator_token

            response = ce.get_cost_and_usage(**kwargs)

            for period in response.get("ResultsByTime", []):
                date_str = period["TimePeriod"]["Start"]
                for group in period.get("Groups", []):
                    keys = group.get("Keys", [])
                    if len(keys) < 2:
                        continue
                    project_tag = keys[0].replace(f"{self.tag_key}$", "")
                    service = keys[1]
                    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])

                    if not project_tag or project_tag == "$":
                        project_tag = "untagged"

                    project_ids.add(project_tag)
                    rows.append(
                        {
                            "date": date_str,
                            "project_id": project_tag,
                            "service": service,
                            "cost_usd": cost,
                        }
                    )

            paginator_token = response.get("NextPageToken")
            if not paginator_token:
                break

        return {"daily_costs": rows, "project_ids": project_ids}

    # ── Resource Tagging API ─────────────────────────────────────────────────

    def _collect_resources(self) -> list[dict]:
        rta = self._client("resourcegroupstaggingapi")
        resources: list[dict] = []
        pagination_token: str = ""

        while True:
            kwargs: dict[str, Any] = {
                "ResourcesPerPage": 100,
                "TagFilters": [],
            }
            if pagination_token:
                kwargs["PaginationToken"] = pagination_token

            response = rta.get_resources(**kwargs)

            for item in response.get("ResourceTagMappingList", []):
                arn: str = item.get("ResourceARN", "")
                tags_raw: list[dict] = item.get("Tags", [])
                tags = {t["Key"]: t["Value"] for t in tags_raw}

                # Parse ARN for service/region
                arn_parts = arn.split(":")
                service = arn_parts[2] if len(arn_parts) > 2 else "unknown"
                resource_region = arn_parts[3] if len(arn_parts) > 3 else self.region

                # Derive resource_id from ARN
                resource_id = arn.split("/")[-1] if "/" in arn else arn.split(":")[-1]

                project_id = tags.get(self.tag_key, "untagged")

                # Try to determine instance type (unavailable from tagging API alone)
                instance_type = tags.get("InstanceType", "unknown")
                state = tags.get("State", "unknown")

                resources.append(
                    {
                        "resource_id": resource_id or arn,
                        "project_id": project_id,
                        "service": self._map_service_name(service),
                        "instance_type": instance_type,
                        "region": resource_region,
                        "tags": tags,
                        "state": state,
                    }
                )

            pagination_token = response.get("PaginationToken", "")
            if not pagination_token:
                break

        return resources

    def _map_service_name(self, service_code: str) -> str:
        """Map boto3 service codes to display names matching CE output."""
        mapping = {
            "ec2":        "Amazon EC2",
            "sagemaker":  "Amazon SageMaker",
            "s3":         "Amazon S3",
            "rds":        "Amazon RDS",
            "lambda":     "AWS Lambda",
        }
        return mapping.get(service_code.lower(), service_code)

    # ── CloudWatch metrics ───────────────────────────────────────────────────

    def _collect_cloudwatch_metrics(self, resources: list[dict]) -> list[dict]:
        cw = self._client("cloudwatch")
        rows: list[dict] = []

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=_METRICS_DAYS)

        for res in resources:
            svc = res.get("service", "")
            rid = res["resource_id"]
            pid = res["project_id"]

            if "EC2" in svc:
                metrics_to_fetch = [
                    ("AWS/EC2", "CPUUtilization", "InstanceId", rid),
                ]
            elif "SageMaker" in svc:
                metrics_to_fetch = [
                    ("aws/sagemaker/Endpoints", "CPUUtilization",  "EndpointName", rid),
                    ("aws/sagemaker/Endpoints", "GPUUtilization",   "EndpointName", rid),
                ]
            else:
                continue

            for namespace, metric_name, dim_name, dim_value in metrics_to_fetch:
                try:
                    response = cw.get_metric_statistics(
                        Namespace=namespace,
                        MetricName=metric_name,
                        Dimensions=[{"Name": dim_name, "Value": dim_value}],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=3600,  # 1-hour buckets
                        Statistics=["Average"],
                    )
                    for point in response.get("Datapoints", []):
                        rows.append(
                            {
                                "timestamp": point["Timestamp"].isoformat(),
                                "resource_id": rid,
                                "project_id": pid,
                                "metric_name": metric_name,
                                "value": float(point["Average"]),
                            }
                        )
                except Exception as exc:
                    logger.debug(
                        "Skipping CloudWatch metric %s for %s: %s",
                        metric_name, rid, exc,
                    )

        return rows

    # ── Budgets ──────────────────────────────────────────────────────────────

    def _collect_budgets(self) -> dict[str, dict]:
        """Return a mapping project_id → {budget, period_start, period_end}."""
        import boto3

        sts = self._session.client("sts")
        try:
            account_id = sts.get_caller_identity()["Account"]
        except Exception as exc:
            logger.warning("Could not get account ID for Budgets: %s", exc)
            return {}

        budgets_client = self._client("budgets")
        result: dict[str, dict] = {}

        try:
            paginator = budgets_client.get_paginator("describe_budgets")
            for page in paginator.paginate(AccountId=account_id):
                for budget in page.get("Budgets", []):
                    name: str = budget.get("BudgetName", "")
                    limit = budget.get("BudgetLimit", {})
                    amount = float(limit.get("Amount", 0))
                    time_period = budget.get("TimePeriod", {})
                    period_start = time_period.get("Start", datetime.utcnow())
                    period_end = time_period.get("End", datetime.utcnow())

                    if isinstance(period_start, datetime):
                        period_start = period_start.isoformat()
                    if isinstance(period_end, datetime):
                        period_end = period_end.isoformat()

                    result[name] = {
                        "monthly_budget_usd": amount,
                        "period_start": period_start,
                        "period_end": period_end,
                    }
        except Exception as exc:
            logger.warning("Budgets collection failed: %s", exc)

        return result

    # ── Project list builder ─────────────────────────────────────────────────

    def _build_projects(
        self,
        ce_data: dict,
        budgets_by_project: dict[str, dict],
    ) -> list[dict]:
        """Merge CE-discovered projects with budget data."""
        project_ids: set[str] = ce_data.get("project_ids", set())
        # Also add any projects found in budgets
        for name in budgets_by_project:
            project_ids.add(name)

        today = datetime.utcnow()
        period_start = today.replace(day=1).strftime("%Y-%m-%d")
        # Period end = last day of current month
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        period_end = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")

        projects = []
        for pid in sorted(project_ids):
            budget_info = budgets_by_project.get(pid, {})
            projects.append(
                {
                    "project_id": pid,
                    "monthly_budget_usd": budget_info.get("monthly_budget_usd", 0.0),
                    "period_start": budget_info.get("period_start", period_start),
                    "period_end": budget_info.get("period_end", period_end),
                    "baseline_daily_usd": 0.0,
                }
            )

        return projects
