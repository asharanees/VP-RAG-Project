# Implementation Tasks

## Tasks

- [x] 1. Fix `_normalize_week` for multi-line week label detection
  - Replace single-line `WEEK_RE` match with two-pass approach: same-line first, then lookahead up to 3 lines for a date pattern
  - Ensure backward compatibility with same-line `WK-08 25-Feb-2026` format
  - File: `src/common/structured_analyst.py`

- [x] 2. Fix `_extract_sections_by_order` for resilient section scanning
  - Remove the forward-only cursor constraint
  - Scan all lines to find every section header position
  - Slice content between consecutive found headers
  - Coalesce duplicate section keys
  - File: `src/common/structured_analyst.py`

- [x] 3. Fix `_clean_section_text` rfx_status date-line filter
  - Tighten the drop pattern from `r"^\d{1,2}[-/][a-z]{3,9}\b"` to only match bare date tokens ending with the month (no trailing content)
  - Preserve lines like `"44 Approved Projects"` that start with a number
  - File: `src/common/structured_analyst.py`

- [x] 4. Fix `_parse_delayed_rows` for robust column extraction
  - Add `KNOWN_DOMAINS` list for multi-word domain matching
  - Extract `budget_sar` via digit-comma pattern and strip commas before `int()`
  - Extract `expense`, `status`, `pending_with` via explicit word-boundary regex
  - Derive `sub_rfp_name` as text before first matched structural token
  - Populate `impacted_domain` from `KNOWN_DOMAINS` match
  - File: `src/common/structured_analyst.py`

- [x] 5. Fix `extract_gcto_updates_fallback` for card boundaries and due date formatting
  - Add `DATE_STANDALONE` regex to detect bare date lines
  - Reformat standalone date lines as `"Due date: <text>"`
  - Fix card boundary detection: new card starts on status keyword line (when a card is already in progress) or on `Project Owner` line
  - File: `src/common/structured_analyst.py`

- [x] 6. Write unit tests for all five fixes
  - Test `_normalize_week` with multi-line input (week and date on separate lines)
  - Test `_extract_sections_by_order` with a missing middle section
  - Test `_clean_section_text` preserves `"44 Approved Projects"` and drops `"25-Feb"`
  - Test `_parse_delayed_rows` with `CAPEXDELAYED`, comma budget, multi-word domain
  - Test `extract_gcto_updates_fallback` produces `"Due date: 30 June 2026"` (fixes `test_extract_gcto_updates_fallback_between_headings`)
  - Ensure all existing tests in `tests/test_structured_analyst.py` still pass
  - File: `tests/test_structured_analyst.py`

- [x] 7. Write property-based tests
  - Property 1: section completeness — all 7 keys present in every Week Record
  - Property 2: week count matches detected week labels
  - Property 3: `budget_sar` is always `int` or `None`
  - Property 4: RFx totals are always `int` or `None`
  - Use `hypothesis` library
  - File: `tests/test_structured_analyst.py`

- [x] 8. Re-ingest PDF from S3 and verify output JSON
  - Read S3 bucket and PDF key from `src/common/settings.py` / environment
  - Invoke the ingestion Lambda (or run `parse_structured_reports_from_pages` locally against the real PDF)
  - Assert all weeks present, `rfx_status.total_received` non-null, `delayed_rfps` non-empty per week
  - Print a summary table of week → section fill status
  - File: `tmp_cleanup/verify_reingest.py` (local verification script)
