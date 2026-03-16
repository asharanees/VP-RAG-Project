import json
import boto3

bucket='vp-rag-project-source-980874804229-us-east-1'
key='structured/structured_reports.json'
s3=boto3.client('s3', region_name='us-east-1')
obj=s3.get_object(Bucket=bucket, Key=key)
data=json.loads(obj['Body'].read().decode('utf-8'))
reports=data.get('reports', data if isinstance(data,list) else [])
by={r.get('week_label'):r for r in reports if r.get('week_label')}

out={}
for wk in ['WK-07','WK-08']:
    row=by.get(wk,{})
    sec=row.get('sections',{}) or {}
    out[wk]={
        'gcto_updates': sec.get('gcto_updates',''),
        'weekly_digest': sec.get('weekly_digest',''),
        'key_projects_hot_topics': sec.get('key_projects_hot_topics',''),
        'cost_optimization': sec.get('cost_optimization',''),
        'rfx_status': sec.get('rfx_status',{}),
        'delayed_rfps_first5': (sec.get('delayed_rfps',[]) or [])[:5],
    }

out['rfx_metrics_wk06_08']={}
for wk in ['WK-06','WK-07','WK-08']:
    sec=(by.get(wk,{}).get('sections',{}) or {})
    status=sec.get('rfx_status',{}) or {}
    out['rfx_metrics_wk06_08'][wk]={
        'total_received': status.get('total_received'),
        'total_approved': status.get('total_approved'),
        'total_in_progress': status.get('total_in_progress'),
        'total_cf_projects': status.get('total_cf_projects'),
    }

with open('tmp_cleanup/pre_reingest_snapshot.json','w',encoding='utf-8') as f:
    json.dump(out,f,ensure_ascii=False,indent=2)
print('saved tmp_cleanup/pre_reingest_snapshot.json')