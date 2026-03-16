import urllib.parse
from typing import Any, Dict

import boto3

from common.logger import get_logger
from common.pdf_utils import read_pdf_pages, sha256_hex
from common.settings import load_settings
from common.structured_analyst import (
    load_structured_reports_json,
    merge_structured_reports,
    parse_structured_reports_from_pages,
    save_structured_reports_json,
)

logger = get_logger(__name__)
settings = load_settings()
s3_client = boto3.client("s3", region_name=settings.aws_region)


def _download_s3_object(bucket: str, key: str) -> bytes:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    records = event.get("Records", [])
    if not records:
        return {"status": "ignored", "reason": "no_records"}

    record = records[0]
    bucket = record["s3"]["bucket"]["name"]
    key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

    if not key.lower().endswith(".pdf"):
        logger.info("Ignoring non-PDF object", extra={"extra": {"key": key}})
        return {"status": "ignored", "reason": "non_pdf"}

    content = _download_s3_object(bucket, key)
    document_id = sha256_hex(content)

    pages = read_pdf_pages(content)
    structured_reports = parse_structured_reports_from_pages(pages)

    if structured_reports:
        existing_structured = load_structured_reports_json(
            s3_client,
            bucket,
            settings.structured_reports_key,
        )
        merged_structured = merge_structured_reports(existing_structured, structured_reports)
        save_structured_reports_json(
            s3_client,
            bucket,
            settings.structured_reports_key,
            merged_structured,
            document_id=document_id,
            source_key=key,
        )

    logger.info(
        "PDF ingestion complete",
        extra={
            "extra": {
                "document_id": document_id,
                "bucket": bucket,
                "key": key,
                "structured_weeks": len(structured_reports),
                "structured_reports_key": settings.structured_reports_key,
            }
        },
    )
    return {"status": "ok", "document_id": document_id, "structured_weeks": len(structured_reports)}
