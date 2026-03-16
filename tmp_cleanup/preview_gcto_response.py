import boto3
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path('src').resolve()))
from common.structured_analyst import classify_query_intent, get_structured_context, load_structured_reports_json, resolve_target_weeks
from common.settings import load_settings

settings = load_settings()
s3 = boto3.client('s3', region_name='us-east-1')
q = 'latest gcto updates'
intent = classify_query_intent(q).get('intent','weekly_summary')
reports = load_structured_reports_json(s3, settings.source_bucket_name, settings.structured_reports_key)
weeks = [r.get('week_label','') for r in reports if r.get('week_label')]
target_weeks = resolve_target_weeks(q, weeks, intent)
ctx = get_structured_context(intent, target_weeks, reports, q)

evidence = ctx.get('evidence',[]) or []
latest_week = (ctx.get('target_weeks',[]) or ['WK-NA'])[-1]
bullets = []
for item in evidence:
    parts = item.split('|', 2)
    if len(parts) < 3:
        continue
    body = ' '.join(parts[2].split()).strip()
    if not body:
        continue
    for sentence in re.split(r"\n|(?<=[.!?])\s+", body):
        line = ' '.join(sentence.split()).strip('-: ')
        if not line:
            continue
        if line.lower() in {'sector weekly report', 'gcto updates'}:
            continue
        if len(line) < 16:
            continue
        if line not in bullets:
            bullets.append(line)
        if len(bullets) >= 6:
            break
    if len(bullets) >= 6:
        break

print(f'intent={intent}')
print(f'target_weeks={ctx.get("target_weeks",[])}')
print('\n' + '\n'.join([f'Latest GCTO Updates ({latest_week})'] + [f'- {b}' for b in bullets[:6]]))