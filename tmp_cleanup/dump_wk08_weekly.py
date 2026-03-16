import json
data = json.load(open('tmp_cleanup/verify_reingest_out.json', encoding='utf-8'))
wk08 = next(r for r in data if r.get('week_label') == 'WK-08')
print("=== weekly_digest ===")
print(wk08['sections'].get('weekly_digest', ''))
