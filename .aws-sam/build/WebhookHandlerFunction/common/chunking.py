import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


WEEK_PATTERN = re.compile(r"\bWK[-\s]?(\d{1,2})\b", re.IGNORECASE)
DATE_PATTERN = re.compile(
    r"\b(\d{1,2}[-/\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/\s]\d{2,4})\b",
    re.IGNORECASE,
)
TIMELINE_WEEK_DATE_PATTERN = re.compile(
    r"\bW(?:K)?[-\s]?(\d{1,2})\s+(\d{1,2})[-/\s]"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"(?:[-/\s](\d{2,4}))?\b",
    re.IGNORECASE,
)

MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

HEADER_PATTERNS: List[Tuple[re.Pattern, str, int]] = [
    (re.compile(r"^gcto\s+updates$", re.IGNORECASE), "GCTO Updates", 1),
    (re.compile(r"^weekly\s+digest$", re.IGNORECASE), "Weekly Digest", 1),
    (re.compile(r"^overall\s+updates$", re.IGNORECASE), "Overall Updates", 1),
    (re.compile(r"^key\s+projects\s*&\s*hot\s*topics$", re.IGNORECASE), "Key Projects & Hot Topics", 1),
    (re.compile(r"^it\s+efficiency\s+initiatives\s*[-–]\s*cost\s*optimization$", re.IGNORECASE), "IT Efficiency Initiatives - Cost Optimization", 1),
    (re.compile(r"^executive\s+summ(?:a|e)ry\s*[–-]\s*rfx\s*&\s*cost\s*optimization\*?$", re.IGNORECASE), "Executive Summary – RFx & Cost Optimization*", 1),
    (re.compile(r"^strategy(?:\s*&\s*architecture)?$", re.IGNORECASE), "Strategy & Architecture", 1),
    (re.compile(r"^cloud(?:\s*&\s*infrastructure)?$", re.IGNORECASE), "Cloud & Infrastructure", 1),
    (re.compile(r"^(?:governance|compliance)(?:\s*&\s*(?:governance|compliance))?$", re.IGNORECASE), "Governance & Compliance", 1),
    (re.compile(r"^cost\s*optimization$", re.IGNORECASE), "Cost Optimization", 1),
    (re.compile(r"^programs?(?:\s*&\s*(?:operations|automation))?$", re.IGNORECASE), "Programs & Operations", 1),
    (re.compile(r"^rfx\s+status$", re.IGNORECASE), "RFx Status", 1),
    (re.compile(r"^delayed\s+rfps?$", re.IGNORECASE), "Delayed RFPs", 1),
]

MAJOR_SECTIONS = [
    "GCTO Updates",
    "Weekly Digest",
    "Key Projects & Hot Topics",
    "IT Efficiency Initiatives - Cost Optimization",
    "Executive Summary – RFx & Cost Optimization*",
    "RFx Status",
    "Delayed RFPs",
]

MAJOR_SECTION_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("GCTO Updates", ["gcto updates", "gcto"]),
    ("Weekly Digest", ["weekly digest"]),
    ("Key Projects & Hot Topics", ["key projects", "hot topics"]),
    ("IT Efficiency Initiatives - Cost Optimization", ["it efficiency initiatives", "cost optimization", "efficiency initiatives"]),
    ("Executive Summary – RFx & Cost Optimization*", ["executive summary", "executive summery", "rfx & cost optimization", "rfx and cost optimization"]),
    ("RFx Status", ["rfx status", "rfx", "rfp status"]),
    ("Delayed RFPs", ["delayed rfps", "delayed rfp"]),
]


def _detect_header_line(line: str) -> Tuple[str, int]:
    value = (line or "").strip().strip("-•: ")
    for pattern, label, level in HEADER_PATTERNS:
        if pattern.match(value):
            return label, level

    return "", 0


def _parse_date_to_iso(date_text: str) -> str:
    value = (date_text or "").strip()
    if not value:
        return ""

    formats = [
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d %b %Y",
        "%d %b %y",
        "%d/%b/%Y",
        "%d/%b/%y",
        "%d-%B-%Y",
        "%d %B %Y",
        "%d/%B/%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return ""


def _iso_to_display(iso_value: str) -> str:
    if not iso_value:
        return ""
    try:
        dt = datetime.strptime(iso_value, "%Y-%m-%d")
        return dt.strftime("%d-%b-%Y")
    except ValueError:
        return ""


def _coerce_year(year_text: str, inferred_year: int) -> int:
    if not year_text:
        return inferred_year
    year = int(year_text)
    if year < 100:
        return 2000 + year
    return year


def _infer_reference_year(text: str) -> int:
    current_year = datetime.now(timezone.utc).year
    years = [
        int(match.group(0))
        for match in re.finditer(r"\b20\d{2}\b", text or "")
        if 2000 <= int(match.group(0)) <= 2100
    ]
    plausible = [year for year in years if current_year - 2 <= year <= current_year + 2]
    if plausible:
        counts: Dict[int, int] = {}
        for year in plausible:
            counts[year] = counts.get(year, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], abs(item[0] - current_year), item[0]))[0][0]

    if years:
        counts: Dict[int, int] = {}
        for year in years:
            counts[year] = counts.get(year, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], abs(item[0] - current_year), item[0]))[0][0]

    return current_year


def normalize_week_metadata(raw_text: str, source_page: int) -> Dict[str, Dict[str, str]]:
    text = raw_text or ""
    inferred_year = _infer_reference_year(text)
    week_date_map: Dict[str, Dict[str, str]] = {}

    for match in TIMELINE_WEEK_DATE_PATTERN.finditer(text):
        week_num = int(match.group(1))
        day = int(match.group(2))
        month_token = (match.group(3) or "").strip().lower()[:3]
        if month_token not in MONTH_MAP:
            continue
        year = _coerce_year(match.group(4) or "", inferred_year)

        try:
            dt = datetime(year=year, month=MONTH_MAP[month_token], day=day)
        except ValueError:
            continue

        week = f"WK-{week_num:02d}"
        iso_value = dt.strftime("%Y-%m-%d")
        display = dt.strftime("%d-%b-%Y")

        existing = week_date_map.get(week)
        if not existing or iso_value > existing.get("report_date_iso", ""):
            week_date_map[week] = {
                "week": week,
                "week_num": str(week_num),
                "report_date": display,
                "report_date_iso": iso_value,
                "source": f"timeline_p{source_page}",
            }

    return week_date_map


def _extract_week_metadata(text: str) -> Dict[str, str]:
    week_match = WEEK_PATTERN.search(text or "")
    date_match = DATE_PATTERN.search(text or "")

    week = ""
    week_num = ""
    if week_match:
        week_num = str(int(week_match.group(1)))
        week = f"WK-{int(week_match.group(1)):02d}"

    report_date = date_match.group(1) if date_match else ""
    report_date_iso = _parse_date_to_iso(report_date)
    report_date_norm = _iso_to_display(report_date_iso) if report_date_iso else report_date
    return {
        "week": week,
        "week_num": week_num,
        "report_date": report_date_norm,
        "report_date_iso": report_date_iso,
    }


def _detect_section_family(title: str, text: str) -> str:
    combined = f"{title} {text}".lower()
    if any(word in combined for word in ["weekly digest", "hot topic", "hot topics"]):
        return "Weekly Digest / Hot Topics"
    if any(word in combined for word in ["key project", "projects update", "major projects"]):
        return "Key Projects"
    if any(word in combined for word in ["strategy", "architecture", "roadmap"]):
        return "Architecture / Strategy"
    if any(word in combined for word in ["staffing", "recruitment", "vacancies"]):
        return "Staffing / Recruitment"
    if any(word in combined for word in ["risk", "blocker", "constraint", "pending", "delayed"]):
        return "Risks & Delays"
    if any(word in combined for word in ["compliance", "governance", "star", "architecture"]):
        return "Governance & Compliance"
    if any(word in combined for word in ["cloud", "infrastructure", "datacenter", "migration"]):
        return "Cloud & Infrastructure"
    if any(word in combined for word in ["genai", "ai", "assistant", "llm"]):
        return "AI Initiatives"
    if any(word in combined for word in ["rfp", "rfx", "pipeline", "project", "capex", "opex", "sar"]):
        return "Portfolio & Financials"
    return "General Updates"


def _normalize_major_section(text: str) -> str:
    value = (text or "").strip().lower()
    if not value:
        return ""
    for canonical, terms in MAJOR_SECTION_KEYWORDS:
        if any(term in value for term in terms):
            return canonical
    return ""


def _detect_major_section(title: str, body: str, current_major: str = "") -> str:
    from_title = _normalize_major_section(title)
    if from_title:
        return from_title

    body_head = "\n".join((body or "").splitlines()[:18])
    from_body = _normalize_major_section(body_head)
    if from_body:
        return from_body

    return current_major or "General"


def _split_sections(page_text: str) -> List[Dict[str, str]]:
    lines = [line.rstrip() for line in (page_text or "").splitlines()]
    sections: List[Dict[str, str]] = []

    current_header = "General"
    current_major_section = "General"
    current_level = 3
    header_position = 0
    buffer: List[str] = []

    def flush_buffer() -> None:
        nonlocal buffer
        body = "\n".join([line for line in buffer if line.strip()]).strip()
        if not body:
            return
        sections.append(
            {
                "section_title": current_header,
                "section_header": current_header,
                "parent_section_header": current_header,
                "major_section": _detect_major_section(current_header, body, current_major_section),
                "section_level": str(current_level),
                "header_position": str(header_position),
                "body": body,
            }
        )
        buffer = []

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            if buffer:
                buffer.append("")
            continue

        detected_header, detected_level = _detect_header_line(line)
        if detected_header:
            flush_buffer()
            current_header = detected_header
            current_level = detected_level
            header_position = idx + 1
            if detected_header in MAJOR_SECTIONS:
                current_major_section = detected_header
            continue

        buffer.append(line)

    flush_buffer()

    if not sections:
        sections.append(
            {
                "section_title": "General",
                "section_header": "General",
                "parent_section_header": "General",
                "major_section": _detect_major_section("General", (page_text or ""), current_major_section),
                "section_level": "3",
                "header_position": "1",
                "body": (page_text or "").strip(),
            }
        )
    return sections


def tokenize(text: str) -> List[str]:
    return text.split()


def split_into_chunks(
    pages: List[Tuple[int, str]], chunk_size_tokens: int, overlap_tokens: int
) -> List[Dict]:
    chunks: List[Dict] = []
    chunk_index = 0

    normalized_week_index: Dict[str, Dict[str, str]] = {}
    for page_number, page_text in pages:
        page_week_map = normalize_week_metadata(page_text, page_number)
        for week, value in page_week_map.items():
            existing = normalized_week_index.get(week)
            if not existing or value.get("report_date_iso", "") > existing.get("report_date_iso", ""):
                normalized_week_index[week] = value

    for page_number, page_text in pages:
        page_meta = _extract_week_metadata(page_text)
        sections = _split_sections(page_text)

        for section in sections:
            section_title = section.get("section_title", "General")
            section_header = section.get("section_header", section_title)
            parent_section_header = section.get("parent_section_header", section_header)
            major_section = section.get("major_section") or _detect_major_section(section_title, section.get("body", ""))
            section_level = section.get("section_level", "3")
            header_position = section.get("header_position", "1")
            section_body = section.get("body", "")

            section_meta = _extract_week_metadata(f"{section_title}\n{section_body}")
            week = section_meta.get("week") or page_meta.get("week", "")
            week_num = section_meta.get("week_num") or page_meta.get("week_num", "")
            report_date_iso = section_meta.get("report_date_iso") or page_meta.get("report_date_iso", "")
            report_date = section_meta.get("report_date") or page_meta.get("report_date", "")

            canonical = normalized_week_index.get(week) if week else None
            if canonical:
                report_date_iso = canonical.get("report_date_iso", report_date_iso)
                report_date = canonical.get("report_date", report_date)

            if not report_date_iso and report_date:
                report_date_iso = _parse_date_to_iso(report_date)
            if report_date_iso and (not report_date or len(report_date) < 8):
                report_date = _iso_to_display(report_date_iso)

            tokens = tokenize(section_body)
            if not tokens:
                continue

            section_family = _detect_section_family(section_title, section_body)
            section_type = "bullets" if "\n-" in section_body or "\n•" in section_body else "body"

            safe_chunk_size = max(1, int(chunk_size_tokens or 0))
            safe_overlap = max(0, min(int(overlap_tokens or 0), safe_chunk_size - 1))
            step = max(1, safe_chunk_size - safe_overlap)

            for start in range(0, len(tokens), step):
                chunk_tokens = tokens[start : start + safe_chunk_size]
                if not chunk_tokens:
                    break
                chunk_text = " ".join(chunk_tokens).strip()
                if not chunk_text:
                    continue
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "page_number": page_number,
                        "source_page": page_number,
                        "chunk_text": chunk_text,
                        "token_count": len(chunk_tokens),
                        "week": week,
                        "week_num": week_num,
                        "report_date": report_date,
                        "report_date_iso": report_date_iso,
                        "section_family": section_family,
                        "major_section": major_section,
                        "section_title": section_title,
                        "section_header": section_header,
                        "section_level": section_level,
                        "header_position": header_position,
                        "parent_section_header": parent_section_header,
                        "section_block_text": section_body,
                        "section_type": section_type,
                    }
                )
                chunk_index += 1
                if start + safe_chunk_size >= len(tokens):
                    break

    return chunks
