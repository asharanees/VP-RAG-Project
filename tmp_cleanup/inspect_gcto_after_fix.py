import json
import boto3

bucket = 'vp-rag-project-source-980874804229-us-east-1'
key = 'structured/structured_reports.json'

s3 = boto3.client('s3', region_name='us-east-1')
obj = s3.get_object(Bucket=bucket, Key=key)
data = json.loads(obj['Body'].read().decode('utf-8'))
reports = data.get('reports', data if isinstance(data, list) else [])
wk08 = next((r for r in reports if r.get('week_label') == 'WK-08'), None)
if not wk08:
    print('WK-08 not found')
else:
    gcto = ((wk08.get('sections') or {}).get('gcto_updates'))
    print(repr(gcto))
