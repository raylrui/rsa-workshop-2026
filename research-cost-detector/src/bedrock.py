"""
bedrock.py — Amazon Bedrock Converse API wrapper.

generate_narrative(findings, model_id, region, profile) → str | None

Calls the Bedrock Converse API with a structured system prompt and a summary
of findings.  Returns the model's plain-English narrative as a string, or
None if Bedrock is unavailable (missing credentials, no model access,
throttling, or any other error).

The caller (main.py, dashboard) should treat None as "narrative unavailable"
and render the rest of the report/dashboard without it.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
_DEFAULT_REGION = "us-east-1"

_SYSTEM_PROMPT = """You are a Research IT cloud cost advisor helping a university's
Research IT team understand cloud expenditure issues.

Your audience is research computing staff who understand AWS but may not be
experts in cost optimisation.  Write in clear, concise prose.  Prioritise
actionable recommendations over generic advice.  Group your response into
short paragraphs: one for critical issues, one for resource waste, one for
governance (tagging/budgets), and one for recommended immediate actions.
Keep the entire response under 400 words."""


def generate_narrative(
    findings: list,
    model_id: str = _DEFAULT_MODEL_ID,
    region: str = _DEFAULT_REGION,
    profile: "str | None" = None,
) -> "str | None":
    """Generate a plain-English Research IT narrative from structured findings.

    Parameters
    ----------
    findings:
        List of Finding objects from the pipeline.
    model_id:
        Bedrock model ID to invoke (defaults to Claude 3 Sonnet).
    region:
        AWS region where the Bedrock endpoint is available.
    profile:
        Optional AWS profile name.

    Returns
    -------
    str or None
        The model's narrative text, or None if Bedrock is unavailable.
    """
    if not findings:
        return None

    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        session_kwargs: dict = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile

        session = boto3.Session(**session_kwargs)
        client = session.client("bedrock-runtime")

        # Summarise findings as compact JSON
        summary = _summarise_findings(findings)
        user_message = (
            "Here is a JSON summary of cloud cost findings detected for our "
            "research projects.  Please write a plain-English report for the "
            "Research IT team:\n\n" + summary
        )

        response = client.converse(
            modelId=model_id,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"maxTokens": 600, "temperature": 0.3},
        )

        # Extract text from response
        output = response.get("output", {})
        message = output.get("message", {})
        content = message.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "").strip() or None

        logger.warning("Bedrock response had unexpected shape: %s", output)
        return None

    except ImportError:
        logger.warning("boto3 not installed; Bedrock narrative skipped.")
        return None
    except Exception as exc:
        # Catch everything: NoCredentialsError, ClientError, throttling, etc.
        logger.warning("Bedrock narrative skipped: %s", exc)
        return None


def _summarise_findings(findings: list) -> str:
    """Produce a compact JSON summary of findings for the Bedrock prompt."""
    from src.findings import Severity

    # Group counts by category and severity
    summary: dict = {
        "total_findings": len(findings),
        "by_category": {},
        "by_severity": {},
        "top_waste_items": [],
        "projects_affected": set(),
    }

    for f in findings:
        cat = f.category.value
        sev = f.severity.value
        summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
        summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
        summary["projects_affected"].add(f.project_id)

    summary["projects_affected"] = sorted(summary["projects_affected"])

    # Top 5 waste items
    by_waste = sorted(findings, key=lambda f: f.estimated_waste_usd, reverse=True)
    for f in by_waste[:5]:
        if f.estimated_waste_usd > 0:
            summary["top_waste_items"].append({
                "category": f.category.value,
                "severity": f.severity.value,
                "project": f.project_id,
                "title": f.title,
                "waste_usd": round(f.estimated_waste_usd, 2),
            })

    # Total estimated waste
    summary["total_estimated_waste_usd"] = round(
        sum(f.estimated_waste_usd for f in findings), 2
    )

    return json.dumps(summary, indent=2)
