import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.common.structured_analyst import _clean_section_text, _parse_delayed_rows

raw = "CorpE – CBU Demand – Tribe Q3 DA - AA TA-Domain CAPEXDELAYED 2,935,210 Corporate Enablement"
cleaned = _clean_section_text("delayed_rfps", raw)
print(f"cleaned: [{cleaned}]")
rows = _parse_delayed_rows(cleaned)
print(f"rows: {len(rows)}")
if rows:
    print(rows[0])
