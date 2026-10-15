# Research Cloud Cost Anomaly & Waste Detector — Kiro Steering

## Project purpose

This is a Research IT FinOps demonstration tool that monitors cloud expenditure
across research projects. It detects cost anomalies, idle resources, missing
cost-allocation tags, and budget overruns, then surfaces findings in a Streamlit
dashboard, a standalone HTML report, and an optional Amazon Bedrock narrative.

## Architecture

The application follows a strict four-stage pipeline:

```
Collect → Transform → Analyse → Present
```

| Stage | Location | Responsibility |
|---|---|---|
| Collect | `src/collectors/` | Pull raw data from AWS or generate synthetic data |
| Transform | `src/transforms/` | Normalise raw data into `NormalizedDataset` |
| Analyse | `src/detectors/` | Run detectors; produce `Finding` objects |
| Present | `dashboard/`, `src/report.py` | Display or render findings |

Stages must not skip steps. Presentation layers must never call collectors
directly; they always receive a `PipelineResult` from `src/pipeline.py`.

## Coding standards

- Prefer simple, readable Python over unnecessary abstractions. Introduce a
  class or abstraction only when it makes the code meaningfully clearer or
  removes genuine repetition.
- Write reusable functions with complete type hints (`from __future__ import
  annotations` for Python 3.9 compatibility).
- Keep AWS-specific code behind the `AbstractCollector` interface in
  `src/collectors/`. Nothing outside `src/collectors/aws.py` should import
  boto3 except `src/bedrock.py`.
- Avoid hard-coded credentials or secrets. Use environment variables or AWS
  named profiles; never embed keys in source code or configuration files.
- Prefer configuration via environment variables or a config dataclass
  (`PipelineConfig`) over ad-hoc keyword arguments scattered through the code.

## Data integrity rules

- **All dashboard and report numbers must originate from `NormalizedDataset`
  fields or detector output.** Numbers must never be derived inside the
  presentation layer.
- **Analysis must be deterministic.** Detectors must produce the same findings
  for the same input every time. No random state, no LLM calls, no external
  service calls inside detectors.
- **Amazon Bedrock may only explain or summarise findings.** It must never
  invent cost figures, resource identifiers, savings estimates, or any other
  quantitative claim. All such numbers come from the detector pipeline.
- **Synthetic data must be clearly identified.** Any UI element, report
  section, or log message that displays demo-mode data must include a visible
  label such as "DEMO DATA — synthetic" or equivalent.

## Mode requirements

- **Demo mode** must run to completion without any AWS credentials, network
  access, or external services. `DemoCollector` is entirely self-contained.
- **AWS mode** must fail gracefully when permissions are unavailable:
  individual API calls should catch exceptions, log a warning, and return an
  empty result rather than crashing the pipeline.
- The pipeline must never hard-fail on a single missing permission; partial
  data collection is preferable to a full abort.

## Testing requirements

- Write tests for all analysis (detector) logic.
- Each detector must have unit tests with hand-crafted inputs and integration
  tests that run against demo-mode data and verify the injected anomalies are
  detected.
- Tests must not make real AWS API calls. Mock boto3 clients with
  `unittest.mock` or equivalent.
- Demo mode must be the default for tests; never require real credentials in CI.

## File layout

```
research-cost-detector/
├── requirements.txt          # pinned dependencies; no build tooling
├── main.py                   # CLI entry point
├── src/
│   ├── findings.py           # Finding dataclass, Severity/Category enums
│   ├── pipeline.py           # PipelineConfig, PipelineResult, run_pipeline()
│   ├── bedrock.py            # Bedrock Converse API wrapper (optional)
│   ├── report.py             # Standalone HTML report generator
│   ├── collectors/
│   │   ├── base.py           # AbstractCollector protocol
│   │   ├── demo.py           # Deterministic synthetic data generator
│   │   └── aws.py            # Real boto3 collectors
│   ├── detectors/
│   │   ├── anomaly.py        # Rolling z-score cost anomaly detector
│   │   ├── idle.py           # CPU/GPU idle resource detector
│   │   ├── tagging.py        # Missing cost-allocation tag detector
│   │   └── budget.py         # Budget overrun / forecast detector
│   ├── transforms/
│   │   └── normalizer.py     # normalize() → NormalizedDataset
│   └── templates/
│       └── report.html.j2    # Jinja2 HTML report template
├── dashboard/
│   └── app.py                # Streamlit dashboard
├── output/                   # findings.json + report.html (git-ignored)
└── tests/                    # one test file per source module
```

## Dependencies

All dependencies are pinned in `requirements.txt`. Do not introduce new
runtime dependencies without updating `requirements.txt` with a pinned version.
Prefer packages already in use (`pandas`, `numpy`, `plotly`, `jinja2`,
`boto3`, `streamlit`) over adding new ones for similar purposes.
