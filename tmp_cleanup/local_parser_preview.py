import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from common.pdf_utils import read_pdf_pages
from common.structured_analyst import parse_structured_reports_from_pages

pdf = Path('TSA Sector Report February 26,2026.pdf')
pages = read_pdf_pages(pdf.read_bytes())
reports = parse_structured_reports_from_pages(pages)
by = {r.get('week_label'): r for r in reports}
for wk in ['WK-07','WK-08']:
    row = by.get(wk, {})
    sec = row.get('sections', {})
    print('\n' + '='*90)
    print(wk)
    print('[gcto_updates]')
    print(sec.get('gcto_updates','<empty>'))
    for k in ['weekly_digest','key_projects_hot_topics','cost_optimization']:
        print(f'[{k} first 20 lines]')
        lines = (sec.get(k,'') or '').splitlines()
        print('\n'.join(lines[:20]) if lines else '<empty>')
    print('[rfx_status]')
    print(sec.get('rfx_status',{}))
    print('[delayed first 5]')
    for item in (sec.get('delayed_rfps',[]) or [])[:5]:
        print('-', item.get('initiative_name'), '|', item.get('budget_sar'))