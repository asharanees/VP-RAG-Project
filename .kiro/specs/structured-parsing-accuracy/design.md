# Design Document: Structured Parsing Accuracy

## Overview

Rewrite the five fragile subsystems in `src/common/structured_analyst.py` that cause incomplete or incorrect JSON output. The approach is surgical — only the broken functions are replaced; all public interfaces, the `_empty_sections()` schema, and downstream consumers remain unchanged.

## Architecture

No new files or AWS resources are needed. All changes are confined to `src/common/structured_analyst.py`. The ingestion Lambda (`src/pdf_ingest/app.py`) and RAG worker (`src/rag_worker/app.py`) are untouched.

```
PDF bytes
  └─► read_pdf_pages()          [pdf_utils.py — unchanged]
        └─► parse_structured_reports_from_pages()   [structured_analyst.py]
              ├─► _group_pages_by_week()             [FIX: multi-line week detection]
              ├─► _extract_sections_by_order()       [FIX: resilient scan]
              ├─► _clean_section_text("rfx_status")  [FIX: preserve numeric lines]
              ├─► _parse_rfx_status()                [unchanged — regex already correct]
              ├─► _parse_delayed_rows()              [FIX: robust column extraction]
              └─► extract_gcto_updates_fallback()    [FIX: card boundary + due date]
```

## Detailed Design

### Fix 1 — Multi-line Week Label Detection (`_normalize_week`)

**Problem:** `WEEK_RE` requires the date to be on the same line as the week label. PDFs often render them on separate lines.

**Solution:** Replace the single-line regex with a two-pass approach:
1. First try the existing same-line pattern (backward compat).
2. If that fails, scan the text line-by-line: when a `WK-NN` token is found, look ahead up to 3 lines for a date pattern `\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{4}`.

```python
def _normalize_week(text: str) -> Tuple[str, Optional[int]]:
    # Pass 1: same-line (existing behaviour)
    match = WEEK_RE.search(text or "")
    if match:
        num = int(match.group(1))
        return f"WK-{num:02d}", num

    # Pass 2: week label and date on separate lines (within 3 lines)
    lines = (text or "").splitlines()
    week_line_re = re.compile(r"\bWK[-_\s]?(\d{1,2})\b", re.IGNORECASE)
    date_line_re = re.compile(r"\b\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{4}\b", re.IGNORECASE)
    for i, line in enumerate(lines):
        wm = week_line_re.search(line)
        if wm:
            num = int(wm.group(1))
            # look ahead up to 3 lines for a date
            for j in range(i, min(i + 4, len(lines))):
                if date_line_re.search(lines[j]):
                    return f"WK-{num:02d}", num
            # week found but no date nearby — still return the week
            return f"WK-{num:02d}", num
    return "", None
```

### Fix 2 — Resilient Section Detection (`_extract_sections_by_order`)

**Problem:** The forward-only cursor stops scanning once a section is missed, silently dropping all later sections.

**Solution:** Remove the cursor constraint. For each section key, scan the **full remaining lines** (from the last found position onward, but never blocking on a miss). Use a two-pass strategy:
- Pass 1: find all section header positions in document order.
- Pass 2: slice content between consecutive found positions.

```python
def _extract_sections_by_order(week_text: str) -> Dict[str, str]:
    lines = [ln.rstrip() for ln in (week_text or "").splitlines()]
    if not lines:
        return {}

    # Find ALL section header positions (no cursor — scan full document)
    found: List[Tuple[str, int]] = []
    for idx, line in enumerate(lines):
        key = _detect_section(line)
        if key and (not found or found[-1][0] != key):
            found.append((key, idx))

    if not found:
        return {}

    # Slice content between consecutive headers
    out: Dict[str, str] = {}
    for pos_idx, (section_key, start_idx) in enumerate(found):
        end_idx = found[pos_idx + 1][1] if pos_idx + 1 < len(found) else len(lines)
        block = "\n".join(lines[start_idx + 1: end_idx]).strip()
        if block:
            # If same key appears twice, coalesce
            if section_key in out:
                out[section_key] = out[section_key] + "\n" + block
            else:
                out[section_key] = block
    return out
```

### Fix 3 — RFx Status Line Preservation (`_clean_section_text`)

**Problem:** The filter `re.match(r"^\d{1,2}[-/][a-z]{3,9}\b", low)` is intended to drop date strings like `"25-Feb"` but also drops valid lines like `"44 Approved Projects"` because the regex is too broad.

**Solution:** Tighten the date-drop pattern to require a month abbreviation immediately after the hyphen/slash, and only drop lines that are *purely* a date token (no trailing alphabetic content beyond the month):

```python
# OLD (drops too much):
if re.match(r"^\d{1,2}[-/][a-z]{3,9}\b", low):
    continue

# NEW (only drops bare date tokens like "25-Feb" or "25/Feb"):
if re.match(r"^\d{1,2}[-/](?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*$", low):
    continue
```

### Fix 4 — Robust Delayed RFP Row Parsing (`_parse_delayed_rows`)

**Problem:** Single-line column extraction using `[A-Z]{2,4}` regex misses multi-word domains; `CAPEXDELAYED` not always split; budget int() fails on commas.

**Solution:** Use a structured token-scanning approach:
1. Normalize `CAPEXDELECTED`/`OPEXDELAYED` first (already done, keep).
2. Extract `budget_sar` via `re.search(r"[\d,]{5,}")` and strip commas before `int()`.
3. Extract `expense` via explicit `\b(CAPEX|OPEX)\b` search.
4. Extract `status` via `\b(DELAYED|PENDING)\b` search.
5. Extract `pending_with` via `\b(Supplier|TA-Domain)\b` search.
6. Extract `impacted_domain` by matching against a known domain list (full names, case-insensitive) rather than uppercase-token regex.
7. Derive `sub_rfp_name` as everything before the first matched domain/expense/status token.

Known domains list:
```python
KNOWN_DOMAINS = [
    "Mobility Services", "Corporate Enablement", "Field Operation Center",
    "Network Operation Center", "Billing & Fulfilment Management",
    "Infrastructure Excellence", "Cloud Services", "FUs Enablement",
    "DA - AA", "SPG - HPG",
]
```

### Fix 5 — GCTO Card Boundary and Due Date Formatting (`extract_gcto_updates_fallback`)

**Problem:** Card grouping logic misses boundaries; standalone date lines not formatted with `"Due date:"` prefix.

**Solution:**
1. After extracting the GCTO block (between "GCTO Updates" and next section header), process line by line.
2. A **new card starts** when a status keyword (`On Track`, `Completed`, `Delayed`, `Pending`) is found on a standalone line OR when `Project Owner` appears (and a card is already in progress).
3. A **standalone date line** matches `r"^\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}$"` or `r"^\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{4}$"` — reformat as `"Due date: <text>"`.
4. Boilerplate lines (matching `_is_boilerplate_line`) are skipped.

```python
def extract_gcto_updates_fallback(raw_week_text: str) -> str:
    ...
    DATE_STANDALONE = re.compile(
        r"^(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})$|"
        r"^(\d{1,2})[-/]([A-Za-z]{3,9})[-/](\d{4})$"
    )
    STATUS_KEYWORDS = {"on track", "completed", "delayed", "pending"}
    ...
    for line in block:
        low = line.lower().strip()
        if DATE_STANDALONE.match(line.strip()):
            card.append(f"Due date: {line.strip()}")
            continue
        if low in STATUS_KEYWORDS and card:
            # flush current card, start new one with this status
            cards.append("\n".join(card).strip())
            card = [line]
            continue
        card.append(line)
    ...
```

## Correctness Properties

### Property 1: Section completeness
For any list of pages produced by `read_pdf_pages`, `parse_structured_reports_from_pages` returns a list where every element contains all 7 section keys.

**Validates: Requirements 1.4, 6.1, 6.2**

### Property 2: Week count matches detected week labels
The number of Week Records returned equals the number of distinct `WK-NN` labels found in the concatenated page text.

**Validates: Requirements 2.1, 6.4**

### Property 3: Budget SAR is always an integer or None
For every delayed RFP row in every Week Record, `budget_sar` is either `None` or a Python `int` (never a string or float).

**Validates: Requirement 3.3**

### Property 4: RFx totals are integers or None
For every Week Record, `rfx_status.total_received`, `total_approved`, `total_in_progress`, `total_cf_projects` are each either `None` or a Python `int`.

**Validates: Requirements 4.1–4.4**

## Testing Strategy

- **Unit tests** (in `tests/test_structured_analyst.py`): cover each fixed function with targeted inputs including edge cases (missing sections, multi-line week headers, CAPEXDELAYED tokens, comma budgets, standalone date lines).
- **Property-based tests** (using `hypothesis`): verify the four correctness properties above across randomly generated page text inputs.
- **Integration smoke test**: a local script (`tmp_cleanup/post_ingest_validation_report.py` style) that reads the real PDF, runs `parse_structured_reports_from_pages`, and asserts all weeks are present with non-null RFx fields.
- **Re-ingestion verification**: invoke the ingestion Lambda against the real S3 PDF and inspect the resulting `structured_reports.json`.

## Testing Framework

Use `pytest` with `hypothesis` for property-based tests. All tests live in `tests/test_structured_analyst.py`.
