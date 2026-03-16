import json
import boto3
from pathlib import Path
import sys
sys.path.insert(0, str(Path('src').resolve()))
from common.structured_analyst import classify_query_intent, resolve_target_weeks, get_structured_context
from rag_worker.app import _extract_gcto_template_fields

bucket = 'vp-rag-project-source-980874804229-us-east-1'
key = 'structured/structured_reports.json'
s3 = boto3.client('s3', region_name='us-east-1')
obj = s3.get_object(Bucket=bucket, Key=key)
data = json.loads(obj['Body'].read().decode('utf-8'))
reports = data.get('reports', data if isinstance(data, list) else [])

q = 'what are the latest gcto updates'
intent = classify_query_intent(q).get('intent','weekly_summary')
weeks = [r.get('week_label','') for r in reports if r.get('week_label')]
target = resolve_target_weeks(q, weeks, intent)
ctx = get_structured_context(intent, target, reports, q)
latest_week = (ctx.get('target_weeks') or ['WK-NA'])[-1]

gcto_body = ''
for item in (ctx.get('evidence') or []):
    parts = item.split('|', 2)
    if len(parts) >= 3 and parts[2].strip():
        gcto_body = parts[2].strip()
        break

fields = _extract_gcto_template_fields(gcto_body)
print('intent=', intent)
print('target=', target)
print('Latest GCTO Updates (' + latest_week + ')')
print('- Status: ' + fields['status'])
print('- Owner: ' + fields['owner'])
print('- Due Date: ' + fields['due_date'])
print('- Update: ' + fields['update'])