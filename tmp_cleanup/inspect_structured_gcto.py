import json
from pathlib import Path
p = Path('tmp_cleanup/structured_reports.json')
obj = json.loads(p.read_text(encoding='utf-8'))
reports = obj.get('reports', []) if isinstance(obj, dict) else obj
for row in reports:
    wk = row.get('week_label')
    secs = row.get('sections', {})
    gcto = (secs.get('gcto_updates') or '').strip()
    wd = (secs.get('weekly_digest') or '').strip()
    print(wk, '| gcto_len=', len(gcto), '| wd_len=', len(wd))
    if gcto:
        print('  gcto_sample:', gcto[:220].replace('\n',' '))
