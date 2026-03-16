import json
import boto3

bucket = 'vp-rag-project-source-980874804229-us-east-1'
key = 'structured/structured_reports.json'

s3 = boto3.client('s3', region_name='us-east-1')
obj = s3.get_object(Bucket=bucket, Key=key)
data = json.loads(obj['Body'].read().decode('utf-8'))
reports = data.get('reports', data if isinstance(data, list) else [])

wk08 = None
for r in reports:
    if r.get('week_label') == 'WK-08':
        wk08 = r
        break

if not wk08:
    print('WK-08 not found')
else:
    gcto = ((wk08.get('sections') or {}).get('gcto_updates'))
    print('WK-08 gcto_updates raw value:')
    print(repr(gcto))
    print('\nclassification:')
    if gcto is None:
        print('missing')
    elif not str(gcto).strip():
        print('empty')
    elif len(str(gcto).strip()) < 40:
        print('too_short_or_heading_only')
    else:
        print('non_empty')
