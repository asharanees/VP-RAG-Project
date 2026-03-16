import sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))

from common.pdf_utils import read_pdf_pages
import common.structured_analyst as sa

pdf = Path('TSA Sector Report February 26,2026.pdf')
pages = read_pdf_pages(pdf.read_bytes())

week_groups = sa._group_pages_by_week(pages)
week = week_groups.get('WK-08')
if not week:
    print('WK-08 not found in grouped pages')
    raise SystemExit(0)

week_text = '\n'.join(week.get('pages', []))
raw_sections = sa._extract_sections_by_order(week_text)
reports = sa.parse_structured_reports_from_pages(pages)
wk08 = next((r for r in reports if r.get('week_label') == 'WK-08'), None)
clean_sections = ((wk08 or {}).get('sections') or {})

ordered = sa.ORDERED_SECTION_KEYS

print('WK-08 SECTION DEBUG')
print('='*110)
print(f"report_date={wk08.get('report_date') if wk08 else None}")
print(f"raw_week_chars={len(week_text)}")

for key in ordered:
    print('\n' + '='*110)
    print(f'SECTION: {key}')
    raw = raw_sections.get(key, '')
    print(f'RAW_CAPTURE chars={len(raw)} lines={len(raw.splitlines())}')
    if raw:
        print('-- RAW (first 80 lines) --')
        print('\n'.join(raw.splitlines()[:80]))
    else:
        print('<no raw capture>')

    parsed = clean_sections.get(key, '')
    if isinstance(parsed, dict):
        print('-- PARSED STRUCT --')
        print(parsed)
    elif isinstance(parsed, list):
        print(f'-- PARSED LIST rows={len(parsed)} (first 8) --')
        for row in parsed[:8]:
            print(row)
    else:
        print(f'-- PARSED TEXT chars={len(parsed)} lines={len((parsed or "").splitlines())} --')
        print(parsed if parsed else '<empty>')