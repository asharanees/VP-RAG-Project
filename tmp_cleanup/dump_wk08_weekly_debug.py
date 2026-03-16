import sys
sys.path.insert(0, 'src')
from common.structured_analyst import (
    _extract_sections_by_order, _group_pages_by_week,
    _clean_section_text, _split_weekly_keyprojects_boundary
)
from common.pdf_utils import read_pdf_pages

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

by_week = _group_pages_by_week(pages)
wk08 = by_week['WK-08']
week_text = "\n".join(wk08['pages'])
sections = _extract_sections_by_order(week_text)

raw_weekly = sections.get('weekly_digest', '')
cleaned = _clean_section_text('weekly_digest', raw_weekly)

print("=== After _clean_section_text ===")
print(cleaned[:2000])
print("\n=== After _split_weekly_keyprojects_boundary ===")
head, tail = _split_weekly_keyprojects_boundary(cleaned)
print("HEAD:")
print(head[:1500])
print("\nTAIL (goes to key_projects):")
print(tail[:500])
