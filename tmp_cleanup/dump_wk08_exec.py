import json
data = json.load(open('tmp_cleanup/verify_reingest_out.json', encoding='utf-8'))
wk08 = next(r for r in data if r.get('week_label') == 'WK-08')

print("=== executive_summary_rfx_cost (text) ===")
print(repr(wk08['sections'].get('executive_summary_rfx_cost', '')))

print()
print("=== executive_summary_rfx_cost_struct ===")
print(json.dumps(wk08['sections'].get('executive_summary_rfx_cost_struct', {}), indent=2))
