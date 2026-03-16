import sys
sys.path.insert(0, 'src')
from common.structured_analyst import _group_pages_by_week
from common.pdf_utils import read_pdf_pages

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

by_week = _group_pages_by_week(pages)
wk08 = by_week['WK-08']
week_text = "\n".join(wk08['pages'])
lines = [ln.strip() for ln in week_text.splitlines() if ln.strip()]

for i, l in enumerate(lines):
    if 'sami' in l.lower() or 'circular economy' in l.lower() or 'on track' == l.lower():
        print(f"[{i}] {repr(l[:120])}")
        for j in range(max(0,i-3), min(len(lines), i+10)):
            print(f"  [{j}] {repr(lines[j][:120])}")
        print()
