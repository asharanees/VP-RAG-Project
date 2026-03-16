import sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from common.pdf_utils import read_pdf_pages
from common.structured_analyst import parse_structured_reports_from_pages

pages = read_pdf_pages(Path('TSA Sector Report February 26,2026.pdf').read_bytes())
reports = parse_structured_reports_from_pages(pages)
wk07 = next((r for r in reports if r.get('week_label')=='WK-07'), {})
rows = (((wk07.get('sections') or {}).get('delayed_rfps_struct') or {}).get('rows') or [])
print('week', wk07.get('week_label'))
print('count', len(rows))
if rows:
    print('start_idx', 1)
    print('start_row', rows[0])
    print('end_idx', len(rows))
    print('end_row', rows[-1])