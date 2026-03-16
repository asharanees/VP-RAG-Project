import sys
sys.path.insert(0, 'src')
from common.structured_analyst import (
    _extract_sections_by_order, _group_pages_by_week,
    _clean_section_text, _split_weekly_keyprojects_boundary,
    parse_structured_reports_from_pages
)
from common.pdf_utils import read_pdf_pages

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

by_week = _group_pages_by_week(pages)
wk07 = by_week.get('WK-07', {})
week_text = "\n".join(wk07.get('pages', []))
sections = _extract_sections_by_order(week_text)

raw = sections.get('weekly_digest', '')
cleaned = _clean_section_text('weekly_digest', raw)

print("=== CLEANED weekly_digest (full) ===")
print(cleaned)
print()
print("=== After _split_weekly_keyprojects_boundary ===")
head, tail = _split_weekly_keyprojects_boundary(cleaned)
print("HEAD (stays as weekly_digest):")
print(head[:1000] or '[EMPTY]')
print()
print("TAIL (goes to key_projects):")
print(tail[:300] or '[NONE]')
