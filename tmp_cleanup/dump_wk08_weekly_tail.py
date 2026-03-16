import sys
sys.path.insert(0, 'src')
from common.structured_analyst import (
    _extract_sections_by_order, _group_pages_by_week,
    _clean_section_text, _split_weekly_keyprojects_boundary,
    _extract_weekly_digest_tail_from_key_projects, _coalesce_text
)
from common.pdf_utils import read_pdf_pages

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

by_week = _group_pages_by_week(pages)
wk08 = by_week['WK-08']
week_text = "\n".join(wk08['pages'])
sections = _extract_sections_by_order(week_text)

raw_weekly = sections.get('weekly_digest', '')
raw_key = sections.get('key_projects_hot_topics', '')

cleaned_weekly = _clean_section_text('weekly_digest', raw_weekly)
cleaned_key = _clean_section_text('key_projects_hot_topics', raw_key)

head, key_tail = _split_weekly_keyprojects_boundary(cleaned_weekly)
if key_tail:
    cleaned_weekly = head
    cleaned_key = _coalesce_text(key_tail, cleaned_key)

print("=== satellite/ntn in weekly?", "satellite/ ntn" in cleaned_weekly.lower())
digest_tail, key_main = _extract_weekly_digest_tail_from_key_projects(cleaned_key)
print("=== digest_tail ===")
print(repr(digest_tail[:300]))
print("=== final weekly after coalesce ===")
final = _coalesce_text(cleaned_weekly, digest_tail) if digest_tail else cleaned_weekly
# show last 300 chars
print(final[-300:])
