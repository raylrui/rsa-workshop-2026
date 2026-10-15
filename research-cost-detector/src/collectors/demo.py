"""
demo.py — Deterministic synthetic data generator.

Produces realistic AWS-like cost, resource and utilisation data for 10
research projects and ~60 resources covering:
  • 90 days of daily cost per project (last day = "today")
  • 7 days × 24 h of hourly CPUUtilization / GPUUtilization per compute resource

Deliberately injected anomalies so the detectors always have something to find:
  A) proj-ml-training   — 5× cost spike on day 75 (→ ANOMALY / CRITICAL)
  B) proj-climate       — actual spend already 20% over monthly budget (→ BUDGET / CRITICAL)
  C) proj-bioinformatics — forecast will exceed 90% of budget (→ BUDGET / HIGH)
  D) i-idle-ec2-{1,2,3} — CPU < 5% for all 7 days (→ IDLE / HIGH)
  E) sagemaker-gpu-idle  — GPU 0% for all 7 days (→ IDLE / CRITICAL)
  F) 8 resources have missing required tags (→ TAGGING / MEDIUM)
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

import numpy as np

# ── Fixed seed for determinism ────────────────────────────────────────────────
_SEED = 42

# ── Simulation anchor: "today" in demo world ─────────────────────────────────
_TODAY = datetime(2026, 10, 15)
_PERIOD_START = datetime(2026, 10, 1)
_PERIOD_END = datetime(2026, 10, 31)

# ── Project definitions ───────────────────────────────────────────────────────
_PROJECTS = [
    {"project_id": "proj-genomics",       "monthly_budget_usd": 8_000,  "baseline": 200},
    {"project_id": "proj-climate",        "monthly_budget_usd": 5_000,  "baseline": 280},  # B
    {"project_id": "proj-ml-training",    "monthly_budget_usd": 12_000, "baseline": 350},  # A
    {"project_id": "proj-bioinformatics", "monthly_budget_usd": 6_000,  "baseline": 190},  # C
    {"project_id": "proj-astrophysics",   "monthly_budget_usd": 4_500,  "baseline": 110},
    {"project_id": "proj-drug-discovery", "monthly_budget_usd": 15_000, "baseline": 420},
    {"project_id": "proj-materials-sim",  "monthly_budget_usd": 7_000,  "baseline": 160},
    {"project_id": "proj-cryo-em",        "monthly_budget_usd": 9_500,  "baseline": 240},
    {"project_id": "proj-epidemiology",   "monthly_budget_usd": 3_500,  "baseline": 85},
    {"project_id": "proj-neuroscience",   "monthly_budget_usd": 11_000, "baseline": 310},
]

_SERVICES = ["Amazon EC2", "Amazon S3", "Amazon SageMaker", "Amazon RDS", "AWS Lambda"]

_SERVICE_COST_SPLIT = {
    "Amazon EC2":        0.45,
    "Amazon SageMaker":  0.30,
    "Amazon S3":         0.10,
    "Amazon RDS":        0.10,
    "AWS Lambda":        0.05,
}

_REGIONS = ["us-east-1", "us-west-2", "eu-west-1"]
_REQUIRED_TAGS = ["CostCentre", "ProjectID", "Owner"]

# ── Resource templates ────────────────────────────────────────────────────────
# (service, instance_type, is_gpu)
_RESOURCE_TEMPLATES = [
    ("Amazon EC2", "m5.xlarge", False),
    ("Amazon EC2", "c5.2xlarge", False),
    ("Amazon EC2", "r5.4xlarge", False),
    ("Amazon EC2", "t3.medium", False),
    ("Amazon SageMaker", "ml.p3.2xlarge", True),   # GPU
    ("Amazon SageMaker", "ml.g4dn.xlarge", True),  # GPU
    ("Amazon SageMaker", "ml.c5.4xlarge", False),
    ("Amazon RDS", "db.r5.large", False),
    ("Amazon S3", "bucket", False),
    ("AWS Lambda", "function", False),
]


def _make_tags(project_id: str, missing_tags: list[str] | None = None) -> dict[str, str]:
    tags = {
        "CostCentre": f"CC-{project_id.split('-')[-1].upper()}",
        "ProjectID":  project_id,
        "Owner":      f"researcher@{project_id.replace('proj-', '')}.edu",
        "Environment": "research",
    }
    for tag in (missing_tags or []):
        tags.pop(tag, None)
    return tags


class DemoCollector:
    """Generates fully deterministic synthetic research cloud data.

    Parameters
    ----------
    seed:
        RNG seed; change to produce a different (but equally valid) dataset.
    """

    def __init__(self, seed: int = _SEED) -> None:
        self._seed = seed

    # ------------------------------------------------------------------
    def collect(self) -> dict[str, Any]:
        rng = np.random.default_rng(self._seed)
        py_rng = random.Random(self._seed)

        projects = self._build_projects()
        resources = self._build_resources(py_rng)
        daily_costs = self._build_daily_costs(rng, resources)
        hourly_metrics = self._build_hourly_metrics(rng, resources)

        return {
            "projects": projects,
            "resources": resources,
            "daily_costs": daily_costs,
            "hourly_metrics": hourly_metrics,
        }

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    def _build_projects(self) -> list[dict]:
        rows = []
        for p in _PROJECTS:
            rows.append(
                {
                    "project_id":         p["project_id"],
                    "monthly_budget_usd": p["monthly_budget_usd"],
                    "period_start":       _PERIOD_START.isoformat(),
                    "period_end":         _PERIOD_END.isoformat(),
                    "baseline_daily_usd": p["baseline"],
                }
            )
        return rows

    def _build_resources(self, py_rng: random.Random) -> list[dict]:
        """Build ~60 resources spread across 10 projects."""
        resources = []
        res_idx = 0

        # Idle EC2 instances (anomaly D) — assigned to proj-astrophysics
        for i in range(1, 4):
            resources.append(
                {
                    "resource_id":   f"i-idle-ec2-{i}",
                    "project_id":    "proj-astrophysics",
                    "service":       "Amazon EC2",
                    "instance_type": "m5.xlarge",
                    "region":        "us-east-1",
                    "state":         "running",
                    "tags":          _make_tags("proj-astrophysics"),
                    "_is_idle_cpu":  True,
                    "_is_idle_gpu":  False,
                }
            )

        # Idle GPU SageMaker (anomaly E) — assigned to proj-ml-training
        resources.append(
            {
                "resource_id":   "sagemaker-gpu-idle",
                "project_id":    "proj-ml-training",
                "service":       "Amazon SageMaker",
                "instance_type": "ml.p3.2xlarge",
                "region":        "us-east-1",
                "state":         "running",
                "tags":          _make_tags("proj-ml-training"),
                "_is_idle_cpu":  False,
                "_is_idle_gpu":  True,
            }
        )

        # 8 resources with deliberately missing tags (anomaly F)
        missing_tag_assignments = [
            ("proj-genomics",       ["CostCentre"]),
            ("proj-genomics",       ["Owner"]),
            ("proj-climate",        ["CostCentre", "Owner"]),
            ("proj-bioinformatics", ["ProjectID"]),
            ("proj-drug-discovery", ["CostCentre"]),
            ("proj-cryo-em",        ["Owner"]),
            ("proj-epidemiology",   ["CostCentre", "ProjectID"]),
            ("proj-neuroscience",   ["Owner"]),
        ]
        for proj, missing in missing_tag_assignments:
            svc, itype, is_gpu = py_rng.choice(_RESOURCE_TEMPLATES[:4])  # EC2 only
            rid = f"i-untagged-{res_idx:03d}"
            resources.append(
                {
                    "resource_id":   rid,
                    "project_id":    proj,
                    "service":       svc,
                    "instance_type": itype,
                    "region":        py_rng.choice(_REGIONS),
                    "state":         "running",
                    "tags":          _make_tags(proj, missing),
                    "_is_idle_cpu":  False,
                    "_is_idle_gpu":  False,
                }
            )
            res_idx += 1

        # Normal resources: ~4–6 per project
        project_resource_counts = {
            p["project_id"]: py_rng.randint(4, 6) for p in _PROJECTS
        }
        for proj_def in _PROJECTS:
            pid = proj_def["project_id"]
            count = project_resource_counts[pid]
            for _ in range(count):
                svc, itype, is_gpu = py_rng.choice(_RESOURCE_TEMPLATES)
                rid = f"res-{res_idx:04d}"
                resources.append(
                    {
                        "resource_id":   rid,
                        "project_id":    pid,
                        "service":       svc,
                        "instance_type": itype,
                        "region":        py_rng.choice(_REGIONS),
                        "state":         py_rng.choice(["running", "running", "stopped"]),
                        "tags":          _make_tags(pid),
                        "_is_idle_cpu":  False,
                        "_is_idle_gpu":  is_gpu and False,  # normal GPU resources are busy
                    }
                )
                res_idx += 1

        return resources

    def _build_daily_costs(
        self,
        rng: np.random.Generator,
        resources: list[dict],
    ) -> list[dict]:
        """90-day daily cost rows per (project, service)."""
        rows = []
        end_date = _TODAY
        start_date = end_date - timedelta(days=89)

        # Build a lookup: project_id → baseline
        baseline_map = {p["project_id"]: p["baseline"] for p in _PROJECTS}

        for proj_def in _PROJECTS:
            pid = proj_def["project_id"]
            baseline = baseline_map[pid]

            for day_offset in range(90):
                date = start_date + timedelta(days=day_offset)
                daily_total = baseline * (1 + rng.normal(0, 0.08))

                # Anomaly A: proj-ml-training spikes 5× on day 75
                if pid == "proj-ml-training" and day_offset == 74:
                    daily_total = baseline * 5.0

                # Anomaly B: proj-climate — inflate to put it 20% over budget
                # Budget = 5000/month, ~14 days elapsed in Oct, daily baseline=280
                # Target: 14 * 280 * 1.20 ≈ over budget
                if pid == "proj-climate" and date >= _PERIOD_START:
                    daily_total = baseline * 1.22  # ~22% above baseline → over budget

                # Anomaly C: proj-bioinformatics — slightly elevated to push forecast > 90%
                if pid == "proj-bioinformatics" and date >= _PERIOD_START:
                    daily_total = baseline * 1.12

                # Split daily total across services
                for svc, frac in _SERVICE_COST_SPLIT.items():
                    svc_cost = daily_total * frac * (1 + rng.normal(0, 0.03))
                    rows.append(
                        {
                            "date":       date.isoformat(),
                            "project_id": pid,
                            "service":    svc,
                            "cost_usd":   max(0.0, round(float(svc_cost), 4)),
                        }
                    )

        return rows

    def _build_hourly_metrics(
        self,
        rng: np.random.Generator,
        resources: list[dict],
    ) -> list[dict]:
        """7-day hourly CPU/GPU utilisation metrics per compute resource."""
        rows = []
        end_ts = _TODAY.replace(hour=23)
        start_ts = end_ts - timedelta(days=6)
        hours = 7 * 24  # 168 data points

        for res in resources:
            svc = res["service"]
            if svc not in ("Amazon EC2", "Amazon SageMaker"):
                continue

            is_idle_cpu = res.get("_is_idle_cpu", False)
            is_idle_gpu = res.get("_is_idle_gpu", False)
            is_gpu = res["instance_type"].startswith("ml.p") or res["instance_type"].startswith("ml.g")

            for h in range(hours):
                ts = start_ts + timedelta(hours=h)

                # CPU utilisation
                if is_idle_cpu:
                    cpu = float(rng.uniform(0.5, 4.9))  # < 5%
                else:
                    cpu = float(rng.uniform(35, 95))

                rows.append(
                    {
                        "timestamp":   ts.isoformat(),
                        "resource_id": res["resource_id"],
                        "project_id":  res["project_id"],
                        "metric_name": "CPUUtilization",
                        "value":       round(cpu, 2),
                    }
                )

                # GPU utilisation (only for GPU-class instances)
                if is_gpu:
                    if is_idle_gpu:
                        gpu = 0.0
                    else:
                        gpu = float(rng.uniform(40, 98))
                    rows.append(
                        {
                            "timestamp":   ts.isoformat(),
                            "resource_id": res["resource_id"],
                            "project_id":  res["project_id"],
                            "metric_name": "GPUUtilization",
                            "value":       round(gpu, 2),
                        }
                    )

        return rows
