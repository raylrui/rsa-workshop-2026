"""
base.py — AbstractCollector protocol.

Any collector (demo, AWS, …) must implement this protocol so the pipeline
can swap data sources without changing any downstream code.
"""
from __future__ import annotations

from typing import Any, Protocol


class AbstractCollector(Protocol):
    """Protocol for all data collectors.

    Implementors return a raw dict with the following top-level keys:

        "projects"       list[dict]  — project metadata + budget fields
        "resources"      list[dict]  — resource inventory
        "daily_costs"    list[dict]  — daily cost rows
        "hourly_metrics" list[dict]  — hourly utilisation rows

    See src/transforms/normalizer.py for the full schema contract.
    """

    def collect(self) -> dict[str, Any]:
        """Collect raw cloud cost and utilisation data.

        Returns
        -------
        dict
            Raw data bag consumed by the normalizer.
        """
        ...
