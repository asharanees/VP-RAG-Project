import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

text = """Sub RFP Name
Sub RFP Name Impacted Domain Status Pending With Expense GD Name Budget (SAR)
Internal-Wireless Network Improvements 2025 - Hajj Scope
IBS 1447 (ESM + RF) SPG - HPG Supplier CAPEXDELAYED 67,519,408 Mobility Services"""

raw_lines = text.splitlines()
joined_lines = []
i = 0
while i < len(raw_lines):
    line = " ".join(raw_lines[i].split()).strip()
    if not line:
        i += 1
        continue
    has_struct = bool(re.search(r"\b(CAPEX|OPEX|DELAYED|PENDING)\b", line, re.IGNORECASE))
    has_budget = bool(re.search(r"\d[\d,]{4,}", line))
    if not has_struct and not has_budget and i + 1 < len(raw_lines):
        next_line = " ".join(raw_lines[i + 1].split()).strip()
        next_has_struct = bool(re.search(r"\b(CAPEX|OPEX|DELAYED|PENDING)\b", next_line, re.IGNORECASE))
        print(f"  Line {i}: [{line}] has_struct={has_struct} has_budget={has_budget}")
        print(f"  Next {i+1}: [{next_line[:80]}] next_has_struct={next_has_struct}")
        if next_has_struct and next_line:
            raw_lines[i + 1] = line + " " + next_line
            print(f"  -> JOINED into: [{raw_lines[i+1][:100]}]")
            i += 1
            continue
    joined_lines.append(line)
    i += 1

print("\nFinal joined lines:")
for j, l in enumerate(joined_lines):
    print(f"  {j}: {l[:120]}")
