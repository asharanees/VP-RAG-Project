"""
verify_reingest.py — Local verification script for structured parsing accuracy.

Steps:
  1. Download the source PDF from S3
  2. Extract pages via pdf_utils
  3. Run parse_structured_reports_from_pages locally
  4. Print a per-week section fill report
  5. Optionally re-upload the PDF to S3 to trigger Lambda re-ingestion
"""
import sys
import os
import json
import argparse

# Allow imports from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3
from src.common.settings import load_settings
from src.common.pdf_utils import read_pdf_pages
from src.common.structured_analyst import parse_structured_reports_from_pages

SECTION_KEYS = [
    "gcto_updates",
    "weekly_digest",
    "key_projects_hot_topics",
    "cost_optimization",
    "executive_summary_rfx_cost",
    "rfx_status",
    "delayed_rfps",
]


def _fill_status(value) -> str:
    """Return a short fill indicator for a section value."""
    if value is None:
        return "MISSING"
    if isinstance(value, list):
        return f"OK ({len(value)} rows)" if value else "EMPTY"
    if isinstance(value, dict):
        non_null = sum(1 for v in value.values() if v not in (None, "", [], {}))
        return f"OK ({non_null}/{len(value)} fields)" if non_null else "EMPTY"
    text = str(value).strip()
    if not text:
        return "EMPTY"
    words = len(text.split())
    return f"OK ({words} words)"


def _check_assertions(reports):
    """Run assertions and return list of failure messages."""
    failures = []
    weeks_found = [r.get("week_label") for r in reports if r.get("week_label")]
    if not weeks_found:
        failures.append("FAIL: No weeks detected at all")
        return failures

    for report in reports:
        wk = report.get("week_label", "?")
        sections = report.get("sections", {})

        rfx = sections.get("rfx_status") or {}
        if rfx.get("total_received") is None:
            failures.append(f"WARN [{wk}]: rfx_status.total_received is null")

        delayed = sections.get("delayed_rfps") or []
        if not delayed:
            failures.append(f"WARN [{wk}]: delayed_rfps is empty")

    return failures


def download_pdf(s3_client, bucket: str, key: str) -> bytes:
    print(f"  Downloading s3://{bucket}/{key} ...")
    resp = s3_client.get_object(Bucket=bucket, Key=key)
    data = resp["Body"].read()
    print(f"  Downloaded {len(data):,} bytes")
    return data


def print_report(reports):
    col_w = 34
    header = f"{'Week':<10}" + "".join(f"{k:<{col_w}}" for k in SECTION_KEYS)
    print("\n" + "=" * (10 + col_w * len(SECTION_KEYS)))
    print(header)
    print("-" * (10 + col_w * len(SECTION_KEYS)))

    for report in reports:
        wk = report.get("week_label", "?")
        sections = report.get("sections", {})
        row = f"{wk:<10}"
        for key in SECTION_KEYS:
            val = sections.get(key)
            row += f"{_fill_status(val):<{col_w}}"
        print(row)

    print("=" * (10 + col_w * len(SECTION_KEYS)))
    print(f"\nTotal weeks parsed: {len(reports)}")


def main():
    parser = argparse.ArgumentParser(description="Verify structured parsing against real PDF")
    parser.add_argument("--local-pdf", metavar="PATH",
                        help="Use a local PDF file instead of downloading from S3")
    parser.add_argument("--reingest", action="store_true",
                        help="Re-upload PDF to S3 to trigger Lambda re-ingestion after verification")
    parser.add_argument("--save-json", metavar="PATH",
                        help="Save parsed reports to a local JSON file for inspection")
    parser.add_argument("--bucket", help="Override S3 source bucket")
    parser.add_argument("--key", help="Override S3 PDF key")
    args = parser.parse_args()

    settings = load_settings()
    bucket = args.bucket or settings.source_bucket_name
    key = args.key or settings.source_pdf_key

    if args.local_pdf:
        import pathlib
        pdf_path = pathlib.Path(args.local_pdf)
        print(f"\n[1-2] Reading local PDF: {pdf_path}")
        pdf_bytes = pdf_path.read_bytes()
        print(f"  Read {len(pdf_bytes):,} bytes")
        s3 = None
    else:
        print(f"\n[1] Connecting to S3 (region={settings.aws_region})")
        s3 = boto3.client("s3", region_name=settings.aws_region)
        print(f"\n[2] Downloading PDF")
        pdf_bytes = download_pdf(s3, bucket, key)

    print(f"\n[3] Extracting pages from PDF")
    pages = read_pdf_pages(pdf_bytes)
    print(f"  Extracted {len(pages)} pages")

    print(f"\n[4] Running parse_structured_reports_from_pages")
    reports = parse_structured_reports_from_pages(pages)
    print(f"  Parsed {len(reports)} week records")

    print(f"\n[5] Section fill report")
    print_report(reports)

    print(f"\n[6] Assertions")
    failures = _check_assertions(reports)
    if failures:
        for msg in failures:
            print(f"  {msg}")
    else:
        print("  All assertions passed.")

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as fh:
            json.dump(reports, fh, ensure_ascii=False, indent=2)
        print(f"\n  Saved parsed JSON to: {args.save_json}")

    if args.reingest:
        if s3 is None:
            print(f"\n[7] Connecting to S3 for re-upload (region={settings.aws_region})")
            s3 = boto3.client("s3", region_name=settings.aws_region)
        print(f"\n[7] Re-uploading PDF to s3://{bucket}/{key} to trigger Lambda re-ingestion")
        s3.put_object(Bucket=bucket, Key=key, Body=pdf_bytes, ContentType="application/pdf")
        print("  Re-upload complete. Lambda should trigger automatically via S3 event.")

    print()
    return 0 if not any(f.startswith("FAIL") for f in failures) else 1


if __name__ == "__main__":
    sys.exit(main())
