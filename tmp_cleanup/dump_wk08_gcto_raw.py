import sys
sys.path.insert(0, 'src')
from common.structured_analyst import _extract_sections_by_order, _group_pages_by_week, _clean_section_text
from common.pdf_utils import read_pdf_pages

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

by_week = _group_pages_by_week(pages)
wk08 = by_week['WK-08']
week_text = "\n".join(wk08['pages'])
sections = _extract_sections_by_order(week_text)

raw_gcto = sections.get('gcto_updates', '')
print("=== RAW gcto_updates ===")
print(repr(raw_gcto[:500]))
print()
print("=== CLEANED gcto_updates ===")
print(_clean_section_text('gcto_updates', raw_gcto)[:500])
