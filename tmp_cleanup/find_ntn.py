import sys, json
sys.path.insert(0,'src')
data = json.load(open('tmp_cleanup/s3_structured_reports.json', encoding='utf-8'))
reports = data.get('reports', data) if isinstance(data, dict) else data
for r in reports:
    wk = r.get('week_label')
    for sec, val in r['sections'].items():
        if isinstance(val, str) and 'ntn' in val.lower():
            idx = val.lower().find('ntn')
            snippet = val[max(0,idx-30):idx+80]
            print(f"{wk} / {sec}: ...{snippet}...")
