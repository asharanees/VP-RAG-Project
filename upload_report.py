#!/usr/bin/env python3
"""
Upload a PDF report to the AI Reporting Assistant.

Usage:
    python upload_report.py <path-to-pdf>

Requirements:
    pip install boto3

No AWS console needed. Whoever runs this needs AWS credentials configured
(aws configure) with s3:PutObject permission on the source bucket.
"""

import os
import sys

try:
    import boto3
except ImportError:
    print("ERROR: boto3 not installed. Run: pip install boto3")
    sys.exit(1)

BUCKET = "vp-rag-project-source-980874804229-us-east-1"
REGION = "us-east-1"


def upload(pdf_path: str) -> None:
    if not os.path.isfile(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        sys.exit(1)

    if not pdf_path.lower().endswith(".pdf"):
        print("ERROR: Only PDF files are accepted.")
        sys.exit(1)

    filename = os.path.basename(pdf_path)
    s3_key = f"reports/{filename}"
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)

    print(f"Uploading: {filename} ({file_size_mb:.1f} MB) → s3://{BUCKET}/{s3_key}")

    s3 = boto3.client("s3", region_name=REGION)
    s3.upload_file(pdf_path, BUCKET, s3_key, ExtraArgs={"ContentType": "application/pdf"})

    print(f"Done. Report will be processed automatically in ~30 seconds.")
    print(f"Your team can now ask the WhatsApp bot about it.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python upload_report.py <path-to-pdf>")
        print('Example: python upload_report.py "TSA Sector Report March 11.pdf"')
        sys.exit(1)

    upload(sys.argv[1])
