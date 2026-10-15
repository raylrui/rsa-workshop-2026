"""
pipeline.py — Pipeline orchestrator.

run_pipeline(mode, config) → PipelineResult

Collect → Normalise → Detect → Write findings.json
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.findings import Finding, FindingEncoder, findings_to_json
from src.transforms.normalizer import NormalizedDataset, normalize

logger = logging.getLogger(__name__)

# Default output directory (relative to cwd)
DEFAULT_OUTPUT_DIR = Path("output")


@dataclass
class PipelineConfig:
    """Configuration for a single pipeline run."""

    mode: str = "demo"                      # "demo" or "aws"
    output_dir: Path = DEFAULT_OUTPUT_DIR
    # aws-mode options
    aws_tag_key: str = "ProjectID"
    aws_profile: str | None = None
    aws_region: str = "us-east-1"
    # detector options (all configurable, sensible defaults)
    anomaly_window: int = 7
    anomaly_threshold: float = 3.0
    cpu_idle_threshold: float = 10.0
    gpu_idle_threshold: float = 5.0
    cpu_idle_min_days: int = 5
    gpu_idle_min_days: int = 3
    required_tags: list[str] = field(
        default_factory=lambda: ["CostCentre", "ProjectID", "Owner"]
    )
    budget_at_risk_threshold: float = 0.90


@dataclass
class PipelineResult:
    """Output of a pipeline run."""

    dataset: NormalizedDataset
    findings: list[Finding]
    run_at: datetime = field(default_factory=datetime.utcnow)
    mode: str = "demo"

    # ── convenience helpers ──────────────────────────────────────────────────

    def findings_by_category(self) -> dict[str, list[Finding]]:
        result: dict[str, list[Finding]] = {}
        for f in self.findings:
            result.setdefault(f.category.value, []).append(f)
        return result

    def findings_by_severity(self) -> dict[str, list[Finding]]:
        result: dict[str, list[Finding]] = {}
        for f in self.findings:
            result.setdefault(f.severity.value, []).append(f)
        return result

    def total_estimated_waste(self) -> float:
        return round(sum(f.estimated_waste_usd for f in self.findings), 2)

    def kpis(self) -> dict[str, Any]:
        """Return a flat dict of key metrics for display in the dashboard/report."""
        dc = self.dataset.daily_costs
        total_spend = float(dc["cost_usd"].sum())
        by_sev = self.findings_by_severity()
        by_cat = self.findings_by_category()
        return {
            "total_spend_usd": round(total_spend, 2),
            "finding_count": len(self.findings),
            "critical_count": len(by_sev.get("CRITICAL", [])),
            "high_count": len(by_sev.get("HIGH", [])),
            "medium_count": len(by_sev.get("MEDIUM", [])),
            "low_count": len(by_sev.get("LOW", [])),
            "anomaly_count": len(by_cat.get("ANOMALY", [])),
            "idle_count": len(by_cat.get("IDLE", [])),
            "tagging_count": len(by_cat.get("TAGGING", [])),
            "budget_count": len(by_cat.get("BUDGET", [])),
            "total_estimated_waste_usd": self.total_estimated_waste(),
            "run_at": self.run_at.isoformat(),
            "mode": self.mode,
        }


def run_pipeline(
    mode: str = "demo",
    config: PipelineConfig | None = None,
) -> PipelineResult:
    """Run the full collect → normalise → detect pipeline.

    Parameters
    ----------
    mode:
        "demo" uses DemoCollector; "aws" uses AWSCollector.
    config:
        Optional PipelineConfig; defaults are used if not provided.

    Returns
    -------
    PipelineResult
    """
    if config is None:
        config = PipelineConfig(mode=mode)

    # ── 1. Collect ────────────────────────────────────────────────────────────
    logger.info("Collecting data (mode=%s)…", mode)
    collector = _build_collector(mode, config)
    raw = collector.collect()

    # ── 2. Normalise ──────────────────────────────────────────────────────────
    logger.info("Normalising dataset…")
    dataset = normalize(raw)

    # ── 3. Detect ─────────────────────────────────────────────────────────────
    logger.info("Running detectors…")
    findings = _run_detectors(dataset, config)

    # Assign stable IDs post-merge (finding IDs are already deterministic via __post_init__)
    logger.info("Found %d findings.", len(findings))

    # ── 4. Write findings.json ────────────────────────────────────────────────
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    findings_path = output_dir / "findings.json"
    findings_path.write_text(findings_to_json(findings), encoding="utf-8")
    logger.info("Findings written to %s", findings_path)

    return PipelineResult(
        dataset=dataset,
        findings=findings,
        mode=mode,
    )


# ── Private helpers ───────────────────────────────────────────────────────────


def _build_collector(mode: str, config: PipelineConfig):
    if mode == "demo":
        from src.collectors.demo import DemoCollector

        return DemoCollector()
    elif mode == "aws":
        from src.collectors.aws import AWSCollector

        return AWSCollector(
            tag_key=config.aws_tag_key,
            profile=config.aws_profile,
            region=config.aws_region,
        )
    else:
        raise ValueError(f"Unknown mode '{mode}'. Use 'demo' or 'aws'.")


def _run_detectors(dataset: NormalizedDataset, config: PipelineConfig) -> list[Finding]:
    from src.detectors.anomaly import AnomalyDetector
    from src.detectors.budget import BudgetDetector
    from src.detectors.idle import IdleDetector
    from src.detectors.tagging import TaggingDetector

    detectors = [
        AnomalyDetector(window=config.anomaly_window, threshold=config.anomaly_threshold),
        IdleDetector(
            cpu_threshold=config.cpu_idle_threshold,
            gpu_threshold=config.gpu_idle_threshold,
            cpu_min_days=config.cpu_idle_min_days,
            gpu_min_days=config.gpu_idle_min_days,
        ),
        TaggingDetector(required_tags=config.required_tags),
        BudgetDetector(at_risk_threshold=config.budget_at_risk_threshold),
    ]

    all_findings: list[Finding] = []
    for detector in detectors:
        try:
            found = detector.detect(dataset)
            all_findings.extend(found)
            logger.debug("%s produced %d findings", type(detector).__name__, len(found))
        except Exception as exc:
            logger.error("Detector %s failed: %s", type(detector).__name__, exc)

    # Sort: CRITICAL first, then by category
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_findings.sort(key=lambda f: (severity_order.get(f.severity.value, 99), f.category.value))

    return all_findings
