import sys
from pathlib import Path

sys.path.insert(0, str(Path('.').resolve() / 'src'))
from common.pdf_utils import read_pdf_pages

pdf_path = Path('TSA Sector Report February 26,2026.pdf')
with pdf_path.open('rb') as f:
    pages = read_pdf_pages(f.read())

for page_num, text in pages:
    lower = text.lower()
    if 'gcto' in lower or 'sector weekly report' in lower:
        print('\n--- PAGE', page_num, '---')
        for token in ['gcto updates', 'gcto', 'sector weekly report', 'project owner', 'completed', 'on track']:
            pos = lower.find(token)
            if pos >= 0:
                start = max(0, pos - 120)
                end = min(len(text), pos + 450)
                print(f"\n[token={token}]\n{text[start:end]}\n")
