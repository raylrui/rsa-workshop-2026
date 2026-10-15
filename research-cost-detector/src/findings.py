"""
findings.py — Core data model for pipeline findings.

Every detector produces a list[Finding].  The pipeline merges them all and
serialises them to findings.json via FindingEncoder.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Category(str, Enum):
    ANOMALY = "ANOMALY"
    IDLE = "IDLE"
    TAGGING = "TAGGING"
    BUDGET = "BUDGET"


@dataclass
class Finding:
    """A single detected issue surfaced by a detector.

    Attributes
    ----------
    finding_id:
        Stable, deterministic identifier derived from the finding's key fields.
        Computed automatically when not provided.
    severity:
        Impact / urgency level (CRITICAL → LOW).
    category:
        Which detector raised this finding.
    project_id:
        Research project this finding is attributed to.
    resource_id:
        Specific cloud resource (e.g. instance ID, S3 bucket name).  Empty
        string for project-level findings such as budget overruns.
    title:
        Short human-readable headline (≤ 80 chars).
    detail:
        Full description with numbers and context.
    estimated_waste_usd:
        Dollar amount of avoidable spend (0.0 when not applicable).
    detected_at:
        UTC timestamp of detection; defaults to now.
    """

    severity: Severity
    category: Category
    project_id: str
    title: str
    detail: str
    resource_id: str = ""
    estimated_waste_usd: float = 0.0
    detected_at: datetime = field(default_factory=datetime.utcnow)
    finding_id: str = field(default="", init=True)

    def __post_init__(self) -> None:
        # Coerce enum values in case raw strings are passed
        if isinstance(self.severity, str):
            self.severity = Severity(self.severity)
        if isinstance(self.category, str):
            self.category = Category(self.category)
        # Generate a stable ID if not explicitly provided
        if not self.finding_id:
            self.finding_id = self._make_id()

    def _make_id(self) -> str:
        """Deterministic SHA-256-based ID (first 16 hex chars)."""
        key = f"{self.category.value}|{self.project_id}|{self.resource_id}|{self.title}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity.value,
            "category": self.category.value,
            "project_id": self.project_id,
            "resource_id": self.resource_id,
            "title": self.title,
            "detail": self.detail,
            "estimated_waste_usd": round(self.estimated_waste_usd, 2),
            "detected_at": self.detected_at.isoformat(),
        }


class FindingEncoder(json.JSONEncoder):
    """JSON encoder that handles Finding objects and datetimes."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Finding):
            return obj.to_dict()
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


def findings_to_json(findings: list[Finding], indent: int = 2) -> str:
    """Serialise a list of findings to a JSON string."""
    return json.dumps([f.to_dict() for f in findings], indent=indent)
