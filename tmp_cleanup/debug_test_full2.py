import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.common.structured_analyst import _parse_delayed_rows

line = "CorpE – CBU Demand – Tribe Q3 DA - AA TA-Domain CAPEXDELAYED 2,935,210 Corporate Enablement"
norm = re.sub(r"\b(CAPEX|OPEX)DELAYED\b", r"\1 DELAYED", line, flags=re.IGNORECASE)
print(f"norm: [{norm}]")

_EXPENSE_STATUS_RE = re.compile(r"\b(CAPEX|OPEX)\s*DELAYED\b", re.IGNORECASE)
_PENDING_WITH_RE   = re.compile(r"\b(TA-Domain|Supplier)\b", re.IGNORECASE)
_BUDGET_RE         = re.compile(r"(\d[\d,]{4,})(?=[^,\d]|$)")
_DOMAIN_SC_RE      = re.compile(r"([A-Z]{2,4}(?:\s*[-_]\s*[A-Z]{2,4})*)\s*$")

es_match = _EXPENSE_STATUS_RE.search(norm)
print(f"es_match: {es_match}")
pw_match = _PENDING_WITH_RE.search(norm)
print(f"pw_match: {pw_match}")
budget_match = _BUDGET_RE.search(norm)
print(f"budget_match: {budget_match}")

if es_match:
    left = norm[:es_match.start()].strip()
    print(f"left before trim: [{left}]")
    if pw_match:
        pw_pos = left.rfind(pw_match.group(0))
        if pw_pos >= 0:
            left = left[:pw_pos].strip()
    print(f"left after pw trim: [{left}]")
    sc_match = _DOMAIN_SC_RE.search(left)
    print(f"sc_match: {sc_match}")
