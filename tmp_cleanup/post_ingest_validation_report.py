import json
import boto3
from pathlib import Path

bucket='vp-rag-project-source-980874804229-us-east-1'
key='structured/structured_reports.json'
pre_path=Path('tmp_cleanup/pre_reingest_snapshot.json')
pre=json.loads(pre_path.read_text(encoding='utf-8')) if pre_path.exists() else {}

s3=boto3.client('s3', region_name='us-east-1')
obj=s3.get_object(Bucket=bucket, Key=key)
data=json.loads(obj['Body'].read().decode('utf-8'))
reports=data.get('reports', data if isinstance(data,list) else [])
by={r.get('week_label'):r for r in reports if r.get('week_label')}


def first_lines(text, n=20):
    lines=(text or '').splitlines()
    return '\n'.join(lines[:n]) if lines else '<empty>'

print('POST-INGEST CHECKS')
print('='*100)
for wk in ['WK-08','WK-07']:
    row=by.get(wk,{})
    sec=(row.get('sections') or {})
    print(f'\n### {wk}')
    print('1) gcto_updates')
    print(sec.get('gcto_updates','<empty>'))
    print('\n2) weekly_digest (first 20 lines)')
    print(first_lines(sec.get('weekly_digest',''),20))
    print('\n3) key_projects_hot_topics (first 20 lines)')
    print(first_lines(sec.get('key_projects_hot_topics',''),20))
    print('\n4) cost_optimization (first 20 lines)')
    print(first_lines(sec.get('cost_optimization',''),20))
    print('\n5) rfx_status extracted metrics')
    print((sec.get('rfx_status') or {}))
    print('\n6) delayed_rfps (first 5 rows)')
    rows=(sec.get('delayed_rfps') or [])[:5]
    print(rows if rows else '<empty>')

print('\n' + '='*100)
print('BEFORE/AFTER WK-08')
pre_wk08=(pre.get('WK-08') or {})
post_wk08=((by.get('WK-08',{}).get('sections') or {}))

for section in ['gcto_updates','weekly_digest','cost_optimization']:
    before=pre_wk08.get(section,'')
    after=post_wk08.get(section,'')
    print(f'\n[{section}] BEFORE len={len(before or "")})')
    print(first_lines(before,20))
    print(f'[{section}] AFTER len={len(after or "")})')
    print(first_lines(after,20))

print('\n' + '='*100)
print('VALIDATION FLAGS')

gcto_after=(post_wk08.get('gcto_updates') or '').lower()
weekly_after=(post_wk08.get('weekly_digest') or '').lower()
cost_after=(post_wk08.get('cost_optimization') or '').lower()
delayed_first=((post_wk08.get('delayed_rfps') or [{}])[0] if (post_wk08.get('delayed_rfps') or []) else {})

print('A) WK-08 gcto has forbidden tokens?', any(t in gcto_after for t in ['satellite/ ntn','satellite/ntn','esm optimization','sector weekly report']))
print('B) WK-08 weekly has gcto-card markers?', any(t in weekly_after for t in ['project owner','develop a proposal for implementing circular economy']))
print('C) WK-08 cost near-empty?', len(' '.join((post_wk08.get('cost_optimization') or '').split())) < 40)

header_phrase='sub rfp name impacted domain status pending with expense gd name budget (sar)'
first_text=(delayed_first.get('initiative_name') or '').lower()
print('E) delayed first row is header?', header_phrase in first_text)

pre_metrics=(pre.get('rfx_metrics_wk06_08') or {})
post_metrics={}
for wk in ['WK-06','WK-07','WK-08']:
    sec=(by.get(wk,{}).get('sections') or {})
    st=(sec.get('rfx_status') or {})
    post_metrics[wk]={
        'total_received': st.get('total_received'),
        'total_approved': st.get('total_approved'),
        'total_in_progress': st.get('total_in_progress'),
        'total_cf_projects': st.get('total_cf_projects'),
    }
print('D) WK-06..08 RFx metrics preserved?', pre_metrics==post_metrics)
print('pre_metrics=', pre_metrics)
print('post_metrics=', post_metrics)