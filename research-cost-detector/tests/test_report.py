"""Tests for src/report.py"""
import sys
import os
import tempfile
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.pipeline import PipelineConfig, run_pipeline
from src.report import generate_report


class IDCollector(HTMLParser):
    """Collects all id= attributes seen in the HTML."""
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.text_chunks = []
        self._capture = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if "id" in attrs_dict:
            self.ids.add(attrs_dict["id"])

    def handle_data(self, data):
        self.text_chunks.append(data)

    @property
    def full_text(self):
        return " ".join(self.text_chunks)


@pytest.fixture(scope="module")
def report_path(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("report")
    config = PipelineConfig(mode="demo", output_dir=tmp)
    result = run_pipeline(mode="demo", config=config)
    out = tmp / "report.html"
    generate_report(result, out, narrative=None)
    return out


@pytest.fixture(scope="module")
def parsed_html(report_path):
    parser = IDCollector()
    parser.feed(report_path.read_text(encoding="utf-8"))
    return parser


def test_report_file_exists(report_path):
    assert report_path.exists()
    assert report_path.stat().st_size > 5000  # should not be trivially small


def test_report_kpi_bar_present(parsed_html):
    assert "kpi-bar" in parsed_html.ids, "Missing id='kpi-bar'"


def test_report_findings_table_present(parsed_html):
    assert "findings-table" in parsed_html.ids, "Missing id='findings-table'"


def test_report_chart_canvases_present(parsed_html):
    for chart_id in ("chartDailyCost", "chartSeverity", "chartWaste", "chartCategory"):
        assert chart_id in parsed_html.ids, f"Missing chart canvas id='{chart_id}'"


def test_report_contains_findings_count(report_path, parsed_html):
    # Should contain some project names from the demo data
    assert "proj-" in parsed_html.full_text


def test_report_contains_chartjs_script(report_path):
    html = report_path.read_text(encoding="utf-8")
    assert "chart.js" in html.lower() or "Chart.js" in html, "Chart.js CDN not found"


def test_report_with_narrative(tmp_path):
    config = PipelineConfig(mode="demo", output_dir=tmp_path)
    result = run_pipeline(mode="demo", config=config)
    out = tmp_path / "report_with_narrative.html"
    generate_report(result, out, narrative="Test Bedrock narrative text here.")
    html = out.read_text(encoding="utf-8")
    assert "Test Bedrock narrative text here." in html


def test_report_without_narrative_no_bedrock_section(tmp_path):
    config = PipelineConfig(mode="demo", output_dir=tmp_path)
    result = run_pipeline(mode="demo", config=config)
    out = tmp_path / "report_no_narrative.html"
    generate_report(result, out, narrative=None)
    parser = IDCollector()
    parser.feed(out.read_text(encoding="utf-8"))
    # The section element with id=bedrock-section must NOT be present when no narrative
    assert "bedrock-section" not in parser.ids


def test_report_is_standalone(report_path):
    """Report must not reference any local file assets — only CDN links allowed."""
    html = report_path.read_text(encoding="utf-8")
    # Should not have local file references like src="./..." or href="./..."
    import re
    local_refs = re.findall(r'(?:src|href)=["\'](?!https?://|#|data:)([^"\']+)["\']', html)
    assert local_refs == [], f"Found local asset references: {local_refs}"
