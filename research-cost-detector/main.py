#!/usr/bin/env python3
"""
main.py — Research Cloud Cost Anomaly & Waste Detector CLI

Usage
-----
  python3 main.py --mode demo
  python3 main.py --mode demo --output-dir /tmp/rcd-output
  python3 main.py --mode aws --profile my-profile --region us-east-1
  python3 main.py --mode demo --no-bedrock
"""
import argparse
import json
import logging
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Research Cloud Cost Anomaly & Waste Detector",
    )
    p.add_argument(
        "--mode",
        choices=["demo", "aws"],
        default="demo",
        help="Data source mode: 'demo' uses synthetic data; 'aws' uses real boto3 collectors.",
    )
    p.add_argument(
        "--output-dir",
        default="output",
        metavar="DIR",
        help="Directory to write findings.json and report.html (default: ./output).",
    )
    p.add_argument(
        "--no-bedrock",
        action="store_true",
        default=False,
        help="Skip Amazon Bedrock narrative generation.",
    )
    p.add_argument(
        "--profile",
        default=None,
        metavar="AWS_PROFILE",
        help="AWS profile name (aws mode only).",
    )
    p.add_argument(
        "--region",
        default="us-east-1",
        metavar="AWS_REGION",
        help="AWS region (aws mode only, default: us-east-1).",
    )
    p.add_argument(
        "--tag-key",
        default="ProjectID",
        metavar="TAG_KEY",
        help="Tag key used to identify research projects (aws mode only).",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log verbosity level.",
    )
    return p


def main(argv: "list[str] | None" = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("rcd")

    # ── Import pipeline ───────────────────────────────────────────────────────
    from src.pipeline import PipelineConfig, run_pipeline

    config = PipelineConfig(
        mode=args.mode,
        output_dir=Path(args.output_dir),
        aws_profile=args.profile,
        aws_region=args.region,
        aws_tag_key=args.tag_key,
    )

    logger.info("Starting pipeline in %s mode…", args.mode.upper())
    try:
        result = run_pipeline(mode=args.mode, config=config)
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        return 1

    kpis = result.kpis()
    logger.info("Pipeline complete. %d findings, $%.2f estimated waste.",
                kpis["finding_count"], kpis["total_estimated_waste_usd"])

    # ── Console summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Research Cloud Cost Anomaly & Waste Detector")
    print("=" * 60)
    print(f"  Mode             : {args.mode.upper()}")
    print(f"  Total spend      : ${kpis['total_spend_usd']:>12,.2f}")
    print(f"  Findings         : {kpis['finding_count']}")
    print(f"    CRITICAL       : {kpis['critical_count']}")
    print(f"    HIGH           : {kpis['high_count']}")
    print(f"    MEDIUM         : {kpis['medium_count']}")
    print(f"    LOW            : {kpis['low_count']}")
    print(f"  Est. waste (USD) : ${kpis['total_estimated_waste_usd']:>12,.2f}")
    print(f"  findings.json    : {Path(args.output_dir) / 'findings.json'}")

    # ── Optional Bedrock narrative ────────────────────────────────────────────
    narrative: str | None = None
    if not args.no_bedrock:
        try:
            from src.bedrock import generate_narrative

            logger.info("Requesting Bedrock narrative…")
            narrative = generate_narrative(result.findings)
            if narrative:
                logger.info("Bedrock narrative generated (%d chars).", len(narrative))
                print("\n--- Bedrock Narrative ---")
                print(narrative)
            else:
                logger.info("Bedrock narrative skipped (unavailable).")
        except ImportError:
            pass  # bedrock.py not yet available

    # ── HTML report ───────────────────────────────────────────────────────────
    try:
        from src.report import generate_report

        report_path = Path(args.output_dir) / "report.html"
        generate_report(result, report_path, narrative=narrative)
        print(f"  report.html      : {report_path}")
    except ImportError:
        pass  # report.py not yet available
    except Exception as exc:
        logger.warning("HTML report generation failed: %s", exc)

    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
