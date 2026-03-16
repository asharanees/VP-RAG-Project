import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from src.common.pdf_utils import read_pdf_pages
from src.common.structured_analyst import (
    _group_pages_by_week, _extract_sections_by_order, _clean_section_text, _parse_delayed_rows
)

pages = read_pdf_pages(Path("TSA Sector Report February 26,2026.pdf").read_bytes())
by_week = _group_pages_by_week(pages)
week_text = "\n".join((by_week.get("WK-08") or {}).get("pages", []))
section_map = _extract_sections_by_order(week_text)

rfx_raw = section_map.get("rfx_status", "")
print("=== RFX RAW (last 50 lines) ===")
rfx_lines = rfx_raw.splitlines()
for i, line in enumerate(rfx_lines[-50:]):
    print(f"{len(rfx_lines)-50+i:3}: {line[:120]}")

print()
rows = _parse_delayed_rows(rfx_raw)
print(f"=== DELAYED ROWS FROM RFX ({len(rows)}) ===")
for i, row in enumerate(rows):
    print(f"[{i+1}] name={row.get('sub_rfp_name')} | domain={row.get('impacted_domain')} | budget={row.get('budget_sar')}")
