import sys; sys.path.insert(0,'src')
from common.structured_analyst import classify_query_intent, resolve_target_weeks

tests = [
    'what is the update on ntn',
    'what is the ntn progress',
    'show me the GCTO updates',
    'what are the delayed RFPs',
    'what are the major hot topics',
    'compare delayed RFPs between WK-07 and WK-08',
    'what is the RFx status',
    'weekly summary',
    'satellite update',
    'tell me about cloud initiatives',
]
weeks = ['WK-07','WK-08','WK-09','WK-10']
for q in tests:
    r = classify_query_intent(q)
    t = resolve_target_weeks(q, weeks, r['intent'])
    print(f"  {r['intent']:20s} {str(t):25s}  <- {q}")
