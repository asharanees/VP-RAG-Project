import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from src.common.pdf_utils import read_pdf_pages
from src.common.structured_analyst import (
    _group_pages_by_week, _extract_sections_by_order, _clean_section_text
)

pages = read_pdf_pages(Path("TSA Sector Report February 26,2026.pdf").read_bytes())
by_week = _group_pages_by_week(pages)
week_text = "\n".join((by_week.get("WK-08") or {}).get("pages", []))
section_map = _extract_sections_by_order(week_text)
raw = section_map.get("delayed_rfps", "")
cleaned = _clean_section_text("delayed_rfps", raw)

print("=== CLEANED LINES (first 10) ===")
for i, line in enumerate(cleaned.splitlines()[:10]):
    print(f"{i:2}: [{line}]")
