import json
data = json.load(open('tmp_cleanup/verify_reingest_out.json', encoding='utf-8'))
wk08 = next(r for r in data if r.get('week_label') == 'WK-08')
# Find the raw weekly_digest section before cleaning
# Re-run extraction to see raw
import sys
sys.path.insert(0, 'src')
from common.structured_analyst import _extract_sections_by_order, _group_pages_by_week
from common.pdf_utils import read_pdf_pages
import os

# Load pages from the PDF
pdf_path = next((f for f in os.listdir('.') if f.endswith('.pdf')), None)
print(f"PDF: {pdf_path}")
with open(pdf_path, 'rb') as f:
    pages = read_pdf_pages(f.read())
by_week = _group_pages_by_week(pages)
wk08_record = by_week.get('WK-08', {})
week_text = "\n".join(wk08_record.get("pages", []))
sections = _extract_sections_by_order(week_text)
raw = sections.get("weekly_digest", "")
print("=== RAW weekly_digest (first 3000 chars) ===")
print(raw[:3000])
