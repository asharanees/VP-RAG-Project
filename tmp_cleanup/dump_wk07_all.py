import sys
sys.path.insert(0, 'src')
from common.structured_analyst import parse_structured_reports_from_pages
from common.pdf_utils import read_pdf_pages

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

reports = parse_structured_reports_from_pages(pages)
wk07 = next((r for r in reports if r.get('week_label') == 'WK-07'), None)
if not wk07:
    print("WK-07 not found")
    sys.exit(1)

sections = wk07['sections']

print("=== GCTO Updates ===")
print(sections.get('gcto_updates', '') or '[EMPTY]')
print()
print("=== Weekly Digest ===")
wd = sections.get('weekly_digest', '') or ''
print(wd[:1500] or '[EMPTY]')
print()
print("=== Key Projects & Hot Topics ===")
kp = sections.get('key_projects_hot_topics', '') or ''
print(kp[:1500] or '[EMPTY]')
print()
print("=== Cost Optimization ===")
print(sections.get('cost_optimization', '') or '[EMPTY]')
print()
print("=== Executive Summary ===")
print(sections.get('executive_summary_rfx_cost', '') or '[EMPTY]')
print()
print("=== RFx Status ===")
rfx = sections.get('rfx_status', {})
print(f"  total_received:    {rfx.get('total_received')}")
print(f"  total_approved:    {rfx.get('total_approved')}")
print(f"  total_in_progress: {rfx.get('total_in_progress')}")
print(f"  total_cf_projects: {rfx.get('total_cf_projects')}")
print()
print("=== Delayed RFPs (count) ===")
rows = sections.get('delayed_rfps', [])
print(f"  {len(rows)} rows")
for r in rows[:5]:
    print(f"  - {r.get('sub_rfp_name','')[:60]} | {r.get('expense')} | {r.get('budget_sar')}")
