import sys, json
sys.path.insert(0, 'src')
from common.structured_analyst import classify_query_intent, resolve_target_weeks, get_structured_context

data = json.load(open('tmp_cleanup/s3_structured_reports.json', encoding='utf-8'))
reports = data.get('reports', data) if isinstance(data, dict) else data

query = "what is the update on ntn"
intent_result = classify_query_intent(query)
intent = intent_result['intent']
weeks = [r['week_label'] for r in reports if r.get('week_label')]
target = resolve_target_weeks(query, weeks, intent)

print(f"Intent: {intent}")
print(f"Target weeks: {target}")

ctx = get_structured_context(intent, target, reports, query)
print(f"\nEvidence items: {len(ctx.get('evidence', []))}")
for e in ctx.get('evidence', []):
    print(f"\n--- {e[:200]}")
