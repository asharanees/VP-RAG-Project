import sys,re
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from common.pdf_utils import read_pdf_pages
from common.structured_analyst import _group_pages_by_week

pages = read_pdf_pages(Path('TSA Sector Report February 26,2026.pdf').read_bytes())
by_week = _group_pages_by_week(pages)
week_text='\n'.join((by_week.get('WK-08') or {}).get('pages', []))
print('total delayed tokens', len(re.findall('DELAYED', week_text, flags=re.IGNORECASE)))
for m in re.finditer('DELAYED', week_text, flags=re.IGNORECASE):
    start=max(0,m.start()-90); end=min(len(week_text),m.end()+120)
    snip=' '.join(week_text[start:end].split())
    print('-', snip)