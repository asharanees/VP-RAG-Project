import json
data = json.load(open('tmp_cleanup/verify_reingest_out.json', encoding='utf-8'))
wk08 = next(r for r in data if r.get('week_label') == 'WK-08')
rows = wk08['sections'].get('delayed_rfps') or []
print(f'Total rows: {len(rows)}')
print()
for i, row in enumerate(rows):
    print(f"[{i+1}] sub_rfp_name:    {row.get('sub_rfp_name')}")
    print(f"     impacted_domain: {row.get('impacted_domain')}")
    print(f"     status:          {row.get('status')}")
    print(f"     pending_with:    {row.get('pending_with')}")
    print(f"     expense:         {row.get('expense')}")
    print(f"     gd_name:         {row.get('gd_name')}")
    print(f"     budget_sar:      {row.get('budget_sar')}")
    print()
