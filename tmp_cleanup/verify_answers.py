import sys, json
sys.path.insert(0, 'src')
data = json.load(open('tmp_cleanup/s3_structured_reports.json', encoding='utf-8'))
reports = data.get('reports', data) if isinstance(data, dict) else data

print("=== RFx metrics per week ===")
for r in reports:
    wk = r.get('week_label')
    rfx = r['sections'].get('rfx_status', {}) or {}
    print(f"  {wk}: received={rfx.get('total_received')}, approved={rfx.get('total_approved')}, "
          f"in_progress={rfx.get('total_in_progress')}, cf={rfx.get('total_cf_projects')}")

print("\n=== Weekly summary scope (last 4 weeks = WK-07 to WK-10) ===")
target_weeks = ['WK-07','WK-08','WK-09','WK-10']
for r in reports:
    wk = r.get('week_label')
    if wk not in target_weeks:
        continue
    wd = r['sections'].get('weekly_digest','')
    kp = r['sections'].get('key_projects_hot_topics','')
    co = r['sections'].get('cost_optimization','')
    print(f"\n  {wk}:")
    print(f"    weekly_digest ({len(wd)} chars): {wd[:120]!r}")
    print(f"    key_projects  ({len(kp)} chars): {kp[:120]!r}")
    print(f"    cost_opt      ({len(co)} chars): {co[:80]!r}")

print("\n=== Delayed RFPs count per week ===")
for r in reports:
    wk = r.get('week_label')
    rows = r['sections'].get('delayed_rfps', []) or []
    print(f"  {wk}: {len(rows)} rows")
