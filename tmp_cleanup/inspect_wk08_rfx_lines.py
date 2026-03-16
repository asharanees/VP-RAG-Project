import sys, re
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from common.pdf_utils import read_pdf_pages
from common.structured_analyst import _group_pages_by_week, _extract_sections_by_order

pages = read_pdf_pages(Path('TSA Sector Report February 26,2026.pdf').read_bytes())
by_week = _group_pages_by_week(pages)
week_text = '\n'.join((by_week.get('WK-08') or {}).get('pages', []))
sec = _extract_sections_by_order(week_text)
rfx = sec.get('rfx_status','')
print('rfx chars', len(rfx))
lines = [' '.join(l.split()).strip() for l in rfx.splitlines() if l.strip()]
print('rfx lines', len(lines))
for i,l in enumerate(lines[:120],1):
    if 'delayed' in l.lower() or 'pending' in l.lower() or i<25:
        print(f'{i:03}: {l}')
print('lines_with_delayed', sum(1 for l in lines if 'delayed' in l.lower()))