"""
tagging.py — Missing cost-allocation tag detector.

Checks every resource in the NormalizedDataset's `resources` DataFrame for
the presence of a configurable set of required tags.  One Finding is
produced per resource that is missing one or more tags.

Severity: MEDIUM (governance issue; doesn't directly cause spend but blocks
cost attribution and chargeback).
"""
from __future__ import annotations

from datetime import datetime

from src.findings import Category, Finding, Severity

DEFAULT_REQUIRED_TAGS = ["CostCentre", "ProjectID", "Owner"]


class TaggingDetector:
    """Flags resources that are missing required cost-allocation tags."""

    def __init__(self, required_tags: list[str] | None = None) -> None:
        self.required_tags: list[str] = required_tags or DEFAULT_REQUIRED_TAGS

    def detect(self, dataset) -> list[Finding]:
        """Run tag-compliance detection over a NormalizedDataset."""
        findings: list[Finding] = []

        for _, row in dataset.resources.iterrows():
            tags: dict = row["tags"] if isinstance(row["tags"], dict) else {}
            missing = [t for t in self.required_tags if t not in tags or not tags[t]]

            if not missing:
                continue

            rid = str(row["resource_id"])
            pid = str(row["project_id"])

            findings.append(
                Finding(
                    severity=Severity.MEDIUM,
                    category=Category.TAGGING,
                    project_id=pid,
                    resource_id=rid,
                    title=f"Missing tags on {rid}: {', '.join(missing)}",
                    detail=(
                        f"Resource {rid} ({row['service']}, {row['instance_type']}, "
                        f"{row['region']}) is missing required cost-allocation "
                        f"tag(s): {', '.join(missing)}.  "
                        f"Without these tags, costs cannot be attributed to the "
                        f"correct project, department or owner.  "
                        f"Present tags: {list(tags.keys())}."
                    ),
                    estimated_waste_usd=0.0,
                    detected_at=datetime.utcnow(),
                )
            )

        return findings
