import sys
sys.path.insert(0, 'src')
from common.structured_analyst import _extract_sections_by_order, _group_pages_by_week, _is_boilerplate_line
from common.pdf_utils import read_pdf_pages
import re

with open('TSA Sector Report February 26,2026.pdf', 'rb') as f:
    pages = read_pdf_pages(f.read())

by_week = _group_pages_by_week(pages)
wk08 = by_week['WK-08']
week_text = "\n".join(wk08['pages'])
sections = _extract_sections_by_order(week_text)
raw = sections.get('weekly_digest', '')

lines = [" ".join(raw_l.split()).strip("-\u2022: ") for raw_l in raw.splitlines()]
lines = [l for l in lines if l and not _is_boilerplate_line(l)]

stop_markers = {
    "compliance", "enterprise architecture (star)",
    "technology governance & arb", "gtu blueprint 2026", "technology strategy",
}
_PERSON_NAME_RE = re.compile(
    r"^[A-Z][a-z]+(?:\s+[A-Z]\.)+\s+[A-Z][a-z]+"
    r"|^[A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+$",
)

for line in lines:
    low = line.lower()
    if low in stop_markers:
        print(f"STOP: {repr(line)}")
        break
    if low in {"on track", "completed", "project owner", "delayed", "pending"}:
        print(f"SKIP(status): {repr(line)}")
        continue
    if re.search(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b", line):
        print(f"SKIP(date): {repr(line)}")
        continue
    if "develop a proposal for implementing circular economy" in low:
        print(f"SKIP(gcto_title): {repr(line)}")
        continue
    if _PERSON_NAME_RE.match(line.strip()):
        print(f"SKIP(name): {repr(line)}")
        continue
    if "rfx cost optimization" in low:
        print(f"SKIP(rfx_cost): {repr(line)}")
        continue
    known_headings = [
        "site forecasting using ml", "technology rationalization", "iram milestones",
        "tsba playbook", "2g shutdown", "technology strategy contribution",
    ]
    if sum(1 for h in known_headings if h in low) >= 2:
        print(f"SKIP(fused): {repr(line)}")
        continue
    print(f"KEEP: {repr(line[:80])}")
