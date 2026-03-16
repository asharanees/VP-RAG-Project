import sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from common.pdf_utils import read_pdf_pages
from common.structured_analyst import parse_structured_reports_from_pages

pages = read_pdf_pages(Path('TSA Sector Report February 26,2026.pdf').read_bytes())
reports = parse_structured_reports_from_pages(pages)
wk08 = next((r for r in reports if r.get('week_label')=='WK-08'), {})
struct = ((wk08.get('sections') or {}).get('delayed_rfps_struct') or {})
print('WK-08 delayed_rfps_struct rows count:', len(struct.get('rows', [])))
for idx, row in enumerate(struct.get('rows', [])[:5], 1):
    print(idx, row.get('sub_rfp_name'), '|', row.get('impacted_domain'), '|', row.get('status'), '|', row.get('pending_with'), '|', row.get('expense'), '|', row.get('gd_name'), '|', row.get('budget_sar'))