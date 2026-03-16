import json
import boto3
from pprint import pprint

bucket = 'vp-rag-project-source-980874804229-us-east-1'
key = 'structured/structured_reports.json'

s3 = boto3.client('s3', region_name='us-east-1')
obj = s3.get_object(Bucket=bucket, Key=key)
data = json.loads(obj['Body'].read().decode('utf-8'))
reports = data.get('reports', data if isinstance(data, list) else [])
if not reports:
    print('No reports found')
    raise SystemExit(0)

reports_sorted = sorted(reports, key=lambda r: int(r.get('week_num') or 0))
latest = reports_sorted[-1]
week = latest.get('week_label')
print(f'Latest week: {week}')
print(f"report_date: {latest.get('report_date')}")
print('-' * 80)

sections = latest.get('sections') or {}
for section_name, section_value in sections.items():
    print(f'\n[{section_name}]')
    if isinstance(section_value, str):
        print(f'length={len(section_value)}')
        print(section_value if section_value else '<empty>')
    else:
        pprint(section_value, width=120, sort_dicts=False)

print('\n' + '=' * 80)
print('Available weeks:', ', '.join(r.get('week_label','') for r in reports_sorted if r.get('week_label')))