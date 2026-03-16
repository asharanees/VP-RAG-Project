# Requirements Document

## Introduction

The `structured_analyst.py` module parses weekly PDF reports into structured JSON for a RAG-based WhatsApp agent. The current parsing logic has five identified failure modes that cause sections to be silently skipped, numeric fields to be missed, and structured rows to be malformed. This feature improves the accuracy and robustness of the parsing pipeline so that all 7 sections are reliably populated for every week in the output JSON.

## Glossary

- **Parser**: The set of functions in `src/common/structured_analyst.py` responsible for converting raw PDF page text into structured JSON.
- **Week Record**: A single entry in the output JSON list, keyed by `week_label` (e.g. `WK-08`), containing all 7 section fields.
- **Section**: One of the 7 named content blocks extracted per week: `gcto_updates`, `weekly_digest`, `key_projects_hot_topics`, `cost_optimization`, `executive_summary_rfx_cost`, `rfx_status`, `delayed_rfps`.
- **Section Header**: A line of text in the PDF that marks the start of a section (e.g. `"GCTO Updates"`, `"RFx Status"`).
- **Delayed RFP Row**: A single parsed record from the Delayed RFPs table, containing fields: `sub_rfp_name`, `impacted_domain`, `expense`, `budget_sar`, `status`, `pending_with`.
- **GCTO Card**: A single project card within the GCTO Updates section, containing a status, project owner, due date, and description.
- **Week Label**: A normalized string of the form `WK-NN` (e.g. `WK-08`) derived from the week header in the PDF.
- **RFx Status Fields**: The four integer KPI fields extracted from the RFx Status section: `total_received`, `total_approved`, `total_in_progress`, `total_cf_projects`.
- **Re-ingestion**: The process of re-uploading the source PDF to S3 to trigger the ingestion Lambda and regenerate `structured_reports.json`.
- **Ingestion Lambda**: The AWS Lambda function in `src/pdf_ingest/app.py` that reads the PDF from S3, calls the Parser, and writes the output JSON back to S3.

---

## Requirements

### Requirement 1: Resilient Section Detection

**User Story:** As a system operator, I want section detection to continue scanning the full document even when a section header is missing or out of order, so that all available sections are captured regardless of PDF layout variations.

#### Acceptance Criteria

1. WHEN `_extract_sections_by_order` scans a week's page text and a section header is not found at the expected cursor position, THE Parser SHALL continue scanning the remaining lines for subsequent section headers rather than stopping.
2. WHEN a section header appears out of the expected order in the page text, THE Parser SHALL still capture that section's content.
3. WHEN a section header is missing entirely from a week's page text, THE Parser SHALL leave that section as an empty string or empty list in the output and SHALL NOT skip detection of later sections.
4. THE Parser SHALL produce output containing all 7 section keys for every Week Record, even when some sections have no content.

---

### Requirement 2: Multi-Line Week Label Detection

**User Story:** As a system operator, I want the week label detector to match week numbers and dates that appear on separate lines in the PDF, so that pages are not silently dropped when the PDF renders the week header across multiple lines.

#### Acceptance Criteria

1. WHEN a PDF page contains a week label (e.g. `WK-08`) and a date (e.g. `25-Feb-2026`) on separate lines within 3 lines of each other, THE Parser SHALL detect and associate them as a single Week Record.
2. WHEN a PDF page contains a week label and date on the same line (e.g. `WK-08 25-Feb-2026`), THE Parser SHALL continue to detect it correctly (backward compatibility).
3. IF a page contains a week label with no date within 3 subsequent lines, THEN THE Parser SHALL still create a Week Record for that week label with `report_date` set to `null`.
4. THE `_normalize_week` function SHALL accept a multi-line string and match a week label and date that are separated by up to 3 lines.

---

### Requirement 3: Accurate Delayed RFP Row Parsing

**User Story:** As a data consumer, I want each Delayed RFP row to be parsed into correctly typed fields, so that the RAG worker can answer questions about delayed initiatives with accurate domain, expense type, budget, and status information.

#### Acceptance Criteria

1. WHEN a Delayed RFP row contains `CAPEXDELAYED` or `OPEXDELAYED` (no space), THE Parser SHALL normalize it to `CAPEX DELAYED` or `OPEX DELAYED` before field extraction.
2. WHEN extracting `impacted_domain` from a Delayed RFP row, THE Parser SHALL correctly extract multi-word domain names such as `"Corporate Enablement"`, `"Field Operation Center"`, and `"Mobility Services"`, and SHALL NOT be limited to 2–4 uppercase letter tokens.
3. WHEN a `budget_sar` value contains commas (e.g. `"2,935,210"`), THE Parser SHALL strip the commas before converting to integer and SHALL store the result as an integer in the `budget_sar` field.
4. WHEN a Delayed RFP row contains the token `CAPEX`, THE Parser SHALL set `expense` to `"CAPEX"`.
5. WHEN a Delayed RFP row contains the token `OPEX`, THE Parser SHALL set `expense` to `"OPEX"`.
6. WHEN a Delayed RFP row contains the token `DELAYED`, THE Parser SHALL set `status` to `"delayed"`.
7. WHEN a Delayed RFP row contains the token `PENDING` and does not contain `DELAYED`, THE Parser SHALL set `status` to `"pending"`.
8. WHEN a Delayed RFP row contains `TA-Domain`, THE Parser SHALL set `pending_with` to `"TA-Domain"`.
9. WHEN a Delayed RFP row contains `Supplier`, THE Parser SHALL set `pending_with` to `"Supplier"`.
10. THE Parser SHALL populate the `sub_rfp_name` field with the initiative name portion of the row, excluding domain, expense, status, and budget tokens.

---

### Requirement 4: RFx Status Numeric Field Extraction

**User Story:** As a data consumer, I want the four RFx KPI integers to be extracted correctly even when the line starts with a number, so that trend analysis and progress comparisons are based on accurate data.

#### Acceptance Criteria

1. WHEN the `rfx_status` section text contains a line starting with a number followed by `"RFPs Received"` (e.g. `"89 RFPs Received in 2026"`), THE Parser SHALL extract that number as `total_received`.
2. WHEN the `rfx_status` section text contains a line starting with a number followed by `"Approved Projects"` (e.g. `"44 Approved Projects"`), THE Parser SHALL extract that number as `total_approved`.
3. WHEN the `rfx_status` section text contains a line starting with a number followed by `"In Progress"` (e.g. `"45 In Progress RFPs"`), THE Parser SHALL extract that number as `total_in_progress`.
4. WHEN the `rfx_status` section text contains a line starting with a number followed by `"CF Projects"` (e.g. `"44 CF Projects"`), THE Parser SHALL extract that number as `total_cf_projects`.
5. THE `_clean_section_text` function for `rfx_status` SHALL NOT drop lines that begin with a number followed by a space and alphabetic text (e.g. `"44 Approved Projects"`).
6. IF a line in the `rfx_status` section matches the date-like pattern `r"^\d{1,2}[-/][a-z]{3,9}\b"`, THEN THE Parser SHALL drop that line; all other numeric lines SHALL be preserved.

---

### Requirement 5: GCTO Card Boundary Detection and Due Date Formatting

**User Story:** As a data consumer, I want GCTO cards to be correctly split at card boundaries and due dates to be formatted with a `"Due date:"` prefix, so that the WhatsApp agent can present structured card information accurately.

#### Acceptance Criteria

1. WHEN `extract_gcto_updates_fallback` processes a GCTO Updates block, THE Parser SHALL identify each card boundary by detecting a standalone date line (matching `r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b"` or `r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{4}\b"`) that is not part of a longer sentence.
2. WHEN a standalone date line is found within a GCTO card, THE Parser SHALL format it as `"Due date: <original date text>"` in the output.
3. WHEN `extract_gcto_updates_fallback` processes a block containing `"30 June 2026"` as a standalone line, THE Parser SHALL include `"Due date: 30 June 2026"` in the output string.
4. WHEN a GCTO card contains a status keyword (`"On Track"`, `"Completed"`, `"Delayed"`) on a line before the project owner line, THE Parser SHALL treat the status as part of the same card and SHALL NOT start a new card boundary at the status line.
5. WHEN `extract_gcto_updates_fallback` encounters a line matching a known section header (e.g. `"Weekly Digest"`), THE Parser SHALL stop processing and SHALL NOT include that line or any subsequent lines in the output.

---

### Requirement 6: Complete Section Presence in Output JSON

**User Story:** As a RAG worker consumer, I want every Week Record in the output JSON to contain all 7 section keys, so that downstream code can safely access any section without key-error guards.

#### Acceptance Criteria

1. THE Parser SHALL include all 7 section keys (`gcto_updates`, `weekly_digest`, `key_projects_hot_topics`, `cost_optimization`, `executive_summary_rfx_cost`, `rfx_status`, `delayed_rfps`) in the `sections` dict of every Week Record.
2. WHEN a section has no extractable content, THE Parser SHALL set text sections to an empty string `""` and list sections (`delayed_rfps`) to an empty list `[]`.
3. THE Parser SHALL include the structured sub-keys (`rfx_status_struct`, `executive_summary_rfx_cost_struct`, `delayed_rfps_struct`) in every Week Record, initialized to their empty-state defaults when no content is found.
4. WHEN `parse_structured_reports_from_pages` is called with pages from a PDF containing 8 weeks of data, THE Parser SHALL return a list of exactly 8 Week Records (one per detected week label).

---

### Requirement 7: Re-ingestion Verification

**User Story:** As a system operator, I want to re-ingest the source PDF from S3 after the parsing logic is updated, so that the `structured_reports.json` file reflects the improved parsing output.

#### Acceptance Criteria

1. WHEN the Ingestion Lambda is triggered by uploading the source PDF to S3, THE Ingestion Lambda SHALL call `parse_structured_reports_from_pages` with the extracted pages and write the result to `structured_reports.json` in S3.
2. WHEN `structured_reports.json` is written after re-ingestion of a PDF with 8 weeks of data, THE output JSON SHALL contain 8 Week Records.
3. WHEN `structured_reports.json` is written after re-ingestion, each Week Record SHALL have a non-`null` `rfx_status.total_received` integer value.
4. WHEN `structured_reports.json` is written after re-ingestion, each Week Record SHALL have a `delayed_rfps` list containing at least 1 row.
5. THE `structured_reports.json` file written to S3 SHALL be valid JSON parseable by `json.loads`.
