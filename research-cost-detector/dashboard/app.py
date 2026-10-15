"""
dashboard/app.py — Research Cloud Cost Intelligence
Streamlit dashboard for Research IT FinOps demonstration.

Navigation: Overview | Findings | Research Projects | Report
Sidebar: controls only (data source, Bedrock toggle, Run Analysis)
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.findings import Category, Severity
from src.pipeline import PipelineConfig, PipelineResult, run_pipeline

# ── Page configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Research Cloud Cost Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design tokens ─────────────────────────────────────────────────────────────
SEV_COLOURS = {
    "CRITICAL": "#c0392b",
    "HIGH":     "#d35400",
    "MEDIUM":   "#d4a017",
    "LOW":      "#27ae60",
}
SEV_BG = {
    "CRITICAL": "#fdf2f2",
    "HIGH":     "#fef6ef",
    "MEDIUM":   "#fefdf0",
    "LOW":      "#f0faf4",
}
CAT_COLOURS = {
    "ANOMALY": "#5b4fcf",
    "IDLE":    "#1a56a0",
    "TAGGING": "#0e7c6a",
    "BUDGET":  "#a93226",
}
PROJECT_PALETTE = [
    "#2563eb", "#d97706", "#059669", "#dc2626", "#7c3aed",
    "#0891b2", "#ea580c", "#16a34a", "#9333ea", "#0284c7",
]
ACCENT = "#2563eb"
NAVY   = "#1e2a3a"

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Base ── */
html, body, [data-testid="stAppViewContainer"] {
    background: #f8fafc !important;
    color: #1e2a3a;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e2e8f0;
}
[data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }

/* ── Tab strip ── */
[data-testid="stTabs"] [role="tablist"] {
    gap: 0;
    border-bottom: 2px solid #e2e8f0;
    background: #ffffff;
    padding: 0 1rem;
}
[data-testid="stTabs"] [role="tab"] {
    font-size: 0.85rem;
    font-weight: 500;
    color: #64748b;
    padding: 0.6rem 1.2rem;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    background: transparent !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #2563eb;
    border-bottom-color: #2563eb;
    font-weight: 600;
}

/* ── Section headers ── */
.section-header {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
    margin: 1.5rem 0 0.75rem 0;
}

/* ── KPI cards ── */
.kpi-grid { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 1.5rem; }
.kpi-card {
    flex: 1 1 160px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.kpi-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #64748b;
    font-weight: 600;
    margin-bottom: 4px;
}
.kpi-value {
    font-size: 1.65rem;
    font-weight: 700;
    color: #1e2a3a;
    line-height: 1.15;
}
.kpi-sub {
    font-size: 0.72rem;
    color: #94a3b8;
    margin-top: 3px;
}
.kpi-critical .kpi-value { color: #c0392b; }
.kpi-high     .kpi-value { color: #d35400; }
.kpi-blue     .kpi-value { color: #2563eb; }

/* ── Severity badges ── */
.badge {
    display: inline-block;
    font-size: 0.67rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 10px;
    letter-spacing: 0.04em;
    color: #ffffff;
    white-space: nowrap;
}
.badge-CRITICAL { background: #c0392b; }
.badge-HIGH     { background: #d35400; }
.badge-MEDIUM   { background: #b7860f; }
.badge-LOW      { background: #27ae60; }
.badge-ANOMALY  { background: #5b4fcf; }
.badge-IDLE     { background: #1a56a0; }
.badge-TAGGING  { background: #0e7c6a; }
.badge-BUDGET   { background: #a93226; }

/* ── Finding cards (Top Findings) ── */
.finding-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #cbd5e1;
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 10px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.finding-card.sev-CRITICAL { border-left-color: #c0392b; }
.finding-card.sev-HIGH     { border-left-color: #d35400; }
.finding-card.sev-MEDIUM   { border-left-color: #d4a017; }
.finding-card.sev-LOW      { border-left-color: #27ae60; }
.finding-title {
    font-size: 0.88rem;
    font-weight: 600;
    color: #1e2a3a;
    margin: 6px 0 4px 0;
}
.finding-meta {
    font-size: 0.75rem;
    color: #64748b;
}
.finding-waste {
    font-size: 0.82rem;
    font-weight: 600;
    color: #2563eb;
    margin-top: 4px;
}

/* ── DEMO badge ── */
.demo-badge {
    display: inline-block;
    background: #fff3cd;
    color: #856404;
    border: 1px solid #ffc107;
    border-radius: 6px;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 2px 8px;
    vertical-align: middle;
    text-transform: uppercase;
    margin-left: 8px;
}

/* ── AI narrative card ── */
.ai-card {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 12px;
    padding: 20px 24px;
    margin-top: 1rem;
}
.ai-card-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #3b82f6;
    margin-bottom: 8px;
}
.ai-card-body {
    font-size: 0.875rem;
    color: #1e3a5f;
    line-height: 1.7;
    white-space: pre-wrap;
}

/* ── Project summary cards ── */
.proj-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 16px 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    height: 100%;
}
.proj-name {
    font-size: 0.82rem;
    font-weight: 700;
    color: #1e2a3a;
    margin-bottom: 10px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.proj-stat { font-size: 0.72rem; color: #475569; margin-bottom: 3px; }
.proj-stat strong { color: #1e2a3a; font-weight: 600; }

/* ── Budget bar ── */
.budget-track {
    background: #e2e8f0;
    border-radius: 4px;
    height: 6px;
    margin: 6px 0;
    overflow: hidden;
}
.budget-fill {
    height: 100%;
    border-radius: 4px;
    background: #2563eb;
}
.budget-fill.over  { background: #c0392b; }
.budget-fill.risk  { background: #d35400; }

/* ── Report page ── */
.report-status-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 24px 28px;
    max-width: 640px;
}
.report-label { font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
                letter-spacing: 0.07em; color: #64748b; margin-bottom: 4px; }
.report-value { font-size: 0.92rem; color: #1e2a3a; margin-bottom: 14px; }

/* ── Sidebar controls ── */
div[data-testid="stSidebar"] hr { border-color: #e2e8f0; margin: 0.8rem 0; }
div[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    background: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 600;
    padding: 0.55rem 1rem;
}
div[data-testid="stSidebar"] .stButton > button:hover {
    background: #1d4ed8;
}

/* ── Divider ── */
.divider { border: none; border-top: 1px solid #e2e8f0; margin: 1.5rem 0; }

/* ── Streamlit metric tweak ── */
[data-testid="metric-container"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 10px 14px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _badge(text: str, kind: str) -> str:
    return f'<span class="badge badge-{kind}">{text}</span>'


def _kpi_card(label: str, value: str, sub: str = "", css_class: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="kpi-card {css_class}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{sub_html}'
        f'</div>'
    )


def _findings_df(result: PipelineResult) -> pd.DataFrame:
    rows = []
    for f in result.findings:
        rows.append({
            "Severity":   f.severity.value,
            "Category":   f.category.value,
            "Project":    f.project_id,
            "Resource":   f.resource_id or "—",
            "Finding":    f.title,
            "Waste (USD)": f.estimated_waste_usd,
            "Detail":     f.detail,
            "finding_id": f.finding_id,
        })
    return pd.DataFrame(rows)


def _anomaly_dates(result: PipelineResult) -> set[tuple[str, str]]:
    """Return set of (date_str, project_id) tuples for anomaly findings."""
    out = set()
    for f in result.findings:
        if f.category != Category.ANOMALY:
            continue
        try:
            date_str = f.title.split(" on ")[1].split(" for ")[0]
            out.add((date_str, f.project_id))
        except (IndexError, ValueError):
            pass
    return out


def _daily_cost_chart(result: PipelineResult, height: int = 420) -> go.Figure:
    """Multi-project daily cost line chart with anomaly markers."""
    dc = result.dataset.daily_costs.copy()
    daily = (
        dc.groupby(["date", "project_id"])["cost_usd"]
        .sum()
        .reset_index()
    )
    cutoff = daily["date"].max() - pd.Timedelta(days=29)
    recent = daily[daily["date"] >= cutoff].sort_values("date")
    projects = sorted(recent["project_id"].unique())

    anomaly_set = _anomaly_dates(result)

    # Find the single largest anomaly finding for a callout annotation
    anomaly_findings = sorted(
        [f for f in result.findings if f.category == Category.ANOMALY],
        key=lambda f: f.estimated_waste_usd, reverse=True,
    )
    top_anomaly = anomaly_findings[0] if anomaly_findings else None
    top_anomaly_key: "tuple[str, str] | None" = None
    if top_anomaly:
        try:
            d = top_anomaly.title.split(" on ")[1].split(" for ")[0]
            top_anomaly_key = (d, top_anomaly.project_id)
        except (IndexError, ValueError):
            pass

    fig = go.Figure()
    for i, proj in enumerate(projects):
        proj_data = recent[recent["project_id"] == proj].sort_values("date")
        colour = PROJECT_PALETTE[i % len(PROJECT_PALETTE)]
        short = proj.replace("proj-", "")
        fig.add_trace(go.Scatter(
            x=proj_data["date"],
            y=proj_data["cost_usd"],
            name=short,
            mode="lines",
            line=dict(color=colour, width=1.5),
            hovertemplate=f"<b>{short}</b><br>%{{x|%d %b}}<br>$%{{y:,.0f}}<extra></extra>",
        ))
        # Anomaly markers
        anom_rows = proj_data[
            proj_data.apply(
                lambda r: (str(r["date"])[:10], proj) in anomaly_set, axis=1
            )
        ]
        if not anom_rows.empty:
            fig.add_trace(go.Scatter(
                x=anom_rows["date"],
                y=anom_rows["cost_usd"],
                mode="markers",
                marker=dict(symbol="diamond", size=9, color="#c0392b",
                            line=dict(color="#ffffff", width=1.5)),
                name="Anomaly",
                showlegend=(i == 0),
                hovertemplate="<b>Anomaly detected</b><br>%{x|%d %b}<br>$%{y:,.0f}<extra></extra>",
            ))

    # Annotation on the largest anomaly point that falls in the 30-day window
    annotations = []
    if top_anomaly_key:
        date_str, proj = top_anomaly_key
        proj_data = recent[recent["project_id"] == proj]
        match_rows = proj_data[
            proj_data["date"].dt.strftime("%Y-%m-%d") == date_str
        ]
        if not match_rows.empty:
            ann_x = match_rows["date"].iloc[0]
            ann_y = float(match_rows["cost_usd"].iloc[0])
            annotations.append(dict(
                x=ann_x, y=ann_y,
                text=f"  ${top_anomaly.estimated_waste_usd:,.0f} excess",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=1.5,
                arrowcolor="#c0392b",
                font=dict(size=11, color="#c0392b", family="inherit"),
                align="left",
                bgcolor="rgba(255,255,255,0.85)",
                borderpad=3,
            ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=60),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="inherit", size=12, color="#475569"),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=-0.28,
            xanchor="left", x=0,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
            traceorder="normal",
        ),
        xaxis=dict(
            gridcolor="#f1f5f9", linecolor="#e2e8f0", tickfont=dict(size=11),
        ),
        yaxis=dict(
            gridcolor="#f1f5f9", linecolor="#e2e8f0", tickfont=dict(size=11),
            tickprefix="$", tickformat=",.0f",
        ),
        hovermode="x unified",
        annotations=annotations,
    )
    return fig


def _waste_bar_chart(result: PipelineResult, height: int = 280) -> go.Figure:
    waste: dict[str, float] = {}
    for f in result.findings:
        waste[f.category.value] = waste.get(f.category.value, 0.0) + f.estimated_waste_usd

    cats  = list(waste.keys())
    vals  = [waste[c] for c in cats]
    cols  = [CAT_COLOURS.get(c, "#94a3b8") for c in cats]

    fig = go.Figure(go.Bar(
        x=cats, y=vals,
        marker_color=cols,
        hovertemplate="%{x}<br>$%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(linecolor="#e2e8f0", tickfont=dict(size=11)),
        yaxis=dict(gridcolor="#f1f5f9", linecolor="#e2e8f0", tickfont=dict(size=11),
                   tickprefix="$", tickformat=",.0f"),
    )
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.05rem;font-weight:700;color:#1e2a3a;margin-bottom:4px">'
        'Research Cloud Cost Intelligence</div>'
        '<div style="font-size:0.72rem;color:#64748b;margin-bottom:1rem">'
        'FinOps · Research IT</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr style="border-color:#e2e8f0;margin:0.5rem 0 1rem 0">', unsafe_allow_html=True)

    mode = st.selectbox(
        "Data source",
        options=["demo", "aws"],
        index=0,
        help="'demo' uses synthetic data. 'aws' uses live boto3 collectors.",
        label_visibility="visible",
    )

    enable_bedrock = st.checkbox(
        "Enable AI narrative (Bedrock)",
        value=False,
        help="Calls Amazon Bedrock Converse API. Requires credentials and model access.",
    )

    st.markdown('<hr style="border-color:#e2e8f0;margin:0.75rem 0">', unsafe_allow_html=True)

    run_clicked = st.button("Run Analysis", use_container_width=True)

    if "run_count" not in st.session_state:
        st.session_state["run_count"] = 0

    if run_clicked:
        with st.spinner("Running analysis pipeline…"):
            try:
                st.session_state["run_count"] += 1
                config = PipelineConfig(mode=mode, output_dir=Path("output"))
                result = run_pipeline(mode=mode, config=config)

                narrative = None
                if enable_bedrock:
                    try:
                        from src.bedrock import generate_narrative
                        narrative = generate_narrative(result.findings)
                    except Exception:
                        narrative = None

                st.session_state["result"]    = result
                st.session_state["narrative"] = narrative
                st.session_state["mode"]      = mode
                st.session_state["run_at"]    = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                st.success(f"Analysis complete — {len(result.findings)} findings")
            except Exception as exc:
                st.error(f"Pipeline error: {exc}")

    st.markdown('<hr style="border-color:#e2e8f0;margin:0.75rem 0">', unsafe_allow_html=True)

    # Generate report button (only when results exist)
    if "result" in st.session_state:
        if st.button("Generate HTML Report", use_container_width=True):
            try:
                from src.report import generate_report
                report_path = Path("output") / "report.html"
                generate_report(
                    st.session_state["result"],
                    report_path,
                    narrative=st.session_state.get("narrative"),
                )
                st.session_state["report_generated_at"] = datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M UTC"
                )
                st.success("Report generated.")
            except Exception as exc:
                st.error(f"Report error: {exc}")

    st.markdown(
        '<div style="font-size:0.68rem;color:#94a3b8;margin-top:1.5rem">'
        'Research IT FinOps Demo<br>Not for production use.'
        '</div>',
        unsafe_allow_html=True,
    )


# ── Page title ────────────────────────────────────────────────────────────────

active_mode = st.session_state.get("mode", mode)
demo_badge  = '<span class="demo-badge">Demo Data</span>' if active_mode == "demo" else ""
run_at      = st.session_state.get("run_at", "")
run_ts      = f'<span style="font-size:0.75rem;color:#94a3b8;margin-left:12px">Last run: {run_at}</span>' if run_at else ""

st.markdown(
    f'<h1 style="font-size:1.55rem;font-weight:700;color:#1e2a3a;margin-bottom:2px">'
    f'Research Cloud Cost Intelligence{demo_badge}{run_ts}'
    f'</h1>'
    f'<p style="font-size:0.85rem;color:#64748b;margin-bottom:1.25rem">'
    f'Cost anomaly, waste and budget risk detection for research workloads'
    f'</p>',
    unsafe_allow_html=True,
)

# ── Landing state ─────────────────────────────────────────────────────────────

if "result" not in st.session_state:
    st.markdown(
        '<div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;'
        'padding:32px 36px;max-width:680px;">'
        '<div style="font-size:1rem;font-weight:600;color:#1e2a3a;margin-bottom:12px">'
        'Automated cloud cost analysis for research workloads</div>'
        '<div style="font-size:0.85rem;color:#475569;line-height:1.8;margin-bottom:20px">'
        '<b>Cost anomalies</b> — statistically unusual spend spikes per project<br>'
        '<b>Idle resources</b> — compute and GPU instances with low utilisation<br>'
        '<b>Missing tags</b> — resources without required cost-allocation tags<br>'
        '<b>Budget risks</b> — projects exceeding or forecast to exceed budget'
        '</div>'
        '<div style="font-size:0.78rem;color:#94a3b8">'
        'Select a data source in the sidebar, then click <strong>Run Analysis</strong> to start.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    # Inline shortcut so the CTA is visible without scrolling to the sidebar
    st.markdown('<div style="margin-top:14px"></div>', unsafe_allow_html=True)
    if st.button("Run Demo Analysis", type="primary"):
        with st.spinner("Running analysis pipeline…"):
            try:
                config = PipelineConfig(mode="demo", output_dir=Path("output"))
                result_inline = run_pipeline(mode="demo", config=config)
                st.session_state["result"]    = result_inline
                st.session_state["narrative"] = None
                st.session_state["mode"]      = "demo"
                st.session_state["run_at"]    = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                st.rerun()
            except Exception as exc:
                st.error(f"Pipeline error: {exc}")
    st.stop()

# ── Load state ────────────────────────────────────────────────────────────────

result: PipelineResult    = st.session_state["result"]
narrative: "str | None"   = st.session_state.get("narrative")
kpis                       = result.kpis()

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_overview, tab_findings, tab_projects, tab_report = st.tabs([
    "Overview", "Findings", "Research Projects", "Report",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Overview
# ═══════════════════════════════════════════════════════════════════════════════

with tab_overview:

    # ── KPI cards ────────────────────────────────────────────────────────────
    total   = kpis["total_spend_usd"]
    waste   = kpis["total_estimated_waste_usd"]
    wpct    = f"{waste / total * 100:.2f}% of total spend" if total else ""

    # Category-specific counts for accurate sub-labels (not total critical count)
    budget_critical = sum(
        1 for f in result.findings
        if f.category == Category.BUDGET and f.severity == Severity.CRITICAL
    )
    budget_high = sum(
        1 for f in result.findings
        if f.category == Category.BUDGET and f.severity == Severity.HIGH
    )
    anomaly_critical = sum(
        1 for f in result.findings
        if f.category == Category.ANOMALY and f.severity == Severity.CRITICAL
    )

    budget_sub = (
        f"{budget_critical} over budget" if budget_critical
        else f"{budget_high} at risk" if budget_high
        else "all within budget"
    )
    anomaly_sub = f"{anomaly_critical} critical" if anomaly_critical else "no critical spikes"

    cards_html = (
        '<div class="kpi-grid">'
        + _kpi_card("Total Spend", f'${total:,.0f}', "90-day period")
        + _kpi_card("Estimated Waste", f'${waste:,.0f}', wpct, "kpi-blue")
        + _kpi_card("Cost Anomalies", str(kpis["anomaly_count"]),
                    anomaly_sub,
                    "kpi-critical" if anomaly_critical else "")
        + _kpi_card("Idle Resources", str(kpis["idle_count"]),
                    "CPU or GPU underutilised")
        + _kpi_card("Budget Risks", str(kpis["budget_count"]),
                    budget_sub,
                    "kpi-high" if budget_critical else "")
        + '</div>'
    )
    st.markdown(cards_html, unsafe_allow_html=True)

    # ── Charts row ───────────────────────────────────────────────────────────
    col_main, col_side = st.columns([2, 1], gap="medium")

    with col_main:
        st.markdown(
            '<div style="font-size:0.82rem;font-weight:600;color:#1e2a3a;margin-bottom:8px">'
            'Daily Cloud Spend — Last 30 Days'
            '</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(_daily_cost_chart(result, height=420),
                        use_container_width=True, config={"displayModeBar": False})

    with col_side:
        st.markdown(
            '<div style="font-size:0.82rem;font-weight:600;color:#1e2a3a;margin-bottom:8px">'
            'Estimated Waste by Category'
            '</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(_waste_bar_chart(result, height=360),
                        use_container_width=True, config={"displayModeBar": False})

        # Finding severity summary — compact, no duplication of KPI cards
        sev_html = (
            '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">'
        )
        for sev_val, colour in SEV_COLOURS.items():
            count = kpis.get(f"{sev_val.lower()}_count", 0)
            if count:
                sev_html += (
                    f'<div style="text-align:center">'
                    f'<div style="font-size:1.1rem;font-weight:700;color:{colour}">{count}</div>'
                    f'<div style="font-size:0.65rem;text-transform:uppercase;'
                    f'letter-spacing:0.06em;color:#94a3b8">{sev_val}</div>'
                    f'</div>'
                )
        sev_html += '</div>'
        st.markdown(sev_html, unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # ── Top Findings ─────────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.82rem;font-weight:600;color:#1e2a3a;margin-bottom:12px">'
        'Top Findings by Impact'
        '</div>',
        unsafe_allow_html=True,
    )

    # Sort by: severity tier first, then estimated waste descending within tier.
    # This surfaces high-$ findings over low-$ findings of the same severity level,
    # making the demo immediately legible.
    _sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    top5 = sorted(
        result.findings,
        key=lambda f: (_sev_order.get(f.severity.value, 99), -f.estimated_waste_usd),
    )[:5]

    for f in top5:
        sev   = f.severity.value
        cat   = f.category.value
        waste_str = f"Estimated waste: ${f.estimated_waste_usd:,.2f}" if f.estimated_waste_usd else ""
        st.markdown(
            f'<div class="finding-card sev-{sev}">'
            f'<div>{_badge(sev, sev)}&nbsp;{_badge(cat, cat)}</div>'
            f'<div class="finding-title">{f.title}</div>'
            f'<div class="finding-meta">Project: {f.project_id}'
            + (f' &nbsp;·&nbsp; Resource: {f.resource_id}' if f.resource_id else '')
            + f'</div>'
            + (f'<div class="finding-waste">{waste_str}</div>' if waste_str else '')
            + f'</div>',
            unsafe_allow_html=True,
        )

    if len(result.findings) > 5:
        st.markdown(
            f'<div style="font-size:0.78rem;color:#64748b;margin-top:6px">'
            f'+ {len(result.findings) - 5} more findings — see the Findings tab</div>',
            unsafe_allow_html=True,
        )

    # ── AI narrative ─────────────────────────────────────────────────────────
    if narrative:
        st.markdown(
            '<div class="ai-card">'
            '<div class="ai-card-label">AI Research IT Summary &nbsp;·&nbsp; Amazon Bedrock — AI-generated analysis</div>'
            f'<div class="ai-card-body">{narrative}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    elif enable_bedrock:
        st.info("Bedrock narrative unavailable — check credentials and model access.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Findings
# ═══════════════════════════════════════════════════════════════════════════════

with tab_findings:

    findings_df = _findings_df(result)

    # ── Compact filter bar ────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns([1, 1, 1, 2])
    with fc1:
        filter_sev = st.multiselect(
            "Severity", ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
            default=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
            label_visibility="visible",
        )
    with fc2:
        filter_cat = st.multiselect(
            "Category", ["ANOMALY", "IDLE", "TAGGING", "BUDGET"],
            default=["ANOMALY", "IDLE", "TAGGING", "BUDGET"],
        )
    with fc3:
        filter_proj = st.multiselect(
            "Project",
            options=sorted(findings_df["Project"].unique()),
            default=[],
            placeholder="All",
        )
    with fc4:
        search_text = st.text_input("Search", placeholder="Filter by project, resource or title…",
                                    label_visibility="visible")

    filtered = findings_df[
        findings_df["Severity"].isin(filter_sev) &
        findings_df["Category"].isin(filter_cat)
    ].copy()
    if filter_proj:
        filtered = filtered[filtered["Project"].isin(filter_proj)]
    if search_text:
        mask = (
            filtered["Project"].str.contains(search_text, case=False, na=False) |
            filtered["Finding"].str.contains(search_text, case=False, na=False) |
            filtered["Resource"].str.contains(search_text, case=False, na=False)
        )
        filtered = filtered[mask]

    st.markdown(
        f'<div style="font-size:0.75rem;color:#64748b;margin:8px 0 10px 0">'
        f'Showing {len(filtered)} of {len(findings_df)} findings'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Table ─────────────────────────────────────────────────────────────────
    display_cols = ["Severity", "Category", "Project", "Resource", "Finding", "Waste (USD)"]
    st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        height=min(600, 60 + len(filtered) * 38),
        hide_index=True,
        column_config={
            "Waste (USD)": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    # ── Detail panel ──────────────────────────────────────────────────────────
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.82rem;font-weight:600;color:#1e2a3a;margin-bottom:10px">'
        'Finding Detail</div>',
        unsafe_allow_html=True,
    )

    if filtered.empty:
        st.info("No findings match the current filters.")
    else:
        finding_titles = [f"{r['Severity']} · {r['Finding'][:80]}"
                          for _, r in filtered.iterrows()]
        selected_idx = st.selectbox("Select a finding to inspect",
                                    options=range(len(finding_titles)),
                                    format_func=lambda i: finding_titles[i],
                                    label_visibility="visible")

        row = filtered.iloc[selected_idx]
        sev = row["Severity"]
        cat = row["Category"]

        # Match to original Finding object for full detail
        match = next(
            (f for f in result.findings if f.finding_id == row["finding_id"]), None
        )

        st.markdown(
            f'<div class="finding-card sev-{sev}" style="max-width:860px">'
            f'<div style="margin-bottom:8px">'
            f'{_badge(sev, sev)}&nbsp;{_badge(cat, cat)}'
            f'</div>'
            f'<div class="finding-title" style="font-size:0.95rem">{row["Finding"]}</div>'
            f'<div class="finding-meta" style="margin-top:6px">'
            f'Project: <strong>{row["Project"]}</strong>'
            + (f'&nbsp;·&nbsp;Resource: <strong>{row["Resource"]}</strong>' if row["Resource"] != "—" else "")
            + f'&nbsp;·&nbsp;Category: <strong>{cat}</strong>'
            f'</div>'
            + (f'<div class="finding-waste" style="margin-top:8px">Estimated waste: ${row["Waste (USD)"]:,.2f}</div>'
               if row["Waste (USD)"] > 0 else "")
            + f'<div style="margin-top:14px;padding-top:12px;border-top:1px solid #f1f5f9;'
              f'font-size:0.82rem;color:#475569;line-height:1.7">'
            + (match.detail if match else row.get("Detail", ""))
            + f'</div>'
              f'<div style="font-size:0.7rem;color:#94a3b8;margin-top:10px">'
              f'Finding ID: {row["finding_id"]}'
            + (f'&nbsp;·&nbsp;Detected: {match.detected_at.strftime("%Y-%m-%d %H:%M UTC")}' if match else "")
            + f'</div>'
              f'</div>',
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Research Projects
# ═══════════════════════════════════════════════════════════════════════════════

with tab_projects:

    dc       = result.dataset.daily_costs
    budgets  = result.dataset.budgets
    res_df   = result.dataset.resources
    findings = result.findings

    # ── Build per-project summary ─────────────────────────────────────────────
    proj_spend = (
        dc.groupby("project_id")["cost_usd"]
        .sum()
        .reset_index()
        .rename(columns={"cost_usd": "total_spend"})
    )
    # Period spend (for budget comparison)
    budgets_map = dict(zip(budgets["project_id"],
                           zip(budgets["monthly_budget_usd"],
                               budgets["period_start"],
                               budgets["period_end"])))
    period_spend: dict[str, float] = {}
    for pid, (budget, pstart, pend) in budgets_map.items():
        mask = (
            (dc["project_id"] == pid) &
            (dc["date"] >= pd.Timestamp(pstart)) &
            (dc["date"] <= pd.Timestamp(pend))
        )
        period_spend[pid] = float(dc[mask]["cost_usd"].sum())

    # Findings per project
    findings_by_proj: dict[str, list] = {}
    for f in findings:
        findings_by_proj.setdefault(f.project_id, []).append(f)

    # Top service per project
    top_service = (
        dc.groupby(["project_id", "service"])["cost_usd"]
        .sum()
        .reset_index()
        .sort_values("cost_usd", ascending=False)
        .groupby("project_id")
        .first()
        .reset_index()
    )
    top_svc_map = dict(zip(top_service["project_id"], top_service["service"]))

    all_projects = sorted(proj_spend["project_id"].unique())

    # ── Summary cards grid ────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:0.82rem;font-weight:600;color:#1e2a3a;margin-bottom:12px">'
        'All Research Projects</div>',
        unsafe_allow_html=True,
    )

    cols_per_row = 3
    for row_start in range(0, len(all_projects), cols_per_row):
        cols = st.columns(cols_per_row, gap="medium")
        for col_i, proj in enumerate(all_projects[row_start:row_start + cols_per_row]):
            spend_row  = proj_spend[proj_spend["project_id"] == proj]
            total_s    = float(spend_row["total_spend"].iloc[0]) if not spend_row.empty else 0
            binfo      = budgets_map.get(proj)
            budget_usd = float(binfo[0]) if binfo else 0
            p_spend    = period_spend.get(proj, 0)
            nfindings  = len(findings_by_proj.get(proj, []))
            waste_est  = sum(f.estimated_waste_usd for f in findings_by_proj.get(proj, []))
            svc        = top_svc_map.get(proj, "—").replace("Amazon ", "").replace("AWS ", "")

            # Budget bar
            budget_pct = min(p_spend / budget_usd * 100, 120) if budget_usd else 0
            bar_class  = "over" if budget_pct > 100 else ("risk" if budget_pct > 89 else "")
            budget_html = ""
            if budget_usd:
                budget_html = (
                    f'<div class="budget-track"><div class="budget-fill {bar_class}" '
                    f'style="width:{min(budget_pct,100):.0f}%"></div></div>'
                    f'<div class="proj-stat">'
                    f'Budget: <strong>${p_spend:,.0f}</strong> / ${budget_usd:,.0f} '
                    f'({budget_pct:.0f}%)</div>'
                )

            with cols[col_i]:
                st.markdown(
                    f'<div class="proj-card">'
                    f'<div class="proj-name">{proj}</div>'
                    f'<div class="proj-stat">90-day spend: <strong>${total_s:,.0f}</strong></div>'
                    f'{budget_html}'
                    f'<div class="proj-stat">Findings: <strong>{nfindings}</strong>'
                    + (f'&nbsp;·&nbsp;Waste: <strong>${waste_est:,.0f}</strong>' if waste_est else '')
                    + f'</div>'
                    f'<div class="proj-stat">Top service: <strong>{svc}</strong></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Project deep-dive ─────────────────────────────────────────────────────
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.82rem;font-weight:600;color:#1e2a3a;margin-bottom:10px">'
        'Project Detail</div>',
        unsafe_allow_html=True,
    )

    selected_proj = st.selectbox(
        "Select project",
        options=all_projects,
        label_visibility="visible",
    )

    if selected_proj:
        proj_dc = dc[dc["project_id"] == selected_proj].copy()
        proj_daily = (
            proj_dc.groupby("date")["cost_usd"]
            .sum()
            .reset_index()
            .sort_values("date")
        )
        cutoff = proj_daily["date"].max() - pd.Timedelta(days=29)
        proj_recent = proj_daily[proj_daily["date"] >= cutoff]

        # Cost trend chart
        anomaly_set_proj = {d for (d, p) in _anomaly_dates(result) if p == selected_proj}
        anom_rows = proj_recent[
            proj_recent["date"].dt.strftime("%Y-%m-%d").isin(anomaly_set_proj)
        ]

        fig_proj = go.Figure()
        fig_proj.add_trace(go.Scatter(
            x=proj_recent["date"], y=proj_recent["cost_usd"],
            mode="lines", name="Daily cost",
            line=dict(color=ACCENT, width=2),
            fill="tozeroy", fillcolor="rgba(37,99,235,0.06)",
            hovertemplate="%{x|%d %b}: $%{y:,.0f}<extra></extra>",
        ))
        if not anom_rows.empty:
            fig_proj.add_trace(go.Scatter(
                x=anom_rows["date"], y=anom_rows["cost_usd"],
                mode="markers", name="Anomaly",
                marker=dict(symbol="diamond", size=10, color="#c0392b",
                            line=dict(color="#ffffff", width=1.5)),
                hovertemplate="Anomaly: $%{y:,.0f}<extra></extra>",
            ))
        fig_proj.update_layout(
            height=260,
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=True,
            legend=dict(orientation="h", y=1.12, x=0, font=dict(size=10),
                        bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(gridcolor="#f1f5f9", tickfont=dict(size=11)),
            yaxis=dict(gridcolor="#f1f5f9", tickfont=dict(size=11),
                       tickprefix="$", tickformat=",.0f"),
        )
        st.plotly_chart(fig_proj, use_container_width=True,
                        config={"displayModeBar": False})

        # Service breakdown
        svc_spend = (
            proj_dc.groupby("service")["cost_usd"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
            .rename(columns={"service": "Service", "cost_usd": "Spend (USD)"})
        )
        pc1, pc2 = st.columns([1, 2], gap="medium")
        with pc1:
            st.markdown(
                '<div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;'
                'letter-spacing:0.07em;color:#64748b;margin-bottom:6px">By service</div>',
                unsafe_allow_html=True,
            )
            st.dataframe(svc_spend, hide_index=True, use_container_width=True,
                         height=180,
                         column_config={"Spend (USD)": st.column_config.NumberColumn(format="$%.0f")})

        with pc2:
            proj_findings = findings_by_proj.get(selected_proj, [])
            st.markdown(
                f'<div style="font-size:0.75rem;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:0.07em;color:#64748b;margin-bottom:6px">'
                f'Findings ({len(proj_findings)})</div>',
                unsafe_allow_html=True,
            )
            if proj_findings:
                for f in proj_findings:
                    sev = f.severity.value
                    st.markdown(
                        f'<div style="display:flex;align-items:flex-start;gap:8px;'
                        f'margin-bottom:6px;font-size:0.8rem">'
                        f'{_badge(sev, sev)}&nbsp;{_badge(f.category.value, f.category.value)}'
                        f'<span style="color:#1e2a3a">{f.title}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<div style="font-size:0.82rem;color:#64748b">No findings for this project.</div>',
                    unsafe_allow_html=True,
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Report
# ═══════════════════════════════════════════════════════════════════════════════

with tab_report:

    report_path      = Path("output") / "report.html"
    report_exists    = report_path.exists()
    report_generated = st.session_state.get("report_generated_at", "")
    if not report_generated and report_exists:
        import datetime as _dt
        mtime = report_path.stat().st_mtime
        report_generated = _dt.datetime.utcfromtimestamp(mtime).strftime("%Y-%m-%d %H:%M UTC")

    st.markdown(
        '<div style="font-size:0.82rem;font-weight:600;color:#1e2a3a;margin-bottom:14px">'
        'HTML Report</div>',
        unsafe_allow_html=True,
    )

    status_colour = "#27ae60" if report_exists else "#94a3b8"
    status_text   = "Available" if report_exists else "Not yet generated"

    st.markdown(
        f'<div class="report-status-card">'
        f'<div class="report-label">Status</div>'
        f'<div class="report-value" style="color:{status_colour};font-weight:600">'
        f'{status_text}</div>'
        f'<div class="report-label">Last generated</div>'
        f'<div class="report-value">{report_generated or "—"}</div>'
        f'<div class="report-label">Contents</div>'
        f'<div class="report-value" style="font-size:0.82rem;color:#475569">'
        f'KPI summary · Daily cost chart · Waste by category · '
        f'Findings by severity · Sortable findings table with detail toggles'
        + (' · AI narrative summary' if st.session_state.get("narrative") else '')
        + f'</div>'
          f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div style="margin-top:1rem"></div>', unsafe_allow_html=True)

    btn1, btn2 = st.columns([1, 1], gap="small")
    with btn1:
        if st.button("Generate / Refresh Report", use_container_width=True):
            try:
                from src.report import generate_report
                generate_report(
                    result,
                    report_path,
                    narrative=narrative,
                )
                st.session_state["report_generated_at"] = datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M UTC"
                )
                st.success("Report generated successfully.")
                st.rerun()
            except Exception as exc:
                st.error(f"Report error: {exc}")

    with btn2:
        if report_exists:
            st.download_button(
                "Download report.html",
                data=report_path.read_bytes(),
                file_name="report.html",
                mime="text/html",
                use_container_width=True,
            )

    if report_exists:
        st.markdown(
            '<div style="font-size:0.75rem;color:#64748b;margin-top:10px">'
            'The report is a standalone HTML file that can be opened in any browser '
            'without a server. All data is embedded inline.'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── JSON export ───────────────────────────────────────────────────────────
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.82rem;font-weight:600;color:#1e2a3a;margin-bottom:10px">'
        'Export Findings (JSON)</div>',
        unsafe_allow_html=True,
    )
    findings_json = json.dumps([f.to_dict() for f in result.findings], indent=2)
    st.download_button(
        "Download findings.json",
        data=findings_json,
        file_name="findings.json",
        mime="application/json",
        use_container_width=False,
    )
    st.markdown(
        '<div style="font-size:0.75rem;color:#64748b;margin-top:6px">'
        f'{len(result.findings)} findings · Schema: finding_id, severity, category, '
        f'project_id, resource_id, title, detail, estimated_waste_usd, detected_at'
        f'</div>',
        unsafe_allow_html=True,
    )
