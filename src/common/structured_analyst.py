# Helper to determine if GCTO fallback extraction is needed
def _needs_gcto_fallback(gcto_text: str) -> bool:
    # Fallback if empty or too short
    return not gcto_text or len(gcto_text.strip()) < 20
import re
# Section header patterns for detection logic (compiled regex)
SECTION_PATTERNS = [
    (re.compile(r"^gcto updates$", re.IGNORECASE), "gcto_updates"),
    (re.compile(r"^weekly digest$", re.IGNORECASE), "weekly_digest"),
    (re.compile(r"^key projects & hot topics$", re.IGNORECASE), "key_projects_hot_topics"),
    (re.compile(r"^it efficiency initiatives[\s–-]+cost optimization$", re.IGNORECASE), "cost_optimization"),
    (re.compile(r"^executive summ[ae]ry[\s–-]+rfx & cost optimization\*?$", re.IGNORECASE), "executive_summary_rfx_cost"),
    (re.compile(r"^rfx status$", re.IGNORECASE), "rfx_status"),
    (re.compile(r"^delayed rfps?$", re.IGNORECASE), "delayed_rfps"),
]

# Section order for extraction logic
ORDERED_SECTION_KEYS = [
    "gcto_updates",
    "weekly_digest",
    "key_projects_hot_topics",
    "cost_optimization",
    "executive_summary_rfx_cost",
    "rfx_status",
    "delayed_rfps",
]

import re
# Regex for date extraction (e.g., 25-Feb-2026) with capture groups
DATE_RE = re.compile(r"\b(\d{1,2})[-\s]([A-Za-z]{3,9})[-\s](\d{4})\b", re.IGNORECASE)

import re
# Regex for week label normalization (e.g., WK-08 25-Feb-2026) — same-line fast path
WEEK_RE = re.compile(r"WK[-_\s]?(\d{1,2})\s*([0-9]{1,2}[\s-][A-Za-z]{3,9}[\s-][0-9]{4})", re.IGNORECASE)
# Helpers for multi-line week detection
_WEEK_LABEL_RE = re.compile(r"\bWK[-_\s]?(\d{1,2})\b", re.IGNORECASE)
_DATE_LINE_RE = re.compile(r"\b\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{4}\b", re.IGNORECASE)
# Section key to title mapping for test compatibility
SECTION_NAME_TO_TITLE = {
    "gcto_updates": "GCTO Updates",
    "weekly_digest": "Weekly Digest",
    "key_projects_hot_topics": "Key Projects & Hot Topics",
    "cost_optimization": "IT Efficiency Initiatives - Cost Optimization",
    "executive_summary_rfx_cost": "Executive Summary – RFx & Cost Optimization",
    "rfx_status": "RFx Status",
    "delayed_rfps": "Delayed RFPs",
}
# Helper for test compatibility: fallback GCTO extraction
# More robust fallback for GCTO updates extraction
def extract_gcto_updates_fallback(raw_week_text: str) -> str:
    text = raw_week_text or ""
    if not text.strip():
        return ""

    _DATE_STANDALONE = re.compile(
        r"^(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})$"
        r"|^(\d{1,2})[-/]([A-Za-z]{3,9})[-/](\d{4})$"
    )
    _STATUS_KEYWORDS = {"on track", "completed", "delayed", "pending"}
    _SECTION_STOPS = {"weekly digest", "key projects", "it efficiency", "executive summary", "rfx status", "delayed rfp"}
    # Person name with initial — marks a GCTO card owner line
    _OWNER_NAME_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z]\.)+\s+[A-Z][a-z]+")

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # ── Strategy 1: section-header scan ──────────────────────────────────────
    try:
        start = next(i for i, l in enumerate(lines) if l.lower().startswith("gcto updates"))
    except StopIteration:
        start = -1

    block: List[str] = []
    if start >= 0:
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if any(lines[i].lower().startswith(h) for h in _SECTION_STOPS):
                candidate_block = [
                    ln for ln in lines[start + 1:i]
                    if ln.strip() and not _is_boilerplate_line(ln)
                ]
                if candidate_block:
                    end = i
                    block = lines[start + 1:end]
                # Whether or not there's content, stop at the first section boundary
                break
        else:
            block = lines[start + 1:end]

    # ── Strategy 2: direct card scan ─────────────────────────────────────────
    # If the section-header approach yielded no real card content, scan the full
    # text for GCTO card anchors: a status keyword followed by an owner name line.
    real_content = [ln for ln in block if ln.strip() and not _is_boilerplate_line(ln)]
    if not real_content:
        block = []
        for i, line in enumerate(lines):
            low = line.lower().strip()
            if low in _STATUS_KEYWORDS:
                # Look ahead: next non-empty line should be an owner name or "Project Owner"
                lookahead = [lines[j] for j in range(i+1, min(i+4, len(lines))) if lines[j].strip()]
                if lookahead and (
                    _OWNER_NAME_RE.match(lookahead[0])
                    or "project owner" in lookahead[0].lower()
                ):
                    # Collect this card: status + lines until due date found (then stop)
                    # A GCTO card is: status, owner name, "Project Owner", title, date
                    card_lines = [line]
                    date_seen = False
                    for j in range(i+1, min(i+15, len(lines))):
                        nxt = lines[j].strip()
                        if not nxt:
                            continue
                        nxt_low = nxt.lower()
                        # Stop at next card or section boundary
                        if j > i+1 and nxt_low in _STATUS_KEYWORDS:
                            break
                        if any(nxt_low.startswith(h) for h in _SECTION_STOPS):
                            break
                        # Stop after collecting the date line (card is complete)
                        if date_seen:
                            break
                        card_lines.append(nxt)
                        if _DATE_STANDALONE.match(nxt):
                            date_seen = True
                    block.extend(card_lines)
                    block.append("")  # card separator

    # ── Build cards from block ────────────────────────────────────────────────
    cards: List[str] = []

    # ── Structured card builder ───────────────────────────────────────────────
    # Each card is assembled as labelled fields so the LLM can parse them cleanly:
    #   Status: On Track
    #   Owner: Sami H. Alzomaia
    #   Title: Develop a Proposal...
    #   Due date: 30 June 2026

    def _flush_card(fields: Dict[str, str]) -> Optional[str]:
        if not fields:
            return None
        parts = []
        if fields.get("status"):
            parts.append(f"Status: {fields['status']}")
        if fields.get("owner"):
            parts.append(f"Owner: {fields['owner']}")
        if fields.get("title"):
            parts.append(f"Title: {fields['title']}")
        if fields.get("due_date"):
            parts.append(f"Due date: {fields['due_date']}")
        return "\n".join(parts) if parts else None

    current: Dict[str, str] = {}
    title_lines: List[str] = []
    skip_next_project_owner = False

    for line in block:
        low = line.lower().strip()

        if _is_boilerplate_line(line):
            continue

        # Date line → due_date field (bare date OR already-labelled "Due date: ...")
        _due_label_match = re.match(r"^due\s*date\s*[:\-]\s*(.+)$", low)
        if _DATE_STANDALONE.match(line.strip()) or _due_label_match:
            date_value = _due_label_match.group(1).strip() if _due_label_match else line.strip()
            if title_lines:
                current["title"] = " ".join(title_lines).strip()
                title_lines = []
            current["due_date"] = date_value
            # Card is complete — flush
            card_str = _flush_card(current)
            if card_str:
                cards.append(card_str)
            current = {}
            continue

        # Status keyword → start new card
        if low in _STATUS_KEYWORDS:
            if current:
                if title_lines:
                    current["title"] = " ".join(title_lines).strip()
                    title_lines = []
                card_str = _flush_card(current)
                if card_str:
                    cards.append(card_str)
                current = {}
            current["status"] = line.strip().title()
            skip_next_project_owner = False
            continue

        # "Project Owner" label — the owner name was already collected on the previous line
        # (PDF layout: name appears before the "Project Owner" label)
        # Also handle fused format: "Sami H. Alzomaia Project Owner" on one line
        if "project owner" in low:
            # Check if name is fused on the same line: "Name Project Owner"
            fused = re.sub(r"\s*project owner\s*", "", line, flags=re.IGNORECASE).strip()
            if fused and _OWNER_NAME_RE.match(fused):
                current["owner"] = fused
            skip_next_project_owner = False
            continue

        # Owner name line: person name with initial (e.g. "Sami H. Alzomaia")
        if _OWNER_NAME_RE.match(line.strip()):
            current["owner"] = line.strip()
            skip_next_project_owner = False
            continue

        # Everything else accumulates as the title
        if current:  # only collect title lines if we're inside a card
            title_lines.append(line.strip())

    # Flush any remaining card
    if current:
        if title_lines:
            current["title"] = " ".join(title_lines).strip()
        card_str = _flush_card(current)
        if card_str:
            cards.append(card_str)

    return "\n\n".join([c for c in cards if c])

# Helper for test compatibility: weekly digest tail marker
def _looks_like_weekly_digest_tail(text: str) -> bool:
    value = (text or "").lower()
    markers = [
        "tech enablement",
        "mobile app assessment",
        "ipnoc assessment",
    ]
    return any(m in value for m in markers)
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Updated section anchors and extraction logic to match the visual structure in the provided images
import re

class StructuredAnalyst:
    SECTION_ANCHORS = [
        ("gcto", r"GCTO Updates"),
        ("weekly_digest", r"Weekly Digest"),
        ("key_projects", r"Key Projects & Hot Topics"),
        ("cost_optimization", r"IT Efficiency Initiatives - Cost Optimization"),
        ("executive_summary", r"Executive Summ[ae]ry[\s–-]+RFx & Cost Optimization\*?"),
        ("rfx_status", r"RFx Status"),
        ("delayed_rfps", r"Delayed RFPs"),
    ]

    def __init__(self, pdf_text):
        self.pdf_text = pdf_text
        self.sections = self._split_sections()

    def _split_sections(self):
        # Use regex to find section boundaries for robustness
        section_spans = {}
        for key, pattern in self.SECTION_ANCHORS:
            match = re.search(pattern, self.pdf_text, re.IGNORECASE)
            if match:
                section_spans[key] = match.start()
        # Sort by start index
        sorted_sections = sorted(section_spans.items(), key=lambda x: x[1])
        # Extract section text
        sections = {}
        for i, (key, idx) in enumerate(sorted_sections):
            start = idx
            end = sorted_sections[i + 1][1] if i + 1 < len(sorted_sections) else len(self.pdf_text)
            sections[key] = self.pdf_text[start:end].strip()
        return sections

    def get_section(self, section):
        return self.sections.get(section, "")

    def extract_gcto_updates(self):
        text = self.get_section("gcto")
        # Extract only the GCTO cards (3 cards, each with status, owner, date, and description)
        # Use regex to split on Project Owner or name patterns
        cards = re.split(r"(?=\bProject Owner\b|\bAbdullah H\. F Alfaifi\b|\bSami H\. Alzomaia\b|\bAhmed Alshaikh\b)", text)
        # Remove the anchor line
        if cards and cards[0].strip().startswith("GCTO Updates"):
            cards = cards[1:]
        # Clean up each card
        cleaned = [c.strip() for c in cards if c.strip()]
        return "\n\n".join(cleaned)

    def extract_weekly_digest(self):
        text = self.get_section("weekly_digest")
        # Extract 12 digest items, each with a number and a title
        # Use regex to find numbered items
        items = re.split(r"\n\s*\d+\s*\n", text)
        # Remove the anchor line
        if items and items[0].strip().startswith("Weekly Digest"):
            items = items[1:]
        # Clean up and join
        cleaned = [i.strip() for i in items if i.strip()]
        return "\n\n".join(cleaned)

    def extract_key_projects(self):
        text = self.get_section("key_projects")
        # Split on bullet or project title patterns
        # Use regex to find project blocks (title in bold or with a bullet)
        projects = re.split(r"\n\s*\d+\. |\n\s*• |\n\s*\u2022 |\n\s*\([a-zA-Z0-9]+\) ", text)
        # Remove the anchor line
        if projects and projects[0].strip().startswith("Key Projects & Hot Topics"):
            projects = projects[1:]
        cleaned = [p.strip() for p in projects if p.strip()]
        return "\n\n".join(cleaned)

    def extract_cost_optimization(self):
        text = self.get_section("cost_optimization")
        # Only the summary line
        summary_match = re.search(r"RFX Cost Optimization[\s~-]+Achieved in 2026", text)
        summary = summary_match.group(0) if summary_match else ""
        return summary

    def extract_executive_summary(self):
        text = self.get_section("executive_summary")
        # Extract the table block (Capex/Opex Savings, IT Platforms, Infrastructures, etc.)
        table_start = re.search(r"Capex Savings", text)
        if table_start:
            table = text[table_start.start():]
        else:
            table = text
        return table.strip()

    def extract_rfx_status(self):
        text = self.get_section("rfx_status")
        # Extract the year-to-date project overview and the two tables
        chart_match = re.search(r"Year-to-Date Project Overview", text)
        if chart_match:
            chart = text[chart_match.start():]
        else:
            chart = text
        return chart.strip()

    def extract_delayed_rfps(self):
        text = self.get_section("delayed_rfps")
        # Extract the delayed RFPs table
        table_match = re.search(r"Sub RFP Name[\s\S]+?Budget \(SAR\)[\s\S]+", text)
        if table_match:
            table = table_match.group(0)
        else:
            table = text

        return table.strip()






def _empty_sections() -> Dict[str, Any]:
    return {
        "gcto_updates": "",
        "weekly_digest": "",
        "key_projects_hot_topics": "",
        "cost_optimization": "",
        "executive_summary_rfx_cost": "",
        "executive_summary_rfx_cost_struct": {
            "capex_savings_2026_estimate": None,
            "opex_savings_2026_estimate": None,
            "domains": [],
            "tsa_efforts_values_m": [],
            "tec_validated_values_m": [],
            "raw_table_text": "",
        },
        "rfx_status": {
            "total_received": None,
            "total_approved": None,
            "total_in_progress": None,
            "total_cf_projects": None,
            "raw_section_text": "",
        },
        "rfx_status_struct": {
            "overview": {
                "received_2026": None,
                "approved_projects": None,
                "in_progress_rfps": None,
                "projects_2026": None,
                "cf_projects": None,
            },
            "pib_not_received_by_rfx": {
                "envelope_2026": None,
                "envelope_2025": None,
                "cf_2024": None,
                "cf_2023": None,
                "project_without_fn": None,
                "total": None,
            },
            "direct_value_mpa_projects_status": {
                "approved_by_rfx": None,
                "mpa_review_in_rfx": None,
                "pib_in_progress": None,
                "total": None,
            },
            "raw_table_text": "",
        },
        "delayed_rfps_struct": {
            "rows": [],
            "raw_table_text": "",
        },
        "delayed_rfps": [],
    }


def _normalize_week(text: str) -> Tuple[str, Optional[int]]:
    # Pass 1: same-line fast path (e.g. "WK-08 25-Feb-2026")
    match = WEEK_RE.search(text or "")
    if match:
        num = int(match.group(1))
        return f"WK-{num:02d}", num

    # Pass 2: week label and date may be on separate lines (within 3 lines of each other)
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        wm = _WEEK_LABEL_RE.search(line)
        if wm:
            num = int(wm.group(1))
            # look ahead up to 3 lines for a date
            for j in range(i, min(i + 4, len(lines))):
                if _DATE_LINE_RE.search(lines[j]):
                    return f"WK-{num:02d}", num
            # week label found but no nearby date — still return the week
            return f"WK-{num:02d}", num
    return "", None


def _parse_date_iso(text: str) -> Optional[str]:
    match = DATE_RE.search(text or "")
    if not match:
        return None
    day = int(match.group(1))
    month_str = match.group(2).title()[:3]
    year_raw = match.group(3)
    year = datetime.now(timezone.utc).year
    if year_raw:
        year = int(year_raw)
        if year < 100:
            year += 2000
    try:
        return datetime.strptime(f"{day:02d}-{month_str}-{year}", "%d-%b-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _detect_section(line: str) -> str:
    value = (line or "").strip().strip("-:• ")
    for pattern, key in SECTION_PATTERNS:
        if pattern.match(value):
            return key
    return ""


def _split_page_sections(page_text: str) -> List[Tuple[str, str]]:
    lines = [ln.rstrip() for ln in (page_text or "").splitlines()]
    current_key = ""
    buffer: List[str] = []
    out: List[Tuple[str, str]] = []

    def _flush() -> None:
        nonlocal buffer
        if current_key and buffer:
            text = "\n".join([b for b in buffer if b.strip()]).strip()
            if text:
                out.append((current_key, text))
        buffer = []

    for line in lines:
        section = _detect_section(line)
        if section:
            _flush()
            current_key = section
            continue
        if current_key:
            buffer.append(line)

    _flush()
    return out


def _is_boilerplate_line(line: str) -> bool:
    low = " ".join((line or "").split()).strip().lower()
    if not low:
        return True
    if low in {
        "sector weekly report",
        "technology strategy",
        "architecture",
        "technology strategy architecture",
        "technology strategy and architecture sector",
        "weekly digest",
        "gcto updates",
    }:
        return True
    if re.match(r"^wk[-\s]?\d{1,2}$", low):
        return True
    if re.match(r"^\d+(?:\s+\d+)+$", low):
        return True
    return False


def _clean_section_text(section_key: str, section_text: str) -> str:
    lines = [" ".join(raw.split()).strip("-•: ") for raw in (section_text or "").splitlines()]
    lines = [line for line in lines if line and not _is_boilerplate_line(line)]

    if section_key == "gcto_updates":
        lines = [line for line in lines if not any(token in line.lower() for token in ["satellite/ ntn", "satellite/ntn", "esm optimization"])]

    if section_key == "weekly_digest":
        # Exact section header names that signal we've crossed into Key Projects territory
        stop_markers = {
            "compliance",
            "enterprise architecture (star)",
            "technology governance & arb",
            "gtu blueprint 2026",
            "technology strategy",
        }
        # Person-name pattern: requires at least one initial (e.g. "Sami H. Alzomaia")
        # Plain title-case topic headings must NOT match
        _PERSON_NAME_RE = re.compile(
            r"^[A-Z][a-z]+(?:\s+[A-Z]\.)+\s+[A-Z][a-z]+"  # Firstname I. Lastname (initial required)
        )
        filtered: List[str] = []
        in_gcto_card = False  # track when we're inside a GCTO card bleed-in
        for line in lines:
            low = line.lower()
            # Only stop on exact match — "Compliance & Governance" is a digest topic, not a stop
            if low in stop_markers:
                break
            if low in {"on track", "completed", "project owner", "delayed", "pending"}:
                in_gcto_card = True
                continue
            # Skip standalone date lines (e.g. "30 June 2026")
            if re.search(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b", line):
                continue
            # Skip GCTO card project titles bleeding in
            if "develop a proposal for implementing circular economy" in low:
                continue
            # Skip person-name lines (GCTO card owner names bleeding into digest)
            if _PERSON_NAME_RE.match(line.strip()):
                in_gcto_card = True
                continue
            # Skip GCTO card content fragments (partial project title lines)
            if "principles across all subsidiaries" in low:
                continue
            if "offered by solutions" in low:
                continue
            # Skip cost optimization footer leaking in
            if "rfx cost optimization" in low:
                continue
            # Skip fused multi-heading lines (3+ known topic titles concatenated by PDF)
            known_headings = [
                "site forecasting using ml", "technology rationalization", "iram milestones",
                "tsba playbook", "2g shutdown", "technology strategy contribution",
                "cloudification strategy", "fixed fundamental plan", "public cloud architecture",
            ]
            if sum(1 for h in known_headings if h in low) >= 2:
                continue
            # If we were in a GCTO card, skip lines that look like a bare person name
            # (two title-case words, no punctuation, no digits) — e.g. "Ahmed Alshaikh"
            if in_gcto_card and re.fullmatch(r"[A-Z][a-z]+\s+[A-Z][a-z]+", line.strip()):
                continue
            in_gcto_card = False
            filtered.append(line)
        lines = filtered

    if section_key == "cost_optimization":
        normalized_cost: List[str] = []
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            low = line.lower()
            if re.fullmatch(r"0+(?:\.0+)?", line) and idx + 1 < len(lines) and lines[idx + 1].lower() == "msar":
                normalized_cost.append("0 mSAR")
                idx += 2
                continue
            if low in {
                "it efficiency initiatives - cost optimization",
                "rfx cost optimization ~ achieved in 2026",
            }:
                normalized_cost.append(line)
                idx += 1
                continue
            if re.fullmatch(r"0(?:\.0+)?\s*msar", low):
                normalized_cost.append("0 mSAR")
                idx += 1
                continue
            idx += 1
        lines = normalized_cost

    if section_key == "executive_summary_rfx_cost":
        allowed_tokens = [
            "capex savings",
            "opex savings",
            "2026 estimate",
            "tsa efforts",
            "tec validated",
            "it platforms",
            "infrastructures",
            "ai & data",
            "sea",
            "csdm",
            "expenditure",
            "capex",
            "opex",
        ]
        filtered_exec: List[str] = []
        for line in lines:
            low = line.lower()
            if re.match(r"^w\d{1,2}$", low):
                break
            if low in {"received closed", "delayed rfps", "sub rfp name"}:
                break
            if "sub rfp name impacted domain" in low:
                break
            if any(token in low for token in allowed_tokens):
                filtered_exec.append(line)
                continue
            if re.search(r"\b\d+(?:\.\d+)?\s*m\b", low):
                filtered_exec.append(line)
                continue
        lines = filtered_exec

    if section_key == "rfx_status":
        filtered_rfx: List[str] = []
        for line in lines:
            low = line.lower()
            if low == "delayed rfps":
                break
            if "capexdelayed" in low or "opexdelayed" in low:
                break
            if re.match(r"^w\d{1,2}\b", low):
                continue
            if re.match(r"^\d{1,2}[-/](?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*$", low):
                continue
            if low in {"received", "closed", "received closed"}:
                continue
            filtered_rfx.append(line)
        lines = filtered_rfx

    deduped: List[str] = []
    seen = set()
    cost_zero_count = 0
    for line in lines:
        if section_key == "cost_optimization" and line.lower() == "0 msar":
            if cost_zero_count < 3:
                deduped.append(line)
                cost_zero_count += 1
            continue
        key = re.sub(r"\W+", " ", line.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(line)

    return "\n".join(deduped).strip()


def _group_pages_by_week(pages: List[Tuple[int, str]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    current_week = ""

    for _, page_text in pages:
        page_week, page_week_num = _normalize_week(page_text)
        page_date_iso = _parse_date_iso(page_text)

        if page_week:
            current_week = page_week
            record = grouped.setdefault(
                page_week,
                {
                    "week_label": page_week,
                    "week_num": page_week_num,
                    "report_date": page_date_iso,
                    "pages": [],
                },
            )
            if not record.get("week_num") and page_week_num:
                record["week_num"] = page_week_num
            if page_date_iso:
                record["report_date"] = page_date_iso
        elif not current_week:
            continue

        record = grouped.get(current_week)
        if not record:
            continue
        record["pages"].append(page_text)
        if not record.get("report_date") and page_date_iso:
            record["report_date"] = page_date_iso

    return grouped


def _extract_sections_by_order(week_text: str) -> Dict[str, str]:
    lines = [ln.rstrip() for ln in (week_text or "").splitlines()]
    if not lines:
        return {}

    # Resilient scan: find ALL section header positions in document order.
    # No forward-only cursor — a missing section never blocks detection of later ones.
    found: List[Tuple[str, int]] = []
    for idx, line in enumerate(lines):
        key = _detect_section(line)
        if key:
            # Avoid consecutive duplicates (same header repeated on adjacent lines)
            if not found or found[-1][0] != key:
                found.append((key, idx))

    if not found:
        return {}

    # Slice content between consecutive found headers
    out: Dict[str, str] = {}
    for pos_idx, (section_key, start_idx) in enumerate(found):
        end_idx = found[pos_idx + 1][1] if pos_idx + 1 < len(found) else len(lines)
        block = "\n".join(lines[start_idx + 1: end_idx]).strip()
        if block:
            # If the same section key appears more than once, coalesce the content
            if section_key in out:
                out[section_key] = out[section_key] + "\n" + block
            else:
                out[section_key] = block
    return out


def _extract_cost_optimization_fallback(raw_week_text: str) -> str:
    lines = [" ".join(raw.split()).strip("-•: ") for raw in (raw_week_text or "").splitlines()]
    lines = [line for line in lines if line and not _is_boilerplate_line(line)]
    if not lines:
        return ""

    idx_it = next((i for i, line in enumerate(lines) if "it efficiency initiatives - cost optimization" in line.lower()), -1)
    idx_rfx = next((i for i, line in enumerate(lines) if "rfx cost optimization ~ achieved in" in line.lower()), -1)

    start_idx = -1
    if idx_it >= 0 and idx_rfx >= 0:
        start_idx = min(idx_it, idx_rfx)
    elif idx_it >= 0:
        start_idx = idx_it
    elif idx_rfx >= 0:
        start_idx = idx_rfx

    if start_idx < 0:
        return ""

    stop_markers = {
        "executive summary – rfx & cost optimization",
        "executive summary – rfx & cost optimization",
        "rfx status",
        "delayed rfps",
    }

    captured: List[str] = []
    for line in lines[start_idx : start_idx + 40]:
        low = line.lower()
        if captured and low in stop_markers:
            break
        captured.append(line)

    return _clean_section_text("cost_optimization", "\n".join(captured))


def _looks_like_weekly_digest_tail(text: str) -> bool:
    value = (text or "").lower()
    markers = [
        "tech enablement",
        "mobile app assessment",
        "ipnoc assessment",
    ]
    hits = sum(1 for marker in markers if marker in value)
    return hits >= 2


def _split_weekly_keyprojects_boundary(weekly_text: str) -> Tuple[str, str]:
    lines = [line for line in (weekly_text or "").splitlines()]
    if not lines:
        return "", ""

    start_markers = [
        "tech-refresh and migration to public cloud",
        "dr and resiliency",
        "erm engagement",
        "ia vacancies",
        "architecture guild",
        "reporting & executive visibility",
        "sea",
        "compliance",
        "enterprise architecture (star)",
        "technology governance & arb",
        "gtu blueprint 2026",
    ]

    start_idx = -1
    for idx, line in enumerate(lines):
        low = " ".join(line.split()).strip().lower()
        for marker in start_markers:
            # Exact match only — prevents "Compliance & Governance" matching "compliance"
            if low == marker:
                start_idx = idx
                break
        if start_idx >= 0:
            break

    if start_idx < 0:
        return weekly_text, ""

    weekly_head = "\n".join(lines[:start_idx]).strip()
    key_tail = "\n".join(lines[start_idx:]).strip()
    return weekly_head, key_tail


def _extract_weekly_digest_tail_from_key_projects(key_projects_text: str) -> Tuple[str, str]:
    lines = [line for line in (key_projects_text or "").splitlines()]
    if not lines:
        return "", ""

    start_idx = -1
    for idx, line in enumerate(lines):
        low = " ".join(line.split()).strip().lower()
        if low.startswith("tech enablement"):
            start_idx = idx
            break

    if start_idx < 0:
        return "", key_projects_text

    tail_text = "\n".join(lines[start_idx:]).strip()
    if not _looks_like_weekly_digest_tail(tail_text):
        return "", key_projects_text

    key_main = "\n".join(lines[:start_idx]).strip()
    return tail_text, key_main


def _extract_key_projects_fallback(raw_week_text: str) -> str:
    lines = [" ".join(raw.split()).strip("-•: ") for raw in (raw_week_text or "").splitlines()]
    lines = [line for line in lines if line and not _is_boilerplate_line(line)]
    if not lines:
        return ""

    start_markers = [
        "tech-refresh and migration to public cloud",
        "dr and resiliency",
        "erm engagement",
        "ia vacancies",
        "architecture guild",
        "reporting & executive visibility",
        "sea",
        "compliance",
        "enterprise architecture (star)",
        "technology governance & arb",
        "gtu blueprint 2026",
    ]
    stop_markers = [
        "it efficiency initiatives - cost optimization",
        "rfx cost optimization ~ achieved in",
        "executive summary – rfx & cost optimization",
        "rfx status",
        "delayed rfps",
        "key projects & hot topics",
        "tech enablement",
    ]

    start_idx = -1
    for idx, line in enumerate(lines):
        low = line.lower()
        if any(low.startswith(marker) for marker in start_markers):
            start_idx = idx
            break

    if start_idx < 0:
        return ""

    captured: List[str] = []
    for line in lines[start_idx:]:
        low = line.lower()
        if captured and any(low.startswith(marker) for marker in stop_markers):
            break
        captured.append(line)

    return _clean_section_text("key_projects_hot_topics", "\n".join(captured))


def _coalesce_text(existing: str, addition: str) -> str:
    existing_clean = (existing or "").strip()
    addition_clean = (addition or "").strip()
    if not existing_clean:
        return addition_clean
    if not addition_clean:
        return existing_clean
    if addition_clean.lower() in existing_clean.lower():
        return existing_clean
    return f"{existing_clean}\n{addition_clean}".strip()


def _parse_rfx_status(section_text: str) -> Dict[str, Any]:
    text = (section_text or "")
    lower = text.lower()

    def _capture(patterns: List[str]) -> Optional[int]:
        for pattern in patterns:
            match = re.search(pattern, lower, flags=re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1).replace(",", ""))
                except ValueError:
                    continue
        return None

    return {
        "total_received": _capture([r"(\d+)\s*rfps?\s*received", r"received\s*[:\-]?\s*(\d+)", r"(\d+)\s*on\s*hands?\s*rfps?"]),
        "total_approved": _capture([r"(\d+)\s*approved\s*projects?", r"approved\s*projects?\s*[:\-]?\s*(\d+)"]),
        "total_in_progress": _capture([r"(\d+)\s*(?:projects?\s*)?in\s*progress", r"in\s*progress\s*rfps?\s*[:\-]?\s*(\d+)"]),
        "total_cf_projects": _capture([r"(\d+)\s*cf\s*projects?", r"cf\s*projects?\s*[:\-]?\s*(\d+)"]),
        "raw_section_text": text.strip(),
    }


def _parse_rfx_status_table(section_text: str) -> Dict[str, Any]:
    text = (section_text or "").strip()
    lower = text.lower()

    def _capture(patterns: List[str]) -> Optional[int]:
        for pattern in patterns:
            match = re.search(pattern, lower, flags=re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1).replace(",", ""))
                except ValueError:
                    continue
        return None

    total_matches = [int(item) for item in re.findall(r"\btotal\b\D*(\d{1,3})", lower)]

    return {
        "overview": {
            "received_2026": _capture([r"(\d+)\s*rfps?\s*received", r"received\s*in\s*2026\D*(\d+)"]),
            "approved_projects": _capture([r"(\d+)\s*approved\s*projects?"]),
            "in_progress_rfps": _capture([r"(\d+)\s*in\s*progress\s*rfps?", r"in\s*progress\s*rfps?\D*(\d+)"]),
            "projects_2026": _capture([r"(\d+)\s*2026\s*projects?", r"2026\s*projects?\D*(\d+)"]),
            "cf_projects": _capture([r"(\d+)\s*cf\s*projects?"]),
        },
        "pib_not_received_by_rfx": {
            "envelope_2026": _capture([r"envelope\s*2026\D*(\d{1,3})"]),
            "envelope_2025": _capture([r"envelope\s*2025\D*(\d{1,3})"]),
            "cf_2024": _capture([r"cf\s*2024\D*(\d{1,3})"]),
            "cf_2023": _capture([r"cf\s*2023\D*(\d{1,3})"]),
            "project_without_fn": _capture([r"project\s*without\s*fn\D*(\d{1,3})"]),
            "total": total_matches[0] if len(total_matches) >= 1 else None,
        },
        "direct_value_mpa_projects_status": {
            "approved_by_rfx": _capture([r"approved\s*by\s*rfx\D*(\d{1,3})"]),
            "mpa_review_in_rfx": _capture([r"mpa\s*review\s*in\s*rfx\D*(\d{1,3})"]),
            "pib_in_progress": _capture([r"pib\s*in[-\s]*progress\D*(\d{1,3})"]),
            "total": total_matches[1] if len(total_matches) >= 2 else None,
        },
        "raw_table_text": text,
    }


def _parse_executive_summary_table(section_text: str) -> Dict[str, Any]:
    text = (section_text or "").strip()
    lines = [" ".join(line.split()).strip() for line in text.splitlines() if line.strip()]
    lower_lines = [line.lower() for line in lines]

    amount_matches = re.findall(r"\b\d+(?:\.\d+)?\s*M\b", text, flags=re.IGNORECASE)

    domains = [
        domain
        for domain in ["IT Platforms", "Infrastructures", "AI & Data", "SEA", "CSDM"]
        if domain.lower() in "\n".join(lower_lines)
    ]

    tsa_values = []
    tec_values = []
    for idx, line in enumerate(lines):
        low = line.lower()
        window = " ".join(lines[idx : min(len(lines), idx + 2)])
        values = re.findall(r"\b\d+(?:\.\d+)?\s*M\b", window, flags=re.IGNORECASE)
        if "tsa effort" in low or "tsa efforts" in low:
            tsa_values.extend(values)
        if "tec validated" in low:
            tec_values.extend(values)

    def _uniq(items: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for item in items:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    return {
        "capex_savings_2026_estimate": amount_matches[0] if len(amount_matches) >= 1 else None,
        "opex_savings_2026_estimate": amount_matches[1] if len(amount_matches) >= 2 else None,
        "domains": domains,
        "tsa_efforts_values_m": _uniq(tsa_values),
        "tec_validated_values_m": _uniq(tec_values),
        "raw_table_text": text,
    }


def _extract_domain(line: str) -> Optional[str]:
    lower = line.lower()
    domains = [
        "mobility services",
        "corporate enablement",
        "field operation center",
        "network operation center",
        "billing & fulfilment management",
        "infrastructure excellence",
        "cloud",
        "network",
    ]
    for domain in domains:
        if domain in lower:
            return domain.title()
    return None


def _parse_delayed_rows(section_text: str) -> List[Dict[str, Any]]:
    """
    Parse delayed RFP rows from concatenated PDF text.

    Each row follows the column order:
      <sub_rfp_name> <impacted_domain> <pending_with> <CAPEX|OPEX> DELAYED <budget> <gd_name>

    Strategy: parse right-to-left from fixed structural anchors.
      1. budget   — rightmost large number  (e.g. 67,519,408)
      2. expense  — CAPEX or OPEX immediately before DELAYED
      3. status   — DELAYED or PENDING
      4. pending_with — TA-Domain or Supplier (immediately before CAPEX/OPEX)
      5. gd_name  — everything to the right of budget (tail of line)
      6. impacted_domain — token(s) immediately to the left of pending_with:
                           all-uppercase 2-4 char codes, optionally chained with - or _
      7. sub_rfp_name — everything to the left of impacted_domain
    """
    # Anchor patterns — order matters for right-to-left slicing
    _EXPENSE_STATUS_RE = re.compile(r"\b(CAPEX|OPEX)\s*DELAYED\b", re.IGNORECASE)
    _PENDING_WITH_RE   = re.compile(r"\b(TA-Domain|Supplier)\b", re.IGNORECASE)
    _BUDGET_RE         = re.compile(r"(\d[\d,]{4,})(?=[^,\d]|$)")
    # Impacted domain: one or more 2-4 uppercase-letter tokens chained by " - " or " _ "
    _DOMAIN_SC_RE      = re.compile(r"([A-Z]{2,4}(?:\s*[-_]\s*[A-Z]{2,4})*)\s*$")

    rows: List[Dict[str, Any]] = []

    # Join continuation lines: a line with no structural anchors followed by one that has them
    raw_lines = (section_text or "").splitlines()
    joined: List[str] = []
    i = 0
    while i < len(raw_lines):
        line = " ".join(raw_lines[i].split()).strip()
        if not line:
            i += 1
            continue
        norm = re.sub(r"\b(CAPEX|OPEX)DELAYED\b", r"\1 DELAYED", line, flags=re.IGNORECASE)
        has_anchor = bool(re.search(r"\b(CAPEX|OPEX)\s*DELAYED\b", norm, re.IGNORECASE))
        if not has_anchor and i + 1 < len(raw_lines):
            nxt = " ".join(raw_lines[i + 1].split()).strip()
            nxt_norm = re.sub(r"\b(CAPEX|OPEX)DELAYED\b", r"\1 DELAYED", nxt, flags=re.IGNORECASE)
            nxt_has_anchor = bool(re.search(r"\b(CAPEX|OPEX)\s*DELAYED\b", nxt_norm, re.IGNORECASE))
            # Only join if this line looks like a name fragment:
            # - must contain at least one lowercase letter (rules out ALL-CAPS headers)
            # - must not be a pure title-case phrase with no punctuation (section headers)
            # - must not look like a table header row (3+ column-header words)
            has_lowercase = bool(re.search(r"[a-z]", line))
            has_punctuation = bool(re.search(r"[-–()/&\d]", line))
            _hdr = line.lower()
            is_header = sum(1 for w in ("sub rfp", "impacted", "pending with", "expense", "budget") if w in _hdr) >= 3
            if nxt_has_anchor and nxt and has_lowercase and has_punctuation and not is_header:
                raw_lines[i + 1] = line + " " + nxt
                i += 1
                continue
        joined.append(line)
        i += 1

    for raw_line in joined:
        # Normalize fused CAPEXDELAYED / OPEXDELAYED
        line = re.sub(r"\b(CAPEX|OPEX)DELAYED\b", r"\1 DELAYED", raw_line, flags=re.IGNORECASE)
        line = " ".join(line.split()).strip()
        if len(line) < 12:
            continue
        lower = line.lower()

        # Must contain DELAYED or PENDING to be a data row
        if "delayed" not in lower and "pending" not in lower:
            continue
        # Skip header rows (contain multiple column-header words)
        header_words = ["sub rfp", "impacted domain", "pending with", "expense", "budget"]
        if sum(1 for w in header_words if w in lower) >= 3:
            continue

        # ── 1. expense + status ──────────────────────────────────────────────
        es_match = _EXPENSE_STATUS_RE.search(line)
        expense_type: Optional[str] = es_match.group(1).upper() if es_match else None
        status: Optional[str] = "delayed" if re.search(r"\bDELAYED\b", line, re.IGNORECASE) else (
            "pending" if re.search(r"\bPENDING\b", line, re.IGNORECASE) else None
        )

        # ── 2. budget ────────────────────────────────────────────────────────
        budget_val: Optional[int] = None
        budget_match = _BUDGET_RE.search(line)
        if budget_match:
            try:
                budget_val = int(budget_match.group(1).replace(",", ""))
            except ValueError:
                pass

        # ── 3. pending_with ──────────────────────────────────────────────────
        pw_match = _PENDING_WITH_RE.search(line)
        pending_with: Optional[str] = pw_match.group(1) if pw_match else None

        # ── 4. gd_name: text after the budget number ─────────────────────────
        gd_name: Optional[str] = None
        if budget_match:
            tail = line[budget_match.end():].strip()
            # Strip any leading digits/punctuation that fused with the budget (e.g. "000FUs")
            tail = re.sub(r"^\d+", "", tail).strip()
            tail = " ".join(tail.split()).strip(" -|–")
            if tail:
                gd_name = tail

        # ── 5. left segment: everything before CAPEX/OPEX DELAYED ────────────
        left = line[:es_match.start()].strip() if es_match else line

        # ── 6. impacted_domain: rightmost all-uppercase shortcode in left segment,
        #       immediately before pending_with ─────────────────────────────────
        # Trim pending_with from the right of left segment first
        if pw_match:
            pw_pos = left.rfind(pw_match.group(0))
            if pw_pos >= 0:
                left = left[:pw_pos].strip()

        impacted_domain: Optional[str] = None
        sc_match = _DOMAIN_SC_RE.search(left)
        if sc_match:
            candidate = sc_match.group(1).strip()
            # Validate: every token must be 2-4 uppercase letters
            parts = [p.strip() for p in re.split(r"[-_]", candidate) if p.strip()]
            if parts and all(re.fullmatch(r"[A-Z]{2,4}", p) for p in parts):
                impacted_domain = candidate
                left = left[:sc_match.start()].strip()

        # ── 7. sub_rfp_name: what remains in left ────────────────────────────
        sub_rfp_name = " ".join(left.split()).strip(" -|–") or line

        domain = impacted_domain or gd_name

        rows.append({
            "sub_rfp_name": sub_rfp_name,
            "impacted_domain": impacted_domain,
            "gd_name": gd_name,
            "expense": expense_type,
            "initiative_name": sub_rfp_name,
            "domain": domain,
            "budget_sar": budget_val,
            "status": status,
            "pending_with": pending_with,
            "expense_type": expense_type,
            "raw_row_text": line,
        })

    deduped: List[Dict[str, Any]] = []
    seen: set = set()
    for row in rows:
        key = (row.get("initiative_name") or "").lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _extract_delayed_block_fallback(raw_week_text: str) -> str:
    lines = [" ".join(raw.split()).strip("-•: ") for raw in (raw_week_text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    delayed_start = next((idx for idx, line in enumerate(lines) if line.lower() == "delayed rfps"), -1)
    if delayed_start < 0:
        return ""

    stop_markers = {"rfx status", "weekly digest", "gcto updates", "key projects & hot topics"}
    captured: List[str] = []
    for line in lines[delayed_start + 1 :]:
        low = line.lower()
        if low in stop_markers:
            break
        captured.append(line)
    return "\n".join(captured).strip()


def _merge_delayed_rows(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for rows in groups:
        for row in rows or []:
            key = (row.get("initiative_name") or "").lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
    return merged


def parse_structured_reports_from_pages(pages: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
    by_week = _group_pages_by_week(pages)
    reports: List[Dict[str, Any]] = []

    for week_label, week_record in by_week.items():
        week_text = "\n".join(week_record.get("pages", []))
        section_map = _extract_sections_by_order(week_text)
        report = {
            "week_label": week_label,
            "week_num": week_record.get("week_num"),
            "report_date": week_record.get("report_date"),
            "sections": _empty_sections(),
        }

        rfx_raw_for_delayed = ""
        for section_key in ORDERED_SECTION_KEYS:
            raw_section = section_map.get(section_key, "")
            cleaned_section = _clean_section_text(section_key, raw_section)

            if section_key == "rfx_status":
                rfx_raw_for_delayed = raw_section
                parsed = _parse_rfx_status(cleaned_section)
                current = report["sections"]["rfx_status"]
                for field in ["total_received", "total_approved", "total_in_progress", "total_cf_projects"]:
                    if parsed.get(field) is not None:
                        current[field] = parsed[field]
                current["raw_section_text"] = _coalesce_text(current.get("raw_section_text", ""), parsed.get("raw_section_text", ""))
                report["sections"]["rfx_status_struct"] = _parse_rfx_status_table(cleaned_section)
                continue

            if section_key == "delayed_rfps":
                parsed_rows = _parse_delayed_rows(cleaned_section)
                report["sections"]["delayed_rfps"] = parsed_rows
                report["sections"]["delayed_rfps_struct"] = {
                    "rows": parsed_rows,
                    "raw_table_text": cleaned_section,
                }
                continue

            report["sections"][section_key] = cleaned_section
            if section_key == "executive_summary_rfx_cost":
                report["sections"]["executive_summary_rfx_cost_struct"] = _parse_executive_summary_table(cleaned_section)

        delayed_from_section = report["sections"].get("delayed_rfps") or []
        # Only feed lines that contain a delayed/pending marker — avoids joining
        # section headers (e.g. "Year-to-Date Project Overview") with data rows
        rfx_delayed_lines = "\n".join(
            ln for ln in rfx_raw_for_delayed.splitlines()
            if re.search(r"\b(CAPEX|OPEX)DELAYED\b|\bDELAYED\b|\bPENDING\b", ln, re.IGNORECASE)
        ) if rfx_raw_for_delayed else ""
        delayed_from_rfx = _parse_delayed_rows(rfx_delayed_lines) if rfx_delayed_lines else []
        delayed_fallback_block = _extract_delayed_block_fallback(week_text)
        delayed_from_week = _parse_delayed_rows(delayed_fallback_block) if delayed_fallback_block else []

        merged_delayed = _merge_delayed_rows(delayed_from_section, delayed_from_week, delayed_from_rfx)
        if merged_delayed:
            report["sections"]["delayed_rfps"] = merged_delayed
            report["sections"]["delayed_rfps_struct"] = {
                "rows": merged_delayed,
                "raw_table_text": "\n".join(
                    part for part in [
                        report["sections"].get("delayed_rfps_struct", {}).get("raw_table_text", ""),
                        delayed_fallback_block,
                        rfx_raw_for_delayed,
                    ]
                    if (part or "").strip()
                ),
            }

        current_gcto = report["sections"].get("gcto_updates", "")
        if _needs_gcto_fallback(current_gcto):
            fallback_gcto = extract_gcto_updates_fallback(week_text)
            if fallback_gcto:
                report["sections"]["gcto_updates"] = _coalesce_text(current_gcto, fallback_gcto)

        weekly_text = report["sections"].get("weekly_digest", "")
        key_projects_text = report["sections"].get("key_projects_hot_topics", "")

        weekly_head, key_tail_from_weekly = _split_weekly_keyprojects_boundary(weekly_text)
        if key_tail_from_weekly:
            weekly_text = weekly_head
            key_projects_text = _coalesce_text(key_tail_from_weekly, key_projects_text)

        if "satellite/ ntn" in (weekly_text or "").lower():
            digest_tail, key_main = _extract_weekly_digest_tail_from_key_projects(key_projects_text)
            if digest_tail:
                # Strip any cost-optimization lines that bleed into the digest tail
                digest_tail_lines = [
                    ln for ln in digest_tail.splitlines()
                    if "rfx cost optimization" not in ln.lower()
                ]
                digest_tail = "\n".join(digest_tail_lines).strip()
                weekly_text = _coalesce_text(weekly_text, digest_tail)
                key_projects_text = key_main

        key_projects_fallback = _extract_key_projects_fallback(week_text)
        if key_projects_fallback:
            low_current = (key_projects_text or "").lower()
            low_fallback = key_projects_fallback.lower()
            needs_enrichment = len(" ".join((key_projects_text or "").split())) < 160
            if "gtu blueprint 2026" in low_fallback and "gtu blueprint 2026" not in low_current:
                needs_enrichment = True
            if "technology governance & arb" in low_fallback and "technology governance & arb" not in low_current:
                needs_enrichment = True
            if needs_enrichment:
                key_projects_text = key_projects_fallback

        report["sections"]["weekly_digest"] = weekly_text
        report["sections"]["key_projects_hot_topics"] = key_projects_text

        current_cost = report["sections"].get("cost_optimization", "")
        if current_cost and "rfx cost optimization ~ achieved in 2026" not in current_cost.lower() and "rfx cost optimization ~ achieved in 2026" in week_text.lower():
            report["sections"]["cost_optimization"] = _coalesce_text(current_cost, "RFX Cost Optimization ~ Achieved in 2026")
            current_cost = report["sections"]["cost_optimization"]
        if not (current_cost or "").strip():
            fallback_cost = _extract_cost_optimization_fallback(week_text)
            if fallback_cost:
                report["sections"]["cost_optimization"] = fallback_cost

        reports.append(report)

    reports.sort(key=lambda item: int(item.get("week_num") or 0))
    return reports


def load_structured_reports_json(s3_client: Any, bucket: str, key: str) -> List[Dict[str, Any]]:
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        payload = response["Body"].read().decode("utf-8")
        data = json.loads(payload)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("reports"), list):
            return data.get("reports", [])
        return []
    except Exception:
        return []


def save_structured_reports_json(
    s3_client: Any,
    bucket: str,
    key: str,
    reports: List[Dict[str, Any]],
    document_id: str,
    source_key: str,
) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "source_key": source_key,
        "reports": reports,
    }
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )


def merge_structured_reports(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for row in existing:
        week = row.get("week_label")
        if week:
            merged[week] = row
    for row in incoming:
        week = row.get("week_label")
        if week:
            merged[week] = row
    out = list(merged.values())
    out.sort(key=lambda item: int(item.get("week_num") or 0))
    return out


def classify_query_intent(query: str) -> Dict[str, Any]:
    q = (query or "").lower().strip()
    if ("gcto" in q and "update" in q) or re.search(r"\bshow\s+gcto\s+updates?\b", q):
        return {"intent": "gcto_updates"}
    # Web search intent — questions about external knowledge not in the reports
    _WEB_PATTERNS = re.compile(
        r"\b(current\s+(price|rate|cost|exchange|usd|sar|dollar)|"
        r"latest\s+news|what\s+is\s+the\s+(price|rate|cost)\s+of|"
        r"how\s+much\s+does\s+.+\s+cost|"
        r"databricks\s+pricing|aws\s+pricing|azure\s+pricing|"
        r"stock\s+price|market\s+cap|"
        r"weather|today.s\s+(news|update)|"
        r"who\s+is\s+the\s+(ceo|cto|president)|"
        r"when\s+was\s+.+\s+founded|"
        r"what\s+country|what\s+city|where\s+is)\b",
        re.IGNORECASE,
    )
    if _WEB_PATTERNS.search(q):
        return {"intent": "web_search"}
    # Also route to web search if query explicitly asks to search the web
    if any(k in q for k in ["search the web", "google", "search online", "look up online", "web search"]):
        return {"intent": "web_search"}
    if any(k in q for k in ["cost saving", "cost savings", "savings", "opex saving", "capex saving",
                              "money saved", "cost reduction", "cost optimize", "cost optimiz"]):
        return {"intent": "cost_savings"}
    # RFX/RFP numeric queries — must route to rfx_status so metrics are populated
    if any(k in q for k in ["rfp", "rfx"]):
        if any(k in q for k in ["status", "how many", "count", "received", "in progress",
                                  "in-progress", "approved", "delayed", "number of",
                                  "progress", "update", "pipeline", "latest", "overview",
                                  "summary", "report", "metrics", "numbers"]):
            return {"intent": "rfx_status"}
        # Bare RFP/RFX query with no other qualifier → default to rfx_status
        if len(q.split()) <= 5:
            return {"intent": "rfx_status"}
    if any(k in q for k in ["delayed", "pending initiative", "pending initiatives"]):
        return {"intent": "delayed_initiatives"}
    if "hot topic" in q or "major hot topic" in q:
        return {"intent": "hot_topics"}
    if "trend" in q or "anomal" in q:
        return {"intent": "trend_analysis"}
    if "compare" in q or "comparison" in q:
        return {"intent": "progress_comparison"}
    if "risk" in q:
        return {"intent": "risk_analysis"}
    if any(k in q for k in ["weekly summary", "weekly digest", "overall update", "overall updates",
                              "summary of", "week summary", "weekly update", "weekly updates",
                              "all sections", "full update", "full summary"]):
        return {"intent": "weekly_summary"}
    # that don't match any structured section intent — search all sections for the keyword
    _TOPIC_TRIGGERS = re.compile(
        r"\b(update on|status of|progress on|what about|tell me about|show me|any news on)\b",
        re.IGNORECASE,
    )
    if _TOPIC_TRIGGERS.search(q) or (
        len(q.split()) <= 8
        and not any(k in q for k in ["how many", "what is the rfx", "what are the delayed"])
        and not any(k in q for k in ["weekly summary", "weekly digest", "all sections"])
    ):
        # If the query is short and focused, treat as a topic search unless it's
        # clearly a section-level request
        _SECTION_LEVEL = {"weekly summary", "weekly digest", "key projects", "cost optimization",
                          "executive summary", "rfx status", "delayed rfps", "gcto updates"}
        if not any(s in q for s in _SECTION_LEVEL):
            return {"intent": "topic_search", "topic": q}
    if any(k in q for k in ["how many", "what is", "what are", "count", "number"]):
        return {"intent": "fact_lookup"}
    return {"intent": "weekly_summary"}


def resolve_target_weeks(query: str, available_weeks: List[str], intent: str) -> List[str]:
    ordered = sorted({w for w in available_weeks if w}, key=lambda wk: int(re.search(r"(\d+)", wk).group(1)))
    if not ordered:
        return []

    q = (query or "").lower()

    # Cross-week analysis queries need all weeks
    _ALL_WEEKS_PATTERNS = re.compile(
        r"\b(consistently|across\s+(all|most|every)\s+weeks?|most\s+weeks?|all\s+weeks?|"
        r"every\s+week|throughout|across\s+weeks?|week.over.week|week\s+by\s+week)\b",
        re.IGNORECASE,
    )
    if _ALL_WEEKS_PATTERNS.search(q):
        return ordered

    explicit = sorted({f"WK-{int(m):02d}" for m in re.findall(r"wk[-\s]?(\d{1,2})", q)}, key=lambda wk: int(re.search(r"(\d+)", wk).group(1)))
    if explicit:
        return [wk for wk in explicit if wk in ordered] or explicit

    if intent == "cost_savings":
        return ordered  # always all weeks — savings are scattered throughout

    last_n_match = re.search(r"last\s+(\d{1,2})\s+weeks?", q)
    if last_n_match:
        n = max(1, min(int(last_n_match.group(1)), 12))
        return ordered[-n:]

    if "last 3 months" in q:
        return ordered[-12:]

    if "latest" in q:
        n = 2 if intent == "weekly_summary" else 1
        return ordered[-n:]

    if intent == "gcto_updates":
        return ordered[-1:]

    if intent == "weekly_summary":
        return ordered[-4:]
    if intent in {"progress_comparison", "trend_analysis"}:
        return ordered[-5:]
    if intent == "delayed_initiatives":
        return ordered[-11:]  # ~3 months = all available weeks
    if intent == "topic_search":
        return ordered[-3:]
    return ordered[-1:]


def _reports_by_week(structured_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {row.get("week_label", ""): row for row in structured_data if row.get("week_label")}


def get_structured_context(intent: str, target_weeks: List[str], structured_data: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
    week_map = _reports_by_week(structured_data)
    selected = [week_map[wk] for wk in target_weeks if wk in week_map]
    if not selected:
        return {"intent": intent, "target_weeks": target_weeks, "evidence": [], "metrics": {}}

    evidence: List[str] = []
    metrics: Dict[str, Any] = {}
    delayed_rows: List[Dict[str, Any]] = []

    def _add_section_text(week: str, section_key: str) -> None:
        text = selected_by_week[week]["sections"].get(section_key, "")
        if text:
            evidence.append(f"{week} | {SECTION_NAME_TO_TITLE.get(section_key, section_key)} | {text[:1000]}")

    selected_by_week = {row["week_label"]: row for row in selected}

    for week in target_weeks:
        if week not in selected_by_week:
            continue
        sections = selected_by_week[week]["sections"]

        if intent == "gcto_updates":
            value = sections.get("gcto_updates", "")
            if value:
                # If the stored text is already structured (has "Status:" labels), use as-is.
                # Otherwise, re-run the structured card builder so the LLM always gets
                # clearly labelled fields: Status: / Owner: / Title: / Due date:
                if "status:" not in value.lower():
                    value = extract_gcto_updates_fallback(value) or value
                evidence.append(f"{week} | GCTO Updates | {value[:1200]}")
            continue

        if intent == "weekly_summary":
            for sec in ["weekly_digest", "key_projects_hot_topics", "gcto_updates"]:
                value = sections.get(sec, "")
                if value:
                    evidence.append(f"{week} | {SECTION_NAME_TO_TITLE[sec]} | {value[:500]}")

        elif intent == "hot_topics":
            for sec in ["weekly_digest", "key_projects_hot_topics"]:
                value = sections.get(sec, "")
                if value:
                    evidence.append(f"{week} | {SECTION_NAME_TO_TITLE[sec]} | {value[:1000]}")

        elif intent == "rfx_status":
            status = sections.get("rfx_status", {}) or {}
            received = status.get("total_received")
            approved = status.get("total_approved")
            in_progress = status.get("total_in_progress")
            cf_projects = status.get("total_cf_projects")
            metrics[week] = {
                "total_received": received,
                "total_approved": approved,
                "total_in_progress": in_progress,
                "total_cf_projects": cf_projects,
            }
            # Always inject a plain-text summary of the key numbers so the LLM
            # sees them directly in evidence (not just in the metrics block)
            struct = sections.get("rfx_status_struct", {}) or {}
            overview = struct.get("overview", {}) or {}
            week_delayed_rows = sections.get("delayed_rfps", []) or []
            numeric_summary = (
                f"RFPs received in 2026: {received}. "
                f"Approved projects: {approved}. "
                f"In-progress RFPs: {in_progress}. "
                f"CF projects: {cf_projects}. "
                f"Total 2026 projects: {overview.get('projects_2026', 'N/A')}. "
                f"Delayed RFPs this week: {len(week_delayed_rows)}."
            )
            evidence.append(f"{week} | RFx Status Numbers | {numeric_summary}")
            raw = status.get("raw_section_text", "")
            if raw:
                evidence.append(f"{week} | RFx Status | {raw[:800]}")
            delayed_rows.extend(week_delayed_rows)

        elif intent == "cost_savings":            # Extract only sentences/lines containing savings amounts
            import re as _re
            _SAVINGS_KW = ["saving", "saved", "msar", "cost reduction", "opex reduction",
                           "capex saving", "cost saving", "cost optimiz", "sar savings",
                           "realized saving", "achieved saving", "cost saved"]
            _SAR_AMOUNT_RE = _re.compile(
                r'\d+[\.,]?\d*\s*(?:m\s*sar|msar|k\s*sar|sar|m\b)', re.IGNORECASE
            )
            for sec in ["weekly_digest", "key_projects_hot_topics"]:
                value = sections.get(sec, "")
                if not value:
                    continue
                # Join adjacent lines into sliding windows of 3 to catch multi-line savings
                raw_lines = [l.strip() for l in value.splitlines() if l.strip()]
                savings_snippets = []
                for i, line in enumerate(raw_lines):
                    # Create a window of this line + next 2 lines
                    window = " ".join(raw_lines[i:i+3])
                    window_lower = window.lower()
                    if (any(kw in window_lower for kw in _SAVINGS_KW)
                            and _SAR_AMOUNT_RE.search(window_lower)
                            and len(window) > 10):
                        snippet = window[:200]
                        if snippet not in savings_snippets:
                            savings_snippets.append(snippet)
                if savings_snippets:
                    combined = " || ".join(savings_snippets[:6])
                    evidence.append(f"{week} | Cost Savings | {combined[:800]}")

        elif intent == "delayed_initiatives":
            delayed_rows.extend(sections.get("delayed_rfps", []) or [])
            extra = sections.get("executive_summary_rfx_cost", "")
            if extra:
                evidence.append(f"{week} | Executive Summary – RFx & Cost Optimization | {extra[:900]}")
            # Also include key_projects for pending strategic initiatives (non-RFP blockers)
            kp = sections.get("key_projects_hot_topics", "")
            if kp:
                kp_lower = kp.lower()
                _PENDING_KW = [
                    "pending", "not yet", "awaiting", "blocked", "no progress",
                    "not initiated", "deferred", "postponed", "unable to progress",
                    "limited engagement", "not formally", "remains pending",
                    "validation", "approval pending", "under review",
                ]
                if any(kw in kp_lower for kw in _PENDING_KW):
                    evidence.append(f"{week} | Key Projects & Hot Topics | {kp[:600]}")

        elif intent == "risk_analysis":
            for sec in ["weekly_digest", "key_projects_hot_topics", "executive_summary_rfx_cost"]:
                value = sections.get(sec, "")
                if value:
                    evidence.append(f"{week} | {SECTION_NAME_TO_TITLE[sec]} | {value[:1000]}")
            delayed_rows.extend(sections.get("delayed_rfps", []) or [])

        elif intent in {"progress_comparison", "trend_analysis"}:
            status = sections.get("rfx_status", {}) or {}
            week_delayed_rows = sections.get("delayed_rfps", []) or []
            metrics[week] = {
                "total_received": status.get("total_received"),
                "total_approved": status.get("total_approved"),
                "total_in_progress": status.get("total_in_progress"),
                "total_cf_projects": status.get("total_cf_projects"),
                "delayed_count": len(week_delayed_rows),
            }
            if status.get("raw_section_text"):
                evidence.append(f"{week} | RFx Status | {status.get('raw_section_text')[:900]}")
            for sec in ["weekly_digest", "key_projects_hot_topics", "cost_optimization"]:
                value = sections.get(sec, "")
                if value:
                    evidence.append(f"{week} | {SECTION_NAME_TO_TITLE[sec]} | {value[:800]}")
            delayed_rows.extend(week_delayed_rows)

        else:
            # topic_search or fact_lookup: scan ALL content sections for the query keyword
            # Extract meaningful keywords (skip stop words)
            # Note: min length is 2 to catch short but meaningful terms like "cv", "ia"
            _STOP = {"what", "is", "the", "are", "on", "in", "of", "for", "and", "or",
                     "a", "an", "me", "my", "any", "tell", "show", "give", "about",
                     "update", "status", "progress", "latest", "recent", "current",
                     "how", "many", "were", "was", "did", "has", "have", "been",
                     "made", "it", "to", "as", "at", "by", "its", "with", "from"}
            topic_words = [w for w in (query or "").lower().split() if len(w) >= 2 and w not in _STOP]
            # Expand compound terms: "tech-refresh" → also match "tech" and "refresh"
            expanded = set(topic_words)
            for w in list(topic_words):
                if "-" in w:
                    expanded.update(w.split("-"))
            topic_words = list(expanded)
            all_sections = [
                "gcto_updates",
                "weekly_digest",
                "key_projects_hot_topics",
                "cost_optimization",
                "executive_summary_rfx_cost",
            ]
            for sec in all_sections:
                value = sections.get(sec, "")
                if not value:
                    continue
                val_lower = value.lower()
                # Include section if any meaningful topic keyword appears in it
                if not topic_words or any(word in val_lower for word in topic_words):
                    evidence.append(f"{week} | {SECTION_NAME_TO_TITLE[sec]} | {value[:1000]}")

    if delayed_rows:
        delayed_rows = sorted(
            delayed_rows,
            key=lambda row: int(row.get("budget_sar") or 0),
            reverse=True,
        )
        deduped = []
        seen = set()
        for row in delayed_rows:
            key = (row.get("initiative_name") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        delayed_rows = deduped[:12]

    # Build cross-week RFP consistency map when multiple weeks are in scope
    # This lets the LLM answer "which RFP appeared in the most weeks"
    if len(target_weeks) > 1 and intent in {"rfx_status", "delayed_initiatives", "progress_comparison", "trend_analysis"}:
        consistency: Dict[str, int] = {}
        for wk in target_weeks:
            if wk not in week_map:
                continue
            for row in (week_map[wk]["sections"].get("delayed_rfps", []) or []):
                name = (row.get("initiative_name") or row.get("sub_rfp_name") or "").strip()
                if name:
                    consistency[name] = consistency.get(name, 0) + 1
        if consistency:
            top = sorted(consistency.items(), key=lambda x: x[1], reverse=True)[:5]
            consistency_lines = [f"{name} (appeared in {count} weeks)" for name, count in top]
            consistency_entry = (
                "Cross-week | Delayed RFP Consistency | Most consistently delayed: "
                + "; ".join(consistency_lines)
            )
            # Insert at the front so the LLM sees it before the budget-sorted list
            evidence.insert(0, consistency_entry)

    return {
        "intent": intent,
        "target_weeks": target_weeks,
        "evidence": evidence[:30],
        "metrics": metrics,
        "delayed_rfps": delayed_rows,
    }


def _format_metrics(metrics: Dict[str, Any]) -> str:
    if not metrics:
        return "- No metrics available"
    lines: List[str] = []
    for week in sorted(metrics.keys(), key=lambda wk: int(re.search(r"(\d+)", wk).group(1))):
        row = metrics.get(week, {})
        delayed_part = f", delayed={row['delayed_count']}" if row.get("delayed_count") is not None else ""
        lines.append(
            f"- {week}: received={row.get('total_received')}, approved={row.get('total_approved')}, "
            f"in_progress={row.get('total_in_progress')}, cf_projects={row.get('total_cf_projects')}{delayed_part}"
        )
    return "\n".join(lines)


def build_structured_prompt(query: str, intent: str, context: Dict[str, Any]) -> str:
    target_weeks = context.get("target_weeks", [])
    evidence = context.get("evidence", [])
    metrics = context.get("metrics", {})
    delayed_rfps = context.get("delayed_rfps", [])

    delayed_lines = []
    for row in delayed_rfps[:8]:
        delayed_lines.append(
            f"- {row.get('initiative_name')} | budget_sar={row.get('budget_sar')} | domain={row.get('domain')} | "
            f"status={row.get('status')} | pending_with={row.get('pending_with')} | expense_type={row.get('expense_type')}"
        )
    delayed_block = "\n".join(delayed_lines) if delayed_lines else "- None"

    # Pull out the consistency line from evidence and put it in its own block
    # so it's never trimmed by the prompt budget
    consistency_block = ""
    filtered_evidence = []
    for e in evidence[:24]:
        if e.startswith("Cross-week | Delayed RFP Consistency"):
            consistency_block = e.split("|", 2)[-1].strip()
        else:
            filtered_evidence.append(e)
    evidence = filtered_evidence

    instruction_map = {
        "gcto_updates": (
            "Output exactly: Latest GCTO Updates (WK-XX) followed by one bullet per card. "
            "Each card in the evidence is structured as: Status: / Owner: / Title: / Due date: — "
            "extract and display all four fields. Never output N/A if the field is present in the evidence."
        ),
        "topic_search": (
            "The user is asking about a specific topic. Search ALL provided evidence sections for any mention "
            "of the topic. Synthesize findings across sections into a concise update: what is happening, "
            "current status, and any relevant metrics or owners. If the topic appears in multiple sections, "
            "combine the information. Do not limit to one section."
        ),
        "weekly_summary": (
            "VP-level weekly summary. Structure as: one section per week (WK-XX label), each with 3-5 "
            "bullet points covering the most significant developments — decisions made, savings achieved, "
            "risks escalated, milestones hit or missed. End with a 2-line Executive Takeaway covering "
            "the most critical item and any action required. Be concise and factual. No filler phrases. "
            "IMPORTANT: Every week in the scope MUST have a section. If evidence exists for a week, "
            "extract highlights from it — do NOT say 'not available'. "
            "The weekly digest evidence starts with a number (e.g. '1\\nTU Data Center Strategy') — "
            "ignore the leading number and treat the rest as the digest content."
        ),
        "hot_topics": (
            "VP-level hot topics brief. List 5-8 themes with the most strategic significance. "
            "For each: one line on what happened, one line on implication or next step. "
            "End with top 2 items requiring VP attention."
        ),
        "rfx_status": (
            "VP-level RFX status. Lead with the headline numbers (received, approved, in-progress, delayed). "
            "Call out week-over-week change if multiple weeks in scope. "
            "List top 3 delayed RFPs by budget with owner and blocker. "
            "If the user asks which RFP has been delayed the most weeks, answer using the "
            "'Cross-week RFP consistency analysis' section — NOT the budget-sorted list. "
            "End with one-line strategic note on pipeline health."
        ),
        "delayed_initiatives": (
            "VP-level delayed initiatives report. Two sections: "
            "1) RFP Delays — list by budget descending, include domain, pending-with, and how many weeks delayed. "
            "2) Strategic Pending Items — non-RFP initiatives that are blocked, not yet initiated, or awaiting decision. "
            "End with total budget at risk and top bottleneck (TA-Domain vs Supplier split)."
        ),
        "progress_comparison": (
            "VP-level progress comparison. Show a clean week-by-week table: received / approved / in-progress / delayed. "
            "Highlight the biggest positive shift and the biggest concern. "
            "Call out any anomalies (e.g. sharp drop in CF projects, spike in delays). "
            "End with one-line trajectory assessment."
        ),
        "trend_analysis": (
            "VP-level trend analysis. Lead with 3 key trends (positive) and 2 anomalies or risks. "
            "Use specific numbers. Flag any metric moving in the wrong direction. "
            "End with recommended focus areas for next week."
        ),
        "risk_analysis": (
            "VP-level risk brief. List risks by severity. For each: what it is, current status, owner if known, "
            "and recommended action. Flag any risk with no mitigation plan."
        ),
        "web_search": (
            "The user asked about external information. Answer using the web search results provided. "
            "Be concise and factual. Cite the source URL if available. "
            "If the results don't answer the question, say so clearly."
        ),
        "cost_savings": (
            "VP-level cost savings summary. List all confirmed savings by week in chronological order. "
            "For each: week label, initiative name, SAR amount, type (OPEX/CAPEX/cost reduction). "
            "End with total confirmed savings across all weeks. "
            "Only include savings with explicit SAR amounts — do not include 0.0M or placeholder values."
        ),
        "fact_lookup": (
            "Answer directly with the specific fact requested. One or two lines maximum. "
            "Include the source week. If the data is not in the evidence, say so explicitly."
        ),
    }

    return (
        "You are a senior executive reporting assistant briefing a VP of Technology Strategy.\n"
        "Use only the provided structured evidence. Be concise, precise, and decision-oriented.\n"
        "Rules:\n"
        "- Use correct weeks only.\n"
        "- Never guess missing metrics; say 'not available in the report' explicitly.\n"
        "- Preserve numeric values exactly as they appear in the evidence.\n"
        "- CRITICAL: Preserve negative statements exactly. If the evidence says 'no progress recorded' or 'not yet initiated', report that verbatim — never rephrase as positive.\n"
        "- CRITICAL: Never add details, context, or explanations that are not explicitly stated in the evidence. If it is not in the evidence, do not say it.\n"
        "- If a specific week is asked about, only use evidence from that week. Do not pull data from other weeks.\n"
        "- Format output for WhatsApp: use *bold* for section headings, week labels, and key numbers.\n"
        "- Use - for bullet points. Keep lines short and scannable. No filler phrases like 'here is your summary' or 'would you like more details'.\n"
        "- Currency is always SAR. Never use ₽ or $ symbols.\n"
        f"Intent: {intent}\n"
        f"Scope weeks: {', '.join(target_weeks) if target_weeks else 'N/A'}\n"
        f"Output guidance: {instruction_map.get(intent, instruction_map['fact_lookup'])}\n\n"
        f"User Query:\n{query}\n\n"
        + (f"Cross-week RFP consistency analysis:\n{consistency_block}\n\n" if consistency_block else "")
        + f"Metrics by week:\n{_format_metrics(metrics)}\n\n"
        f"Top delayed RFP rows (sorted by budget):\n{delayed_block}\n\n"
        "Structured evidence:\n"
        + "\n".join([f"- {line}" for line in evidence[:24]])
    )
