import json, sys
sys.path.insert(0,'src')

data = json.load(open('tmp_cleanup/s3_structured_reports.json', encoding='utf-8'))
reports = data.get('reports', data) if isinstance(data, dict) else data
print(f"updated_at: {data.get('updated_at','?')}")
print(f"Total weeks: {len(reports)}\n")

SECTIONS = ['gcto_updates','weekly_digest','key_projects_hot_topics',
            'cost_optimization','executive_summary_rfx_cost','rfx_status','delayed_rfps']

for r in reports:
    wk = r.get('week_label','?')
    secs = r.get('sections', {})
    rfx = secs.get('rfx_status', {}) or {}
    delayed = secs.get('delayed_rfps', []) or []
    gcto = secs.get('gcto_updates','')
    wd = secs.get('weekly_digest','')
    kp = secs.get('key_projects_hot_topics','')
    co = secs.get('cost_optimization','')
    ex = secs.get('executive_summary_rfx_cost','')

    print(f"{'='*60}")
    print(f"  {wk}  (date: {r.get('report_date','?')})")
    print(f"  RFx: recv={rfx.get('total_received')} appr={rfx.get('total_approved')} "
          f"prog={rfx.get('total_in_progress')} cf={rfx.get('total_cf_projects')}")
    print(f"  Delayed rows: {len(delayed)}")
    print(f"  GCTO ({len(gcto)} chars): {'OK - structured' if 'Status:' in gcto else 'MISSING/UNSTRUCTURED' if gcto else 'EMPTY'}")
    print(f"  Weekly Digest ({len(wd)} chars): {'OK' if len(wd)>100 else 'SPARSE' if wd else 'EMPTY'}")
    print(f"  Key Projects ({len(kp)} chars): {'OK' if len(kp)>100 else 'SPARSE' if kp else 'EMPTY'}")
    print(f"  Cost Opt ({len(co)} chars): {'OK' if co else 'EMPTY'}")
    print(f"  Exec Summary ({len(ex)} chars): {'OK' if ex else 'EMPTY'}")

    # Show top 3 delayed rows
    if delayed:
        print(f"  Top delayed:")
        for row in sorted(delayed, key=lambda x: x.get('budget_sar') or 0, reverse=True)[:3]:
            print(f"    - {row.get('sub_rfp_name','?')[:50]} | SAR {row.get('budget_sar')} | {row.get('expense_type')} | {row.get('pending_with')}")

print(f"\n{'='*60}")
print("SUMMARY OF GAPS:")
for r in reports:
    wk = r.get('week_label','?')
    secs = r.get('sections', {})
    issues = []
    rfx = secs.get('rfx_status', {}) or {}
    if not rfx.get('total_received'): issues.append('rfx_metrics_missing')
    if not secs.get('delayed_rfps'): issues.append('no_delayed_rows')
    if not secs.get('gcto_updates'): issues.append('gcto_empty')
    if not secs.get('weekly_digest'): issues.append('digest_empty')
    if not secs.get('key_projects_hot_topics'): issues.append('key_projects_empty')
    if issues:
        print(f"  {wk}: {', '.join(issues)}")
    else:
        print(f"  {wk}: ALL OK")
