import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from src.common.pdf_utils import read_pdf_pages
from src.common.structured_analyst import _group_pages_by_week

pages = read_pdf_pages(Path("TSA Sector Report February 26,2026.pdf").read_bytes())
by_week = _group_pages_by_week(pages)
wk08 = by_week.get("WK-08") or {}
wk08_pages = wk08.get("pages", [])
print(f"WK-08 has {len(wk08_pages)} pages")
for i, page in enumerate(wk08_pages):
    print(f"\n=== PAGE {i+1} (first 60 chars per line) ===")
    for line in page.splitlines():
        if line.strip():
            print(f"  {line[:120]}")
