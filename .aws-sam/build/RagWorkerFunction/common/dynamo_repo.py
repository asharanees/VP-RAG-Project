from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Attr


class ChunkRepository:
    def __init__(self, table_name: str, region: str):
        self.table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._weeks_cache: Optional[List[Dict[str, str]]] = None
        self._weeks_cache_ts: Optional[datetime] = None

    def get_chunk(self, chunk_id: str) -> Optional[Dict]:
        response = self.table.get_item(Key={"chunk_id": chunk_id})
        item = response.get("Item")
        if not item:
            return None
        return _normalize_numbers(item)

    def batch_get_chunks(self, chunk_ids: List[str]) -> List[Dict]:
        if not chunk_ids:
            return []
        request_keys = [{"chunk_id": chunk_id} for chunk_id in chunk_ids]
        response = self.table.meta.client.batch_get_item(
            RequestItems={self.table.name: {"Keys": request_keys}}
        )
        items = response.get("Responses", {}).get(self.table.name, [])
        by_id = {item["chunk_id"]: _normalize_numbers(item) for item in items}
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]

    def put_chunk(
        self,
        *,
        chunk_id: str,
        document_id: str,
        chunk_index: int,
        page_number: int,
        chunk_text: str,
        source_s3_key: str,
        token_count: int,
        week: str = "",
        week_num: str = "",
        report_date: str = "",
        report_date_iso: str = "",
        section_family: str = "",
        major_section: str = "",
        section_title: str = "",
        section_header: str = "",
        section_level: str = "",
        header_position: str = "",
        parent_section_header: str = "",
        section_block_text: str = "",
        section_type: str = "",
        source_page: int = -1,
    ) -> None:
        self.table.put_item(
            Item={
                "chunk_id": chunk_id,
                "document_id": document_id,
                "chunk_index": chunk_index,
                "page_number": page_number,
                "chunk_text": chunk_text,
                "source_s3_key": source_s3_key,
                "token_count": token_count,
                "week": week,
                "week_num": week_num,
                "report_date": report_date,
                "report_date_iso": report_date_iso,
                "section_family": section_family,
                "major_section": major_section,
                "section_title": section_title,
                "section_header": section_header,
                "section_level": section_level,
                "header_position": header_position,
                "parent_section_header": parent_section_header,
                "section_block_text": section_block_text,
                "section_type": section_type,
                "source_page": source_page,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_document_marker(self, document_id: str) -> Optional[Dict]:
        return self.get_chunk(f"DOC#{document_id}")

    def put_document_marker(self, document_id: str, source_s3_key: str, token_count: int) -> None:
        self.table.put_item(
            Item={
                "chunk_id": f"DOC#{document_id}",
                "document_id": document_id,
                "chunk_index": -1,
                "page_number": -1,
                "chunk_text": "DOCUMENT_INGESTED",
                "source_s3_key": source_s3_key,
                "token_count": token_count,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_not_exists(chunk_id)",
        )

    def list_available_weeks(self) -> List[Dict[str, str]]:
        if self._weeks_cache and self._weeks_cache_ts:
            age_seconds = (datetime.now(timezone.utc) - self._weeks_cache_ts).total_seconds()
            if age_seconds < 300:
                return self._weeks_cache

        items: List[Dict[str, str]] = []
        scan_kwargs = {
            "ProjectionExpression": "chunk_id, #wk, report_date, report_date_iso",
            "ExpressionAttributeNames": {"#wk": "week"},
        }

        response = self.table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))

        while "LastEvaluatedKey" in response:
            response = self.table.scan(ExclusiveStartKey=response["LastEvaluatedKey"], **scan_kwargs)
            items.extend(response.get("Items", []))

        unique: Dict[str, Dict[str, str]] = {}
        for item in items:
            chunk_id = str(item.get("chunk_id", ""))
            if chunk_id.startswith("DOC#"):
                continue
            week = str(item.get("week", "") or "").strip()
            if not week:
                continue
            date = str(item.get("report_date", "") or "").strip()
            date_iso = str(item.get("report_date_iso", "") or "").strip()

            existing = unique.get(week)
            if not existing:
                unique[week] = {"report_date": date, "report_date_iso": date_iso}
                continue

            if date_iso and (not existing.get("report_date_iso") or date_iso > existing.get("report_date_iso", "")):
                unique[week] = {"report_date": date, "report_date_iso": date_iso}
            elif date and not existing.get("report_date"):
                unique[week]["report_date"] = date

        result = [
            {
                "week": week,
                "report_date": value.get("report_date", ""),
                "report_date_iso": value.get("report_date_iso", ""),
            }
            for week, value in unique.items()
        ]
        self._weeks_cache = result
        self._weeks_cache_ts = datetime.now(timezone.utc)
        return result

    def scan_chunks_by_weeks(self, weeks: List[str], limit: int = 40) -> List[Dict]:
        target_weeks = [week for week in weeks if week]
        if not target_weeks:
            return []

        items: List[Dict] = []
        response = self.table.scan(FilterExpression=Attr("week").is_in(target_weeks))
        items.extend(response.get("Items", []))

        while "LastEvaluatedKey" in response and len(items) < limit:
            response = self.table.scan(
                FilterExpression=Attr("week").is_in(target_weeks),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        normalized = [_normalize_numbers(item) for item in items]
        filtered = [item for item in normalized if not str(item.get("chunk_id", "")).startswith("DOC#")]
        return filtered[:limit]


def _normalize_numbers(obj: Dict) -> Dict:
    normalized = {}
    for key, value in obj.items():
        if isinstance(value, Decimal):
            if value % 1 == 0:
                normalized[key] = int(value)
            else:
                normalized[key] = float(value)
        else:
            normalized[key] = value
    return normalized
