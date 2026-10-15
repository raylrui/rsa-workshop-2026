"""Tests for src/bedrock.py — uses unittest.mock to avoid real AWS calls."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.bedrock import generate_narrative, _summarise_findings
from src.findings import Category, Finding, Severity


def _make_findings(n: int = 3) -> list[Finding]:
    return [
        Finding(
            severity=Severity.CRITICAL,
            category=Category.ANOMALY,
            project_id="proj-genomics",
            resource_id="",
            title=f"Cost spike #{i}",
            detail="Spike detected.",
            estimated_waste_usd=500.0 * i,
            detected_at=datetime(2026, 10, 15),
        )
        for i in range(1, n + 1)
    ]


def _mock_bedrock_response(text: str) -> dict:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
            }
        },
        "stopReason": "end_turn",
    }


# ── Success path ──────────────────────────────────────────────────────────────

def test_generate_narrative_returns_string_on_success():
    expected_text = "Here is the Research IT narrative."
    mock_client = MagicMock()
    mock_client.converse.return_value = _mock_bedrock_response(expected_text)

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_client
        result = generate_narrative(_make_findings())

    assert result == expected_text


def test_generate_narrative_calls_converse_with_correct_model():
    mock_client = MagicMock()
    mock_client.converse.return_value = _mock_bedrock_response("ok")

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_client
        generate_narrative(_make_findings(), model_id="my.model-id")

    call_kwargs = mock_client.converse.call_args[1]
    assert call_kwargs["modelId"] == "my.model-id"


def test_generate_narrative_includes_findings_summary():
    mock_client = MagicMock()
    mock_client.converse.return_value = _mock_bedrock_response("narrative")

    captured_messages = []

    def capture_converse(**kwargs):
        captured_messages.append(kwargs["messages"])
        return _mock_bedrock_response("narrative")

    mock_client.converse.side_effect = capture_converse

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_client
        generate_narrative(_make_findings(3))

    user_content = captured_messages[0][0]["content"][0]["text"]
    assert "proj-genomics" in user_content


# ── Failure / graceful-skip path ──────────────────────────────────────────────

def test_generate_narrative_returns_none_on_client_error():
    from botocore.exceptions import ClientError

    mock_client = MagicMock()
    mock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "User not authorized"}},
        "Converse",
    )

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.return_value = mock_client
        result = generate_narrative(_make_findings())

    assert result is None


def test_generate_narrative_returns_none_on_no_credentials():
    from botocore.exceptions import NoCredentialsError

    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.return_value.client.side_effect = NoCredentialsError()
        result = generate_narrative(_make_findings())

    assert result is None


def test_generate_narrative_returns_none_for_empty_findings():
    result = generate_narrative([])
    assert result is None


def test_generate_narrative_returns_none_on_generic_exception():
    with patch("boto3.Session") as mock_session_cls:
        mock_session_cls.side_effect = RuntimeError("Something went wrong")
        result = generate_narrative(_make_findings())

    assert result is None


# ── summarise_findings helper ─────────────────────────────────────────────────

def test_summarise_findings_is_valid_json():
    summary = _summarise_findings(_make_findings(5))
    parsed = json.loads(summary)
    assert parsed["total_findings"] == 5
    assert "by_category" in parsed
    assert "by_severity" in parsed
    assert "top_waste_items" in parsed


def test_summarise_findings_waste_sorted():
    findings = _make_findings(3)
    summary = json.loads(_summarise_findings(findings))
    wastes = [item["waste_usd"] for item in summary["top_waste_items"]]
    assert wastes == sorted(wastes, reverse=True)
