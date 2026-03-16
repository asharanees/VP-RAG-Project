import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.common.structured_analyst import _extract_sections_by_order, _clean_section_text, _parse_delayed_rows

text = "\n".join([
    "WK-08 25-Feb-2026",
    "Delayed RFPs",
    "Sub RFP Name Impacted Domain Status Pending With Expense GD Name Budget (SAR)",
    "CorpE – CBU Demand – Tribe Q3 DA - AA TA-Domain CAPEXDELAYED 2,935,210 Corporate Enablement",
])

sections = _extract_sections_by_order(text)
print("sections found:", list(sections.keys()))
raw = sections.get("delayed_rfps", "")
print(f"raw delayed: [{raw}]")
cleaned = _clean_section_text("delayed_rfps", raw)
print(f"cleaned: [{cleaned}]")
rows = _parse_delayed_rows(cleaned)
print(f"rows: {len(rows)}")
