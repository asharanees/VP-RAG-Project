import sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from common.pdf_utils import read_pdf_pages
from common.structured_analyst import parse_structured_reports_from_pages

TEXT_SECTIONS = [
    'gcto_updates',
    'weekly_digest',
    'key_projects_hot_topics',
    'cost_optimization',
    'executive_summary_rfx_cost',
]

pages = read_pdf_pages(Path('TSA Sector Report February 26,2026.pdf').read_bytes())
reports = parse_structured_reports_from_pages(pages)
wk07 = next((r for r in reports if r.get('week_label') == 'WK-07'), {})
sections = wk07.get('sections') or {}

print('week', wk07.get('week_label'))
print('report_date', wk07.get('report_date'))
print('--- text sections ---')
for sec in TEXT_SECTIONS:
    text = (sections.get(sec) or '').strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    print(f'[{sec}] lines={len(lines)}')
    if lines:
        print('  start:', lines[0])
        print('  end  :', lines[-1])

print('--- rfx_status ---')
rfx = sections.get('rfx_status') or {}
print(rfx)

print('--- rfx_status_struct overview ---')
rfxs = sections.get('rfx_status_struct') or {}
print((rfxs.get('overview') or {}))
print('pib_total', ((rfxs.get('pib_not_received_by_rfx') or {}).get('total')))
print('mpa_total', ((rfxs.get('direct_value_mpa_projects_status') or {}).get('total')))

print('--- executive_summary_rfx_cost_struct ---')
execs = sections.get('executive_summary_rfx_cost_struct') or {}
print(execs)

print('--- delayed_rfps_struct ---')
delayed = sections.get('delayed_rfps_struct') or {}
rows = delayed.get('rows') or []
print('count', len(rows))
if rows:
    print('start_row', rows[0])
    print('end_row', rows[-1])