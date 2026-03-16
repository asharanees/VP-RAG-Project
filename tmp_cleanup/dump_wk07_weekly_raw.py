import sys
sys.path.insert(0, 'src')
from common.structured_analyst import _extract_sections_by_order, _group_pages_by_week, _clean_section_text
from common.pdf_utils import read_pdf_pages

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

by_week = _group_pages_by_week(pages)
wk07 = by_week.get('WK-07', {})
week_text = "\n".join(wk07.get('pages', []))
sections = _extract_sections_by_order(week_text)

raw = sections.get('weekly_digest', '')
print("=== RAW weekly_digest (first 800 chars) ===")
print(repr(raw[:800]))
print()
print("=== CLEANED ===")
print(_clean_section_text('weekly_digest', raw)[:800] or '[EMPTY]')
