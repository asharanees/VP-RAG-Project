import sys
sys.path.insert(0, 'src')
from common.structured_analyst import _group_pages_by_week
from common.pdf_utils import read_pdf_pages
import re

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

by_week = _group_pages_by_week(pages)
wk08 = by_week['WK-08']
week_text = "\n".join(wk08['pages'])

lines = [ln.strip() for ln in week_text.splitlines() if ln.strip()]

# Find gcto updates line
for i, l in enumerate(lines):
    if 'gcto updates' in l.lower():
        print(f"[{i}] GCTO HEADER: {repr(l)}")
        # Print surrounding context
        for j in range(max(0,i-2), min(len(lines), i+30)):
            print(f"  [{j}] {repr(lines[j][:100])}")
        break
