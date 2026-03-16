import json
import boto3

bucket='vp-rag-project-source-980874804229-us-east-1'
key='structured/structured_reports.json'
s3=boto3.client('s3', region_name='us-east-1')
obj=s3.get_object(Bucket=bucket, Key=key)
data=json.loads(obj['Body'].read().decode('utf-8'))
reports=data.get('reports', data if isinstance(data,list) else [])
print('reports_count=', len(reports))
print('weeks=', ', '.join(sorted([r.get('week_label','') for r in reports if r.get('week_label')], key=lambda x:int(x.split('-')[1]))))