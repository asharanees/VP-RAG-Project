import sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from common.pdf_utils import read_pdf_pages
from common.structured_analyst import parse_structured_reports_from_pages

pages = read_pdf_pages(Path('TSA Sector Report February 26,2026.pdf').read_bytes())
reports = parse_structured_reports_from_pages(pages)
wk07 = next((r for r in reports if r.get('week_label') == 'WK-07'), {})
sections = wk07.get('sections') or {}

def print_lines(label, text):
    lines = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]
    print(f'--- {label} ({len(lines)} lines) ---')
    for i, ln in enumerate(lines, 1):
        print(f'{i:02}: {ln}')

print_lines('weekly_digest', sections.get('weekly_digest'))
print_lines('key_projects_hot_topics', sections.get('key_projects_hot_topics'))