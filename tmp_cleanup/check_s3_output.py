import json
data = json.load(open('tmp_cleanup/s3_structured_reports.json', encoding='utf-8'))
reports = data.get('reports', data) if isinstance(data, dict) else data
print(f"updated_at: {data.get('updated_at', 'N/A') if isinstance(data, dict) else 'N/A'}")
print(f"Total weeks: {len(reports)}")
for r in reports:
    wk = r.get('week_label', '?')
    s = r.get('sections', {})
    gcto = len((s.get('gcto_updates') or '').split())
    wd = len((s.get('weekly_digest') or '').split())
    kp = len((s.get('key_projects_hot_topics') or '').split())
    delayed = len(s.get('delayed_rfps') or [])
    rfx_recv = (s.get('rfx_status') or {}).get('total_received')
    print(f"  {wk}: gcto={gcto}w  weekly={wd}w  keyproj={kp}w  delayed={delayed}rows  rfx_recv={rfx_recv}")
