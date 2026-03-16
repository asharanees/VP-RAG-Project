import json
data = json.load(open('tmp_cleanup/verify_reingest_out.json', encoding='utf-8'))
wk08 = next(r for r in data if r.get('week_label') == 'WK-08')
rfx = wk08['sections'].get('rfx_status') or {}
rfx_struct = wk08['sections'].get('rfx_status_struct') or {}

print("=== rfx_status (flat) ===")
for k, v in rfx.items():
    print(f"  {k}: {v}")

print()
print("=== rfx_status_struct ===")
print(json.dumps(rfx_struct, indent=2))
