import json
import boto3
import re

bucket = 'vp-rag-project-source-980874804229-us-east-1'
key = 'structured/structured_reports.json'
s3 = boto3.client('s3', region_name='us-east-1')
obj = s3.get_object(Bucket=bucket, Key=key)
data = json.loads(obj['Body'].read().decode('utf-8'))
reports = data.get('reports', data if isinstance(data, list) else [])

query='latest gcto updates'
# strict latest week from data
week_rows=[r for r in reports if r.get('week_label')]
week_rows.sort(key=lambda r: int(r.get('week_num') or 0))
latest = week_rows[-1] if week_rows else {}
wk = latest.get('week_label','WK-NA')
gcto = ((latest.get('sections') or {}).get('gcto_updates') or '')

lines=[]
for sentence in re.split(r"\n|(?<=[.!?])\s+", gcto):
    line=' '.join(sentence.split()).strip('-: ')
    if not line:
        continue
    if line.lower() in {'sector weekly report','gcto updates'}:
        continue
    if len(line) < 16:
        continue
    if line not in lines:
        lines.append(line)
    if len(lines)>=6:
        break

print(f'reports={len(reports)} latest={wk} chars={len(gcto)}')
print('\n' + '\n'.join([f'Latest GCTO Updates ({wk})'] + [f'- {x}' for x in lines]))