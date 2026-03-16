import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from src.common.pdf_utils import read_pdf_pages
from src.common.structured_analyst import (
    _group_pages_by_week, _extract_delayed_block_fallback, _parse_delayed_rows
)

pages = read_pdf_pages(Path("TSA Sector Report February 26,2026.pdf").read_bytes())
by_week = _group_pages_by_week(pages)
week_text = "\n".join((by_week.get("WK-08") or {}).get("pages", []))

fallback_block = _extract_delayed_block_fallback(week_text)
print("=== FALLBACK BLOCK ===")
for i, line in enumerate(fallback_block.splitlines()):
    print(f"{i:3}: {line}")

print()
rows = _parse_delayed_rows(fallback_block)
print(f"=== FALLBACK ROWS ({len(rows)}) ===")
for i, row in enumerate(rows):
    print(f"[{i+1}] name={row.get('sub_rfp_name')} | domain={row.get('impacted_domain')} | budget={row.get('budget_sar')}")
