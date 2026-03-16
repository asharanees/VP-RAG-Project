import sys
sys.path.insert(0, 'src')
from common.structured_analyst import (
    _extract_sections_by_order, _group_pages_by_week,
    _clean_section_text, parse_structured_reports_from_pages
)
from common.pdf_utils import read_pdf_pages

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

reports = parse_structured_reports_from_pages(pages)
wk08 = next(r for r in reports if r.get('week_label') == 'WK-08')
print("=== weekly_digest ===")
print(wk08['sections'].get('weekly_digest', ''))
