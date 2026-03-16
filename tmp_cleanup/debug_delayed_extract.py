import sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from common.pdf_utils import read_pdf_pages
from common.structured_analyst import _group_pages_by_week, _extract_sections_by_order, _clean_section_text

pages = read_pdf_pages(Path('TSA Sector Report February 26,2026.pdf').read_bytes())
by_week = _group_pages_by_week(pages)
week_text = '\n'.join((by_week.get('WK-08') or {}).get('pages', []))
sec = _extract_sections_by_order(week_text)
print('keys:', list(sec.keys()))
raw = sec.get('delayed_rfps','')
print('raw delayed first 1200:')
print(raw[:1200])
print('\ncleaned delayed first 1200:')
print(_clean_section_text('delayed_rfps', raw)[:1200])