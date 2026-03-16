import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.common.structured_analyst import _parse_delayed_rows

# Simulate what happens after _clean_section_text passes through unchanged
cleaned = "Sub RFP Name Impacted Domain Status Pending With Expense GD Name Budget (SAR)\nCorpE – CBU Demand – Tribe Q3 DA - AA TA-Domain CAPEXDELAYED 2,935,210 Corporate Enablement"

rows = _parse_delayed_rows(cleaned)
print(f"rows: {len(rows)}")
if rows:
    print(rows[0])
else:
    # Debug: check each line
    import re
    for line in cleaned.splitlines():
        norm = re.sub(r"\b(CAPEX|OPEX)DELAYED\b", r"\1 DELAYED", line, flags=re.IGNORECASE)
        has_anchor = bool(re.search(r"\b(CAPEX|OPEX)\s*DELAYED\b", norm, re.IGNORECASE))
        lower = line.lower()
        header_words = ["sub rfp", "impacted domain", "pending with", "expense", "budget"]
        header_count = sum(1 for w in header_words if w in lower)
        print(f"line: [{line[:80]}]")
        print(f"  has_anchor={has_anchor}, header_count={header_count}, delayed_in_lower={'delayed' in lower}")
