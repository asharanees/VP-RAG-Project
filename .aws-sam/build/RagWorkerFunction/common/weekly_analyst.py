import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


INTENT_KEYWORDS = {
    "progress_comparison": ["comparison", "compare", "progress across", "week over week", "across weeks"],
    "delayed_initiatives": ["delayed", "pending initiatives", "pending", "overdue", "stuck"],
    "trend_analysis": ["trend", "anomaly", "anomalies", "pattern", "insight"],
    "weekly_summary": ["summary", "overall updates", "latest updates", "last week", "last 4 weeks", "recap", "updates"],
    "hot_topics": ["hot topics", "major topics", "key themes", "top themes"],
    "risk_analysis": ["risk", "risks", "blockers", "constraints", "issues"],
    "fact_lookup": ["how many", "what is", "what are", "count", "number of"],
}

RECENCY_TERMS = [
    "latest",
    "recent",
    "recently",
    "current",
    "newest",
    "latest updates",
    "overall updates",
]

SECTION_PRIORITY_WEIGHTS = {
    "weekly digest": 5.0,
    "hot topics": 5.0,
    "key projects": 4.0,
    "architecture": 4.0,
    "strategy": 4.0,
    "compliance": 3.0,
    "governance": 3.0,
    "operational": 2.0,
    "operations": 2.0,
    "staffing": 1.0,
    "recruitment": 1.0,
}

HEADER_PRIORITY_WEIGHTS = {
    "weekly digest": 5.0,
    "overall updates": 5.0,
    "key projects & hot topics": 4.0,
    "strategy & architecture": 4.0,
    "cloud & infrastructure": 4.0,
    "governance & compliance": 3.0,
    "cost optimization": 3.0,
    "programs & operations": 2.0,
    "rfx status": 2.0,
    "delayed rfps": 2.0,
}

INTENT_SECTION_HINTS = {
    "fact_lookup": ["kpi", "rfp", "status", "metrics"],
    "weekly_summary": ["summary", "governance", "strategy", "progress"],
    "progress_comparison": ["comparison", "progress", "metrics", "rfp"],
    "delayed_initiatives": ["delayed", "pending", "blocker", "risk", "status"],
    "trend_anomaly_analysis": ["trend", "anomaly", "kpi", "metrics"],
    "hot_topics": ["strategy", "architecture", "cloud", "genai", "governance"],
    "risk_analysis": ["risk", "constraint", "blocker", "governance", "resource"],
}

THEME_CLUSTERS = {
    "Cloud Transformation": ["cloud", "public cloud", "migration", "tagging", "roadmap", "infrastructure"],
    "Architecture Governance": ["star", "architecture mapping", "governance", "architecture"],
    "Data & AI Platforms": ["ai", "ml", "databricks", "analytics", "automation"],
    "Cost Optimization": ["cost", "savings", "optimization", "opex", "capex", "tco"],
    "Governance & Compliance": ["compliance", "standards", "control", "maturity", "waiver"],
    "Programs & Automation": ["site forecasting", "dashboard", "tools", "program", "operations"],
}

QUERY_MAJOR_SECTION_HINTS: List[Tuple[str, List[str]]] = [
    ("GCTO Updates", ["gcto updates", "gcto update", "gcto"]),
    ("Weekly Digest", ["weekly digest"]),
    ("Key Projects & Hot Topics", ["key projects", "hot topics"]),
    ("IT Efficiency Initiatives - Cost Optimization", ["it efficiency initiatives", "efficiency initiatives", "cost optimization"]),
    ("Executive Summary – RFx & Cost Optimization*", ["executive summary", "executive summery", "rfx & cost optimization", "rfx and cost optimization"]),
    ("RFx Status", ["rfx status", "rfp status"]),
    ("Delayed RFPs", ["delayed rfp", "delayed rfps"]),
]

MAJOR_SECTION_MATCH_TERMS: Dict[str, List[str]] = {
    "GCTO Updates": ["gcto update", "gcto updates", "gcto", "project owner", "engagement model"],
    "Weekly Digest": ["weekly digest"],
    "Key Projects & Hot Topics": ["key projects", "hot topics"],
    "IT Efficiency Initiatives - Cost Optimization": ["it efficiency initiatives", "cost optimization", "opex savings", "capex savings"],
    "Executive Summary – RFx & Cost Optimization*": ["executive summary", "executive summery", "rfx & cost optimization"],
    "RFx Status": ["rfx status", "rfp status", "approved projects", "in progress rfps"],
    "Delayed RFPs": ["delayed rfp", "delayed rfps", "pending with", "budget (sar)", "status delayed"],
}


def _detect_query_major_sections(query: str) -> List[str]:
    q = (query or "").strip().lower()
    if not q:
        return []

    sections: List[str] = []
    for section, terms in QUERY_MAJOR_SECTION_HINTS:
        if any(term in q for term in terms):
            if section not in sections:
                sections.append(section)
    return sections


def _chunk_major_section(chunk: Dict[str, Any]) -> str:
    return (chunk.get("major_section") or "").strip()


def _chunk_in_target_major_sections(chunk: Dict[str, Any], target_sections: List[str]) -> bool:
    if not target_sections:
        return True

    chunk_major = _chunk_major_section(chunk).strip()
    target_set = {section.lower() for section in target_sections}

    if chunk_major and chunk_major.lower() != "general":
        return chunk_major.lower() in target_set

    metadata_haystack = " ".join(
        [
            (chunk.get("section_title") or "").lower(),
            (chunk.get("section_header") or "").lower(),
            (chunk.get("parent_section_header") or "").lower(),
        ]
    )

    for section in target_sections:
        section_lc = section.lower()
        if section_lc in metadata_haystack:
            return True
        if any(term in metadata_haystack for term in MAJOR_SECTION_MATCH_TERMS.get(section, [])):
            return True

    body_haystack = " ".join(
        [
            (chunk.get("section_block_text") or "").lower()[:1200],
            (chunk.get("chunk_text") or "").lower()[:800],
        ]
    )

    for section in target_sections:
        if any(term in body_haystack for term in MAJOR_SECTION_MATCH_TERMS.get(section, [])):
            return True
    return False


def classify_query_intent(query: str) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    target_major_sections = _detect_query_major_sections(q)

    if any(term in q for term in ["delayed rfp", "delayed rfps"]):
        explicit_weeks = sorted(set(re.findall(r"wk[-\s]?(\d{1,2})", q)))
        explicit_weeks = [f"WK-{int(w):02d}" for w in explicit_weeks]
        latest_n_weeks: Optional[int] = None
        latest_match = re.search(r"last\s+(\d{1,2})\s+weeks?", q)
        if latest_match:
            latest_n_weeks = int(latest_match.group(1))
        elif "last week" in q:
            latest_n_weeks = 1
        elif any(term in q for term in RECENCY_TERMS):
            latest_n_weeks = 2
        return {
            "intent": "delayed_initiatives",
            "explicit_weeks": explicit_weeks,
            "latest_n_weeks": latest_n_weeks,
            "requested_time_scope": "explicit_weeks" if explicit_weeks else "latest_n_weeks" if latest_n_weeks else "unspecified",
            "target_major_sections": target_major_sections or ["Delayed RFPs"],
        }

    if "gcto" in q and "update" in q:
        explicit_weeks = sorted(set(re.findall(r"wk[-\s]?(\d{1,2})", q)))
        explicit_weeks = [f"WK-{int(w):02d}" for w in explicit_weeks]
        latest_n_weeks: Optional[int] = None
        latest_match = re.search(r"last\s+(\d{1,2})\s+weeks?", q)
        if latest_match:
            latest_n_weeks = int(latest_match.group(1))
        elif "last week" in q:
            latest_n_weeks = 1
        elif any(term in q for term in RECENCY_TERMS):
            latest_n_weeks = 2
        return {
            "intent": "weekly_summary",
            "explicit_weeks": explicit_weeks,
            "latest_n_weeks": latest_n_weeks,
            "requested_time_scope": "explicit_weeks" if explicit_weeks else "latest_n_weeks" if latest_n_weeks else "unspecified",
            "target_major_sections": target_major_sections or ["GCTO Updates"],
        }

    if any(term in q for term in ["rfp", "rfx"]) and "status" in q:
        explicit_weeks = sorted(set(re.findall(r"wk[-\s]?(\d{1,2})", q)))
        explicit_weeks = [f"WK-{int(w):02d}" for w in explicit_weeks]
        latest_n_weeks: Optional[int] = None
        latest_match = re.search(r"last\s+(\d{1,2})\s+weeks?", q)
        if latest_match:
            latest_n_weeks = int(latest_match.group(1))
        elif "last week" in q:
            latest_n_weeks = 1
        elif any(term in q for term in RECENCY_TERMS):
            latest_n_weeks = 2
        resolved_sections = target_major_sections[:]
        if not resolved_sections:
            resolved_sections = ["RFx Status"]
        elif "RFx Status" not in resolved_sections:
            resolved_sections.append("RFx Status")

        if "delayed" in q and any(term in q for term in ["rfp", "rfps", "rfx"]):
            if "Delayed RFPs" not in resolved_sections:
                resolved_sections.append("Delayed RFPs")

        return {
            "intent": "fact_lookup",
            "explicit_weeks": explicit_weeks,
            "latest_n_weeks": latest_n_weeks,
            "requested_time_scope": "explicit_weeks" if explicit_weeks else "latest_n_weeks" if latest_n_weeks else "unspecified",
            "target_major_sections": resolved_sections,
        }

    if "hot topics" in q:
        explicit_weeks = sorted(set(re.findall(r"wk[-\s]?(\d{1,2})", q)))
        explicit_weeks = [f"WK-{int(w):02d}" for w in explicit_weeks]
        latest_n_weeks: Optional[int] = None
        latest_match = re.search(r"last\s+(\d{1,2})\s+weeks?", q)
        if latest_match:
            latest_n_weeks = int(latest_match.group(1))
        elif "last week" in q:
            latest_n_weeks = 1
        return {
            "intent": "hot_topics",
            "explicit_weeks": explicit_weeks,
            "latest_n_weeks": latest_n_weeks,
            "requested_time_scope": "explicit_weeks" if explicit_weeks else "latest_n_weeks" if latest_n_weeks else "unspecified",
            "target_major_sections": target_major_sections,
        }

    explicit_weeks = sorted(set(re.findall(r"wk[-\s]?(\d{1,2})", q)))
    explicit_weeks = [f"WK-{int(w):02d}" for w in explicit_weeks]

    latest_n_weeks: Optional[int] = None
    latest_match = re.search(r"last\s+(\d{1,2})\s+weeks?", q)
    month_match = re.search(r"last\s+(\d{1,2})\s+months?", q)
    if latest_match:
        latest_n_weeks = int(latest_match.group(1))
    elif month_match:
        latest_n_weeks = int(month_match.group(1)) * 4
    elif "last week" in q:
        latest_n_weeks = 1
    elif "latest updates" in q:
        latest_n_weeks = 2
    elif any(term in q for term in RECENCY_TERMS):
        latest_n_weeks = 2

    requested_time_scope = "explicit_weeks" if explicit_weeks else "latest_n_weeks" if latest_n_weeks else "unspecified"

    best_intent = "weekly_summary"
    best_score = 0
    for intent, terms in INTENT_KEYWORDS.items():
        score = sum(1 for term in terms if term in q)
        if score > best_score:
            best_score = score
            best_intent = intent

    return {
        "intent": best_intent,
        "explicit_weeks": explicit_weeks,
        "latest_n_weeks": latest_n_weeks,
        "requested_time_scope": requested_time_scope,
        "target_major_sections": target_major_sections,
    }


def _parse_report_date(date_text: str) -> datetime:
    value = (date_text or "").strip()
    if not value:
        return datetime.min
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
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.min


def _display_from_iso(date_iso: str) -> str:
    value = (date_iso or "").strip()
    if not value:
        return ""
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.strftime("%d-%b-%Y")
    except ValueError:
        return ""


def _parse_week_num(week: str) -> int:
    match = re.search(r"(\d{1,2})", week or "")
    return int(match.group(1)) if match else -1


def _sort_weeks(weeks: List[str], ascending: bool = True) -> List[str]:
    unique = {week for week in weeks if week}
    return sorted(unique, key=_parse_week_num, reverse=not ascending)


def detect_target_weeks(query: str, intent_result: Dict[str, Any], available_week_rows: List[Dict[str, str]]) -> Dict[str, Any]:
    query_lc = (query or "").lower()
    explicit_weeks = intent_result.get("explicit_weeks") or []
    latest_n = intent_result.get("latest_n_weeks")
    intent = intent_result.get("intent", "weekly_summary")

    explicit_latest_match = re.search(r"latest\s+(\d{1,2})\s+weeks?", query_lc)
    explicit_month_match = re.search(r"last\s+(\d{1,2})\s+months?", query_lc)
    if explicit_latest_match:
        latest_n = int(explicit_latest_match.group(1))
    elif explicit_month_match:
        latest_n = int(explicit_month_match.group(1)) * 4

    if "latest updates" in query_lc and not latest_n:
        latest_n = 2

    if not latest_n and not explicit_weeks and any(term in query_lc for term in RECENCY_TERMS):
        if intent == "trend_analysis":
            latest_n = 3
        elif intent == "progress_comparison":
            latest_n = 3
        elif intent == "delayed_initiatives":
            latest_n = 8
        else:
            latest_n = 2

    available = [
        {
            "week": row.get("week", ""),
            "report_date": row.get("report_date", ""),
            "report_date_iso": row.get("report_date_iso", ""),
        }
        for row in (available_week_rows or [])
        if row.get("week")
    ]

    if not available:
        return {"target_weeks": explicit_weeks[:], "resolved_from": "fallback_none", "week_dates": {}}

    by_week: Dict[str, Dict[str, str]] = {}
    for row in available:
        week = row["week"]
        date = row.get("report_date", "")
        date_iso = row.get("report_date_iso", "")

        if not date_iso and date:
            parsed = _parse_report_date(date)
            if parsed != datetime.min:
                date_iso = parsed.strftime("%Y-%m-%d")

        existing = by_week.get(week)
        if not existing:
            by_week[week] = {
                "report_date": date,
                "report_date_iso": date_iso,
            }
            continue

        if date_iso and (not existing.get("report_date_iso") or date_iso > existing.get("report_date_iso", "")):
            by_week[week] = {
                "report_date": _display_from_iso(date_iso) or date,
                "report_date_iso": date_iso,
            }
        elif date and not existing.get("report_date"):
            existing["report_date"] = date

    ordered_weeks = sorted(
        by_week.keys(),
        key=lambda w: (by_week.get(w, {}).get("report_date_iso", ""), _parse_week_num(w)),
        reverse=True,
    )

    if explicit_weeks:
        selected = [week for week in explicit_weeks if week in by_week]
        if not selected:
            selected = explicit_weeks[:]
        week_dates = {wk: val.get("report_date", "") for wk, val in by_week.items()}
        week_dates_iso = {wk: val.get("report_date_iso", "") for wk, val in by_week.items()}
        return {
            "target_weeks": _sort_weeks(selected, ascending=True),
            "resolved_from": "explicit_weeks",
            "week_dates": week_dates,
            "week_dates_iso": week_dates_iso,
        }

    if latest_n:
        latest_n = max(1, min(int(latest_n), 12))
        return {
            "target_weeks": _sort_weeks(ordered_weeks[:latest_n], ascending=True),
            "resolved_from": "latest_n_weeks",
            "week_dates": {wk: val.get("report_date", "") for wk, val in by_week.items()},
            "week_dates_iso": {wk: val.get("report_date_iso", "") for wk, val in by_week.items()},
        }

    if intent == "trend_analysis":
        fallback_n = 3
    elif intent == "progress_comparison":
        fallback_n = 3
    elif intent == "delayed_initiatives":
        fallback_n = 8
    else:
        fallback_n = 2
    return {
        "target_weeks": _sort_weeks(ordered_weeks[:fallback_n], ascending=True),
        "resolved_from": "recency_fallback",
        "week_dates": {wk: val.get("report_date", "") for wk, val in by_week.items()},
        "week_dates_iso": {wk: val.get("report_date_iso", "") for wk, val in by_week.items()},
    }


def _section_weight(chunk: Dict[str, Any]) -> float:
    combined = (
        f"{chunk.get('major_section', '')} "
        f"{chunk.get('section_title', '')} "
        f"{chunk.get('section_family', '')} "
        f"{chunk.get('section_header', '')} "
        f"{chunk.get('parent_section_header', '')}"
    ).lower()
    best = 0.0
    for keyword, weight in SECTION_PRIORITY_WEIGHTS.items():
        if keyword in combined:
            best = max(best, weight)

    for keyword, weight in HEADER_PRIORITY_WEIGHTS.items():
        if keyword in combined:
            best = max(best, weight)

    section_level = str(chunk.get("section_level", "") or "")
    if section_level == "1":
        best += 0.6
    elif section_level == "2":
        best += 0.3

    return best


def _intent_relevance_bonus(chunk: Dict[str, Any], intent: str) -> float:
    header_text = " ".join(
        [
            chunk.get("section_title", ""),
            chunk.get("section_family", ""),
            chunk.get("section_header", ""),
            chunk.get("parent_section_header", ""),
        ]
    ).lower()
    body_text = (chunk.get("section_block_text") or chunk.get("chunk_text") or "").lower()
    major_section = (chunk.get("major_section") or "").lower()
    text = f"{major_section} {header_text} {body_text[:900]}"

    bonus = 0.0
    if intent == "delayed_initiatives":
        if any(term in text for term in ["delayed", "pending", "overdue", "stuck", "delay", "rfx status", "delayed rfps"]):
            bonus += 2.6
        if "delayed rfp" in major_section:
            bonus += 2.5
        if any(term in text for term in ["group erp", "cow network", "huawei spare", "internal wireless", "nokia"]):
            bonus += 1.2
        if "weekly digest" in header_text and not any(term in text for term in ["delayed", "pending", "rfx", "rfp"]):
            bonus -= 1.0

    if intent == "trend_analysis":
        if any(term in text for term in ["rfx status", "rfp", "rfx", "trend", "anomaly", "compliance", "star", "cases"]):
            bonus += 2.2
        if any(term in text for term in ["64 rfp", "75 rfp", "89 rfp"]):
            bonus += 1.0
        if "weekly digest" in header_text and not any(term in text for term in ["rfx", "rfp", "compliance", "star"]):
            bonus -= 0.8

    if intent == "progress_comparison":
        if any(term in text for term in ["status", "progress", "roadmap", "rfx", "rfp", "savings", "compliance"]):
            bonus += 1.4

    if intent == "weekly_summary" and "gcto" in major_section:
        bonus += 2.3

    return bonus


def _query_focus_bonus(chunk: Dict[str, Any], query: str, intent: str) -> float:
    query_lc = (query or "").lower()
    if not query_lc:
        return 0.0

    header_text = " ".join(
        [
            chunk.get("section_title", ""),
            chunk.get("section_family", ""),
            chunk.get("section_header", ""),
            chunk.get("parent_section_header", ""),
        ]
    ).lower()
    body_text = (chunk.get("section_block_text") or chunk.get("chunk_text") or "").lower()
    major_section = (chunk.get("major_section") or "").lower()
    text = f"{major_section} {header_text} {body_text[:1000]}"

    bonus = 0.0

    if any(term in query_lc for term in ["rfp", "rfx", "status"]):
        if any(term in text for term in ["rfx status", "rfp", "rfx", "approved projects", "projects in progress"]):
            bonus += 2.8
        if "delayed rfp" in text:
            bonus += 1.2
        if "delayed" in query_lc and any(term in text for term in ["delayed rfp", "pending", "group erp", "cow network", "huawei", "nokia", "internal wireless"]):
            bonus += 2.0

    if "gcto" in query_lc and "update" in query_lc:
        if "gcto" in text:
            bonus += 3.0
        elif "weekly digest" in text:
            bonus += 0.4

    if any(term in query_lc for term in ["ntn", "satellite", "nb-iot", "oq"]):
        if any(term in text for term in ["ntn", "satellite", "nb-iot", "oq", "backhaul"]):
            bonus += 2.6

    if intent == "fact_lookup" and any(term in query_lc for term in ["what is", "what are", "status", "progress"]):
        if any(term in text for term in ["status", "kpi", "roadmap", "in progress", "approved"]):
            bonus += 0.8

    return bonus


def _week_recency_bonus(week: str, ordered_target_weeks: List[str]) -> float:
    if not week or not ordered_target_weeks:
        return 0.0
    week_to_rank = {wk: idx for idx, wk in enumerate(ordered_target_weeks)}
    if week not in week_to_rank:
        return -1.5
    rank = week_to_rank[week]
    return max(0.0, 1.2 - (0.35 * rank))


def _expand_to_section_blocks(selected: List[Dict[str, Any]], pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not selected:
        return []

    blocks: List[Dict[str, Any]] = []
    seen_block_keys = set()

    for chunk in selected:
        week = chunk.get("week", "")
        parent_header = chunk.get("parent_section_header") or chunk.get("section_header") or chunk.get("section_title") or "General"
        block_key = f"{week}::{parent_header}".lower()
        if block_key in seen_block_keys:
            continue
        seen_block_keys.add(block_key)

        siblings = [
            candidate
            for candidate in pool
            if candidate.get("week", "") == week
            and (candidate.get("parent_section_header") or candidate.get("section_header") or candidate.get("section_title") or "General") == parent_header
        ]
        if not siblings:
            siblings = [chunk]

        siblings.sort(key=lambda c: (int(str(c.get("header_position", "0") or "0")), int(c.get("chunk_index", 0))))

        bullet_parts: List[str] = []
        for sibling in siblings:
            block_text = (sibling.get("section_block_text") or sibling.get("chunk_text") or "").strip()
            if not block_text:
                continue
            pieces = [p.strip(" -") for p in re.split(r"\n|(?<=[.!?])\s+", block_text) if p.strip()]
            for piece in pieces:
                if len(piece) < 12:
                    continue
                if piece.lower() in {p.lower() for p in bullet_parts}:
                    continue
                bullet_parts.append(piece)
                if len(bullet_parts) >= 5:
                    break
            if len(bullet_parts) >= 5:
                break

        aggregated_text = ". ".join(bullet_parts[:5]).strip()
        if not aggregated_text:
            aggregated_text = (chunk.get("chunk_text") or "").strip()

        block_chunk = dict(chunk)
        block_chunk["chunk_text"] = aggregated_text
        block_chunk["section_title"] = parent_header
        block_chunk["section_header"] = parent_header
        block_chunk["section_type"] = "section_block"
        blocks.append(block_chunk)

    return blocks


def _map_chunk_to_exec_section(chunk: Dict[str, Any]) -> str:
    text = (
        f"{chunk.get('section_header', '')} "
        f"{chunk.get('section_family', '')} "
        f"{chunk.get('section_title', '')} "
        f"{chunk.get('chunk_text', '')}"
    ).lower()
    if any(k in text for k in ["strategy", "architecture", "roadmap", "hot topics", "weekly digest", "ntn", "nokia"]):
        return "Strategy & Architecture"
    if any(k in text for k in ["cloud", "infrastructure", "migration", "resilien", "disaster recovery", "tagging", "cloudification"]):
        return "Cloud & Infrastructure"
    if any(k in text for k in ["governance", "compliance", "star", "standard", "non-compliant", "waiver"]):
        return "Governance & Compliance"
    if any(k in text for k in ["cost", "saving", "opex", "capex", "tco", "adobe experience manager", "hcl", "databricks"]):
        return "Cost Optimization"
    return "Programs & Operations"


def _ensure_weekly_summary_coverage(scored: List[Tuple[float, Dict[str, Any]]], selected_count: int) -> List[Dict[str, Any]]:
    if not scored:
        return []

    sections = [
        "Strategy & Architecture",
        "Cloud & Infrastructure",
        "Governance & Compliance",
        "Cost Optimization",
        "Programs & Operations",
    ]

    selected: List[Dict[str, Any]] = []
    selected_ids = set()

    for section in sections:
        for _, chunk in scored:
            chunk_id = chunk.get("chunk_id", "")
            if chunk_id in selected_ids:
                continue
            if _map_chunk_to_exec_section(chunk) == section:
                selected.append(chunk)
                if chunk_id:
                    selected_ids.add(chunk_id)
                break

    for _, chunk in scored:
        if len(selected) >= selected_count:
            break
        chunk_id = chunk.get("chunk_id", "")
        if chunk_id and chunk_id in selected_ids:
            continue
        selected.append(chunk)
        if chunk_id:
            selected_ids.add(chunk_id)

    return selected[:selected_count]


def _map_note_to_exec_section(note: Dict[str, Any]) -> str:
    text = f"{note.get('section_header', '')} {note.get('section_family', '')} {note.get('section_title', '')} {note.get('theme_candidate', '')}".lower()
    if any(k in text for k in ["strategy", "architecture", "roadmap", "digest", "hot topics"]):
        return "Strategy & Architecture"
    if any(k in text for k in ["cloud", "infrastructure", "migration", "resiliency"]):
        return "Cloud & Infrastructure"
    if any(k in text for k in ["governance", "compliance", "star", "standards"]):
        return "Governance & Compliance"
    if any(k in text for k in ["cost", "savings", "opex", "capex", "tco", "rfx"]):
        return "Cost Optimization"
    return "Programs & Operations"


def _map_fact_to_exec_section(note: Dict[str, Any], fact: str) -> str:
    combined = f"{fact} {note.get('section_header', '')} {note.get('section_family', '')} {note.get('section_title', '')}".lower()
    if any(k in combined for k in ["savings", "opex savings", "capex savings", "sar savings", "cost optimization", "rationalization", "timeline reduction"]):
        return "Cost Optimization"
    if any(k in combined for k in ["compliance", "non-compliance", "standards", "star", "arb", "maturity", "waiver", "architecture roadmap"]):
        return "Governance & Compliance"
    if any(k in combined for k in ["cloud roadmap", "public cloud", "migration", "dr", "disaster recovery", "resiliency", "infrastructure planning", "tagging architecture", "infra"]):
        return "Cloud & Infrastructure"
    if any(k in combined for k in ["rfx automation", "dashboard", "executive visibility", "reporting", "gtu dashboard", "program cards", "assessment", "automation model"]):
        return "Programs & Operations"
    if any(k in combined for k in ["strategy", "architecture", "roadmap", "nokia", "ntn", "accen", "lmm", "modernization"]):
        return "Strategy & Architecture"
    if any(k in combined for k in ["program", "dashboard", "site forecasting", "automation", "rfx", "rfp", "gtu"]):
        return "Programs & Operations"
    return _map_note_to_exec_section(note)


def normalize_bullet_text(text: str) -> str:
    value = " ".join((text or "").replace("", " ").replace("•", " ").split()).strip("-: ")
    if not value:
        return ""

    value = re.sub(r"\.{2,}$", ".", value)
    value = re.sub(r"\s+([.,;:!?])", r"\1", value)

    lowered = value.lower()
    header_noise = [
        "sub rfp name",
        "impacted domain",
        "pending with",
        "expense gd",
        "budget (sar)",
        "status pending",
    ]
    if any(noise in lowered for noise in header_noise):
        return ""

    if lowered.startswith("sectors over") or lowered.startswith("project timeline from"):
        return ""

    if lowered.endswith(" with the.") or lowered.endswith(" aligned with the."):
        return ""

    if lowered.endswith(" to the.") or lowered.endswith(" to the") or lowered.endswith(" to.") or lowered.endswith(" to") or lowered.endswith(" and."):
        return ""

    if lowered.endswith(" with") or lowered.endswith(" and") or lowered.endswith(" of"):
        return ""

    if len(value) < 24:
        return ""

    if value[-1] not in ".!?" and len(value) < 38:
        return ""

    return value


def aggregate_section_bullets(notes: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {
        "Strategic & Architecture Initiatives": [],
        "Cloud, Infrastructure & Technology Programs": [],
        "Cost Optimization & Efficiency": [],
        "Governance, Compliance & Enterprise Architecture": [],
        "Programs, Reporting & Execution": [],
    }

    map_to_label = {
        "Strategy & Architecture": "Strategic & Architecture Initiatives",
        "Cloud & Infrastructure": "Cloud, Infrastructure & Technology Programs",
        "Cost Optimization": "Cost Optimization & Efficiency",
        "Governance & Compliance": "Governance, Compliance & Enterprise Architecture",
        "Programs & Operations": "Programs, Reporting & Execution",
    }

    for note in notes:
        week = note.get("week", "")
        date = note.get("report_date", "")
        for fact in note.get("key_facts", [])[:3]:
            cleaned = normalize_bullet_text(fact)
            if not cleaned:
                continue
            section_key = _map_fact_to_exec_section(note, cleaned)
            label = map_to_label.get(section_key, "Programs, Reporting & Execution")
            line = (f"{week} ({date}): " if week else "") + cleaned
            line = " ".join(line.split())
            if line and line.lower() not in {existing.lower() for existing in sections[label]}:
                sections[label].append(line)

    for key in list(sections.keys()):
        uniq = []
        seen = set()
        for line in sections[key]:
            norm = re.sub(r"\W+", " ", line.lower()).strip()
            if norm in seen:
                continue
            seen.add(norm)
            uniq.append(line)
            if len(uniq) >= 3:
                break
        sections[key] = uniq

    return sections


def extract_latest_rfp_status(target_week: str, notes: List[Dict[str, Any]], selected_chunks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    week_notes = [note for note in notes if not target_week or note.get("week") == target_week]
    all_facts: List[str] = []
    for note in week_notes:
        all_facts.extend(note.get("key_facts", [])[:3])

    rfx_texts: List[str] = []
    delayed_texts: List[str] = []
    for chunk in (selected_chunks or []):
        week = chunk.get("week", "")
        if target_week and week != target_week:
            continue
        section_text = " ".join(
            [
                chunk.get("section_title", ""),
                chunk.get("section_header", ""),
                chunk.get("section_family", ""),
                chunk.get("parent_section_header", ""),
            ]
        ).lower()
        body = (chunk.get("section_block_text") or chunk.get("chunk_text") or "").strip()
        if not body:
            continue
        if any(k in section_text for k in ["rfx status", "rfx", "rfp"]):
            rfx_texts.append(body)
        if any(k in section_text for k in ["delayed rfp", "risk", "delay", "pending"]):
            delayed_texts.append(body)

    prioritized_text = " \n ".join(rfx_texts + all_facts)
    combined_text = prioritized_text if prioritized_text.strip() else " \n ".join(all_facts)
    lower_text = combined_text.lower()

    def _capture(patterns: List[str]) -> str:
        for pattern in patterns:
            match = re.search(pattern, lower_text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "missing"

    total_received = _capture([
        r"(\d+)\s*rfps?\s*received(?:\s*in\s*\d{4})?",
        r"received\s*in\s*\d{4}\s*[:\-]?\s*(\d+)",
    ])
    total_approved = _capture([r"(\d+)\s*approved\s*projects?", r"approved\s*projects?\s*[:\-]?\s*(\d+)"])
    total_in_progress = _capture([
        r"(\d+)\s*(?:projects?\s*)?in\s*progress",
        r"in\s*progress\s*rfps?\s*[:\-]?\s*(\d+)",
        r"in\s*progress\s*[:\-]?\s*(\d+)",
        r"rfps?\s*in\s*progress\s*[:\-]?\s*(\d+)",
    ])
    total_2026_projects = _capture([
        r"(\d+)\s*2026\s*projects?",
        r"2026\s*projects?\s*[:\-]?\s*(\d+)",
    ])
    total_cf_projects = _capture([r"(\d+)\s*cf\s*projects?", r"cf\s*projects?\s*[:\-]?\s*(\d+)"])

    if total_2026_projects == "missing" and total_in_progress != "missing":
        total_2026_projects = total_in_progress

    delayed_items: List[Dict[str, str]] = []
    delayed_source_text = " \n ".join(delayed_texts)
    for note in week_notes:
        week = note.get("week", "")
        date = note.get("report_date", "")
        for fact in note.get("key_facts", [])[:3]:
            cleaned = normalize_bullet_text(fact)
            if not cleaned:
                continue
            low = cleaned.lower()
            if not any(term in low for term in ["delayed", "pending", "group erp", "cow network", "huawei", "nokia", "internal wireless"]):
                continue

            budget_match = re.search(r"(?:sar\s*)?([\d,]{5,}(?:\.\d+)?)", cleaned, flags=re.IGNORECASE)
            budget = budget_match.group(1) if budget_match else "missing"
            if budget != "missing":
                try:
                    if float(budget.replace(",", "")) < 1000000:
                        continue
                except ValueError:
                    pass

            name = cleaned.split("-")[0].strip()
            domain = "missing"
            for d in ["billing", "mobility", "network", "cloud", "erp", "transmission", "wireless"]:
                if d in low:
                    domain = d.title()
                    break
            status = "pending/delayed"
            if "pending" in low:
                status = "pending"
            elif "delayed" in low:
                status = "delayed"

            delayed_items.append(
                {
                    "name": name or "missing",
                    "budget": budget,
                    "domain": domain,
                    "status": status,
                    "week": week,
                    "date": date,
                }
            )

    if not delayed_items and delayed_source_text:
        for m in re.finditer(r"([A-Za-z][^\n]{10,120}?)\s*(?:-|–|\|)\s*(?:.*?)(?:sar\s*)?([\d,]{5,}(?:\.\d+)?)", delayed_source_text, flags=re.IGNORECASE):
            name = normalize_bullet_text(m.group(1)) or "missing"
            budget = m.group(2)
            try:
                if float(budget.replace(",", "")) < 1000000:
                    continue
            except ValueError:
                pass
            delayed_items.append(
                {
                    "name": name,
                    "budget": budget,
                    "domain": "missing",
                    "status": "pending/delayed",
                    "week": target_week,
                    "date": "",
                }
            )

    uniq_items = []
    seen_names = set()
    for item in delayed_items:
        key = item.get("name", "").lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        uniq_items.append(item)
        if len(uniq_items) >= 5:
            break

    missing_fields = [
        field
        for field, value in {
            "total_received": total_received,
            "total_approved": total_approved,
            "total_in_progress": total_in_progress,
            "total_2026_projects": total_2026_projects,
        }.items()
        if value == "missing"
    ]

    return {
        "week": target_week,
        "total_received": total_received,
        "total_approved": total_approved,
        "total_in_progress": total_in_progress,
        "total_2026_projects": total_2026_projects,
        "total_cf_projects": total_cf_projects,
        "delayed_high_budget_rfps": uniq_items,
        "missing_fields": missing_fields,
    }


def build_structured_sections(notes: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {
        "Strategy & Architecture": [],
        "Cloud & Infrastructure": [],
        "Governance & Compliance": [],
        "Cost Optimization": [],
        "Programs & Operations": [],
    }

    for note in notes:
        week = note.get("week", "")
        date = note.get("report_date", "")
        facts = note.get("key_facts", []) or []
        for fact in facts[:3]:
            section = _map_fact_to_exec_section(note, fact)
            line = (f"{week} ({date}): " if week else "") + fact
            line = " ".join(line.split())
            if line and line.lower() not in {existing.lower() for existing in sections[section]}:
                sections[section].append(line)

    for key in list(sections.keys()):
        sections[key] = sections[key][:5]

    return sections


def retrieve_context(
    query: str,
    intent_result: Dict[str, Any],
    query_embedding: List[float],
    vector_store: Any,
    chunk_repo: Any,
) -> Dict[str, Any]:
    semantic_top_k = 10
    semantic_ids = vector_store.query(query_embedding, semantic_top_k)
    chunks = chunk_repo.batch_get_chunks(semantic_ids)
    rank_index = {chunk_id: idx for idx, chunk_id in enumerate(semantic_ids)}

    intent = intent_result.get("intent", "fact_lookup")
    available_week_rows: List[Dict[str, str]] = []
    try:
        available_week_rows = chunk_repo.list_available_weeks()
    except Exception:
        available_week_rows = [
            {"week": chunk.get("week", ""), "report_date": chunk.get("report_date", "")}
            for chunk in chunks
            if chunk.get("week")
        ]

    target_scope = detect_target_weeks(query, intent_result, available_week_rows)
    target_weeks = target_scope.get("target_weeks", [])
    target_major_sections = intent_result.get("target_major_sections") or []
    target_week_set = set(target_weeks)
    week_dates = target_scope.get("week_dates", {})
    week_dates_iso = target_scope.get("week_dates_iso", {})

    filtered_chunks = chunks
    if target_week_set:
        in_scope = [chunk for chunk in chunks if chunk.get("week") in target_week_set]
        filtered_chunks = in_scope

    if target_major_sections:
        section_scoped = [chunk for chunk in filtered_chunks if _chunk_in_target_major_sections(chunk, target_major_sections)]
        if section_scoped:
            filtered_chunks = section_scoped

    scoped_pool: List[Dict[str, Any]] = []
    if hasattr(chunk_repo, "scan_chunks_by_weeks") and target_weeks:
        try:
            scoped_pool = chunk_repo.scan_chunks_by_weeks(target_weeks, limit=220)
        except Exception:
            scoped_pool = []

    if target_major_sections and scoped_pool:
        scoped_pool = [chunk for chunk in scoped_pool if _chunk_in_target_major_sections(chunk, target_major_sections)]

    candidate_chunks = list(filtered_chunks)
    candidate_ids = {chunk.get("chunk_id", "") for chunk in candidate_chunks}
    for pool_chunk in scoped_pool:
        chunk_id = pool_chunk.get("chunk_id", "")
        if chunk_id and chunk_id in candidate_ids:
            continue
        header_value = (pool_chunk.get("section_header") or pool_chunk.get("section_title") or "").lower()
        high_header = any(term in header_value for term in ["weekly digest", "key projects", "hot topics", "strategy", "cloud", "governance", "compliance", "cost"]) 
        high_header = high_header or any(term in header_value for term in ["rfx", "rfp", "delayed rfp", "risks", "ntn", "satellite"])
        if high_header:
            candidate_chunks.append(pool_chunk)
            if chunk_id:
                candidate_ids.add(chunk_id)

    if target_major_sections:
        strict_candidates = [chunk for chunk in candidate_chunks if _chunk_in_target_major_sections(chunk, target_major_sections)]
        if strict_candidates:
            candidate_chunks = strict_candidates

    ordered_target_weeks = sorted(target_weeks, key=_parse_week_num, reverse=True)

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for chunk in candidate_chunks:
        chunk_id = chunk.get("chunk_id", "")
        rank = rank_index.get(chunk_id, semantic_top_k)
        semantic_score = max(0.0, (semantic_top_k - rank) / semantic_top_k)
        if chunk_id not in rank_index:
            semantic_score = 0.2
        week = chunk.get("week", "")
        section_weight = _section_weight(chunk)
        recency_bonus = _week_recency_bonus(week, ordered_target_weeks)
        intent_bonus = _intent_relevance_bonus(chunk, intent)
        focus_bonus = _query_focus_bonus(chunk, query, intent)
        score = semantic_score + section_weight + recency_bonus + intent_bonus + focus_bonus

        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)

    intent_limits = {
        "fact_lookup": 3,
        "weekly_summary": 8,
        "hot_topics": 7,
        "progress_comparison": 6,
        "delayed_initiatives": 8,
        "trend_analysis": 6,
        "risk_analysis": 5,
    }
    selected_count = min(intent_limits.get(intent, 5), 10)
    query_lc = (query or "").lower()
    if intent == "fact_lookup" and any(term in query_lc for term in ["rfp", "rfx", "status"]):
        selected_count = max(selected_count, 5)

    if intent == "weekly_summary" and not target_major_sections:
        selected = _ensure_weekly_summary_coverage(scored, selected_count)
    else:
        selected = [chunk for _, chunk in scored[:selected_count]]

    selected_week_set = {chunk.get("week", "") for chunk in selected if chunk.get("week")}
    missing_target_weeks = [week for week in target_weeks if week and week not in selected_week_set]

    if missing_target_weeks and hasattr(chunk_repo, "scan_chunks_by_weeks"):
        try:
            supplemental = chunk_repo.scan_chunks_by_weeks(missing_target_weeks, limit=30)
            supplemental_scored: List[Tuple[float, Dict[str, Any]]] = []
            for chunk in supplemental:
                week = chunk.get("week", "")
                section_weight = _section_weight(chunk)
                recency_bonus = _week_recency_bonus(week, ordered_target_weeks)
                fallback_score = 0.25 + section_weight + recency_bonus
                supplemental_scored.append((fallback_score, chunk))

            supplemental_scored.sort(key=lambda x: x[0], reverse=True)
            selected_by_id = {chunk.get("chunk_id"): chunk for chunk in selected if chunk.get("chunk_id")}
            selected_by_week = {chunk.get("week", "") for chunk in selected if chunk.get("week")}

            for _, chunk in supplemental_scored:
                week = chunk.get("week", "")
                chunk_id = chunk.get("chunk_id", "")
                if not week or week in selected_by_week:
                    continue
                if chunk_id and chunk_id in selected_by_id:
                    continue
                selected.append(chunk)
                if chunk_id:
                    selected_by_id[chunk_id] = chunk
                selected_by_week.add(week)
                if len(selected) >= selected_count:
                    break

            selected = selected[:selected_count]
        except Exception:
            pass

    pool_chunks = scoped_pool if scoped_pool else filtered_chunks

    selected = _expand_to_section_blocks(selected, pool_chunks)

    selected_weeks = _sort_weeks([chunk.get("week", "") for chunk in selected], ascending=True)
    filtered_weeks = _sort_weeks([chunk.get("week", "") for chunk in filtered_chunks], ascending=True)

    resolved_week_dates: Dict[str, str] = {}
    for chunk in selected:
        week = chunk.get("week", "")
        date = chunk.get("report_date", "")
        if week and date and week not in resolved_week_dates:
            resolved_week_dates[week] = date

    for week in target_weeks:
        if week not in resolved_week_dates and week in week_dates:
            resolved_week_dates[week] = week_dates.get(week, "")

    resolved_scope_weeks = target_weeks if target_weeks else selected_weeks
    top_sections = _dedupe([chunk.get("section_title", "") for chunk in selected if chunk.get("section_title")])[:5]
    normalized_week_date_map = {
        week: {
            "report_date": week_dates.get(week, ""),
            "report_date_iso": week_dates_iso.get(week, ""),
        }
        for week in target_weeks
    }

    return {
        "semantic_ids": semantic_ids,
        "scored_count": len(scored),
        "retrieved_chunks": len(chunks),
        "target_weeks": target_weeks,
        "target_major_sections": target_major_sections,
        "target_resolved_from": target_scope.get("resolved_from"),
        "normalized_week_date_map": normalized_week_date_map,
        "filtered_retrieval_weeks": filtered_weeks,
        "top_sections": top_sections,
        "selected_chunks": selected,
        "selected_weeks": selected_weeks,
        "resolved_scope_weeks": resolved_scope_weeks,
        "resolved_week_dates": resolved_week_dates,
    }


def extract_structured_notes(chunks: List[Dict[str, Any]], intent_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []

    budget_pattern = re.compile(r"SAR\s*[\d,]+(?:\.\d+)?", re.IGNORECASE)
    rfp_count_pattern = re.compile(r"(\d+)\s*(?:RFP|RFx|cases?|projects?)", re.IGNORECASE)
    delayed_pattern = re.compile(r"\b(delayed|pending|on hold|in progress)\b", re.IGNORECASE)
    week_pattern = re.compile(r"\bWK[-\s]?(\d{1,2})\b", re.IGNORECASE)
    date_pattern = re.compile(
        r"\b(\d{1,2}[-/\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/\s]\d{2,4})\b",
        re.IGNORECASE,
    )

    noisy_markers = [
        "sub rfp name",
        "impacted domain",
        "pending with",
        "expense gd",
        "budget (sar)",
        "status pending",
    ]

    def _clean_fact(value: str) -> str:
        fact = " ".join((value or "").replace("", " ").replace("•", " ").split())
        fact = fact.strip("-: ")
        return fact

    def _is_low_signal_fact(value: str) -> bool:
        text = (value or "").lower()
        if len(text) < 18:
            return True
        if any(marker in text for marker in noisy_markers):
            return True
        if text in {"tech enablement", "sector weekly report", "gcto updates"}:
            return True
        return False

    for chunk in chunks:
        text = (chunk.get("chunk_text") or "").strip()
        if not text:
            continue

        week = chunk.get("week", "")
        if not week:
            week_match = week_pattern.search(text)
            if week_match:
                week = f"WK-{int(week_match.group(1)):02d}"

        report_date = chunk.get("report_date", "")
        if not report_date:
            date_match = date_pattern.search(text)
            if date_match:
                report_date = date_match.group(1)

        raw_parts = re.split(r"(?<=[.!?])\s+|\s*[;•]\s*", text)
        facts = []
        for part in raw_parts:
            cleaned = _clean_fact(part)
            if not cleaned or _is_low_signal_fact(cleaned):
                continue
            facts.append(cleaned)
        key_facts = facts[:3]
        budgets = budget_pattern.findall(text)[:3]
        counts = rfp_count_pattern.findall(text)[:4]
        statuses = sorted(set(match.group(1).lower() for match in delayed_pattern.finditer(text)))

        notes.append(
            {
                "week": week,
                "report_date": report_date,
                "section_title": chunk.get("section_title", "General"),
                "section_header": chunk.get("section_header", chunk.get("section_title", "General")),
                "section_family": chunk.get("section_family", "General"),
                "theme_candidate": chunk.get("section_family") or chunk.get("section_title") or "General",
                "key_facts": key_facts,
                "risks_blockers": statuses,
                "metrics_budgets": budgets + counts,
                "source_page": chunk.get("page_number") or chunk.get("source_page"),
            }
        )

    max_notes = 16
    return notes[:max_notes]


def _normalize_theme(raw: str) -> str:
    value = (raw or "General").strip()
    lc = value.lower()
    for canonical, keywords in THEME_CLUSTERS.items():
        if any(keyword in lc for keyword in keywords):
            return canonical
    return value[:80]


def merge_structured_notes(notes: List[Dict[str, Any]], intent_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for note in notes:
        theme = _normalize_theme(note.get("theme_candidate") or note.get("section_title") or "General")
        bucket = merged.setdefault(
            theme,
            {
                "theme": theme,
                "weeks": set(),
                "facts": [],
                "metrics": [],
                "risks": set(),
                "sections": set(),
            },
        )

        week = note.get("week")
        if week:
            bucket["weeks"].add(week)
        bucket["sections"].add(note.get("section_title", "General"))
        bucket["facts"].extend(note.get("key_facts", []))
        bucket["metrics"].extend(note.get("metrics_budgets", []))
        bucket["risks"].update(note.get("risks_blockers", []))

    merged_list: List[Dict[str, Any]] = []
    for item in merged.values():
        merged_list.append(
            {
                "theme": item["theme"],
                "weeks": sorted(item["weeks"]),
                "sections": sorted(item["sections"]),
                "facts": _dedupe(item["facts"])[:3],
                "metrics": _dedupe(item["metrics"])[:6],
                "risks": sorted(item["risks"]),
            }
        )

    merged_list.sort(key=lambda x: (len(x["weeks"]), len(x["facts"])), reverse=True)

    intent = intent_result.get("intent", "weekly_summary")
    caps = {
        "hot_topics": 5,
        "weekly_summary": 5,
        "progress_comparison": 5,
        "trend_analysis": 5,
        "delayed_initiatives": 5,
        "fact_lookup": 3,
        "risk_analysis": 5,
    }
    return merged_list[: caps.get(intent, 5)]


def _dedupe(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        normalized = " ".join((value or "").split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def build_intent_prompt(query: str, intent_result: Dict[str, Any], merged_themes: List[Dict[str, Any]], notes: List[Dict[str, Any]]) -> str:
    intent = intent_result.get("intent", "fact_lookup")
    resolved_scope_weeks = intent_result.get("resolved_scope_weeks") or []
    resolved_week_dates = intent_result.get("resolved_week_dates") or {}

    compact_lines: List[str] = []
    for idx, theme in enumerate(merged_themes, start=1):
        compact_lines.append(f"[{idx}] Theme: {theme['theme']}")
        if theme["weeks"]:
            compact_lines.append(f"Weeks: {', '.join(theme['weeks'])}")
        if theme["metrics"]:
            compact_lines.append(f"Metrics: {', '.join(theme['metrics'][:4])}")
        if theme["facts"]:
            compact_lines.append(f"Facts: {' | '.join(theme['facts'][:3])}")
        if theme["risks"]:
            compact_lines.append(f"Risks: {', '.join(theme['risks'][:3])}")
        compact_lines.append("")

    if not compact_lines:
        compact_lines = ["No strong structured themes found from context."]

    scope_lines: List[str] = []
    for week in resolved_scope_weeks:
        date = resolved_week_dates.get(week, "")
        scope_lines.append(f"- {week}" + (f" ({date})" if date else ""))

    if not scope_lines:
        scope_lines = ["- Scope not resolved from metadata; use strongest available week evidence only."]

    intent_directives = {
        "fact_lookup": "Answer with concise executive bullets using exact values and week/date references.",
        "weekly_summary": "Answer with concise executive bullets only; include the highest-impact updates in scope.",
        "progress_comparison": "Answer with concise executive bullets; emphasize week-over-week movement.",
        "delayed_initiatives": "Answer with concise executive bullets focused on delayed items, budget exposure, and owners if available.",
        "trend_analysis": "Answer with concise executive bullets focused on trends/anomalies and evidence.",
        "hot_topics": "Answer with concise executive bullets focused on strategic hot topics.",
        "risk_analysis": "Answer with concise executive bullets focused on key risks and constraints.",
    }

    notes_brief = []
    for note in notes[:8]:
        notes_brief.append(
            f"- {note.get('week', 'N/A')} {note.get('report_date', '')} | {note.get('section_title', 'General')} | "
            f"{'; '.join(note.get('key_facts', [])[:1])}"
        )

    return (
        "You are analyzing weekly TSA reports.\n"
        "Use only the structured notes and merged themes.\n"
        "Return ONLY concise executive bullets (no numbered sections, no rigid templates, no decorative headings).\n"
        "Each bullet should be one clear insight and include week/date when available.\n"
        "Prioritize strategic implications, risks, budget/portfolio impact, and leadership actions.\n"
        "Audience is VP Strategy & Architecture in a telecom operator; prioritize major cross-domain topics, pain points, and CTO-level escalation signals.\n"
        "Do not drop major updates present in Weekly Digest or Key Projects & Hot Topics.\n"
        "Do not invent facts. If critical data is missing, say: I don't have enough information.\n"
        "Never include emojis. Never start with phrases like 'Here is' or 'Here's your analysis'.\n"
        "Never include weeks outside the resolved scope unless the user explicitly asked for them.\n"
        f"Intent: {intent}\n"
        f"Directive: {intent_directives.get(intent, intent_directives['fact_lookup'])}\n"
        "Response constraints:\n"
        "- 4-8 bullets total\n"
        "- No predefined sections\n"
        "- No concluding summary block\n"
        "- Keep each bullet concise\n\n"
        "Resolved Scope Weeks:\n"
        + "\n".join(scope_lines)
        + "\n\n"
        f"User Query:\n{query}\n\n"
        "Merged Themes:\n"
        + "\n".join(compact_lines[:120])
        + "\nStructured Notes (compact):\n"
        + "\n".join(notes_brief)
    )


def apply_prompt_budget(prompt: str, max_chars: int = 6500) -> str:
    if len(prompt) <= max_chars:
        return prompt
    return prompt[:max_chars].rstrip() + "\n\n[Prompt trimmed for budget]"


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def build_deterministic_fallback_response(
    query: str,
    intent_result: Dict[str, Any],
    merged_themes: List[Dict[str, Any]],
    notes: List[Dict[str, Any]],
    selected_chunks: Optional[List[Dict[str, Any]]] = None,
) -> str:
    intent = intent_result.get("intent", "weekly_summary")
    scope_weeks = intent_result.get("resolved_scope_weeks") or []
    week_dates = intent_result.get("resolved_week_dates") or {}

    def _wk_label(week: str) -> str:
        date = week_dates.get(week, "")
        return f"{week} ({date})" if date else week

    def _render_bullets(items: List[str]) -> str:
        cleaned: List[str] = []
        seen = set()
        for item in items:
            text = " ".join((item or "").split()).strip("-: ")
            if not text:
                continue

            if cleaned and re.match(r"^[a-z]", text):
                cleaned[-1] = f"{cleaned[-1]} {text}"
                continue

            norm = re.sub(r"\W+", " ", text.lower()).strip()
            if norm in seen:
                continue
            seen.add(norm)
            cleaned.append(f"- {text}")
            if len(cleaned) >= 8:
                break
        return "\n".join(cleaned) if cleaned else "- I don't have enough information."

    scope_line = ", ".join(_wk_label(week) for week in scope_weeks[:8]) if scope_weeks else "Best available weeks"

    structured = aggregate_section_bullets(notes)

    target_major_sections = intent_result.get("target_major_sections") or []

    def _chunk_matches_section(chunk: Dict[str, Any], section: str) -> bool:
        metadata_text = " ".join(
            [
                (chunk.get("major_section") or ""),
                (chunk.get("section_title") or ""),
                (chunk.get("section_header") or ""),
                (chunk.get("parent_section_header") or ""),
            ]
        ).lower()
        if section.lower() in metadata_text:
            return True
        return any(term in metadata_text for term in MAJOR_SECTION_MATCH_TERMS.get(section, []))

    def _section_updates_from_chunks(section: str) -> List[str]:
        lines: List[str] = []
        seen = set()
        for chunk in (selected_chunks or []):
            if not _chunk_matches_section(chunk, section):
                continue
            week = chunk.get("week", "")
            date = chunk.get("report_date", "")
            body = (chunk.get("section_block_text") or chunk.get("chunk_text") or "").strip()
            if not body:
                continue
            parts = re.split(r"\n|(?<=[.!?])\s+", body)
            for part in parts:
                cleaned = normalize_bullet_text(part)
                if not cleaned:
                    continue

                if lines and re.match(r"^(?:for|and|with|to|including|which|that)\b", cleaned, flags=re.IGNORECASE):
                    lines[-1] = f"{lines[-1]} {cleaned}"
                    continue

                key = re.sub(r"\W+", " ", cleaned.lower()).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                label = f"{week} ({date}): " if week else ""
                lines.append(f"{label}{cleaned}".strip())
                if len(lines) >= 8:
                    return lines
        return lines

    if intent == "weekly_summary" and not target_major_sections:
        executive_bullets: List[str] = []
        if scope_weeks:
            executive_bullets.append("Scope: " + ", ".join(_wk_label(week) for week in reversed(scope_weeks)))
        else:
            executive_bullets.append("Scope: Best available context")

        section_order = [
            "Strategic & Architecture Initiatives",
            "Cloud, Infrastructure & Technology Programs",
            "Cost Optimization & Efficiency",
            "Governance, Compliance & Enterprise Architecture",
            "Programs, Reporting & Execution",
        ]
        for section_name in section_order:
            section_items = structured.get(section_name, [])
            if not section_items:
                continue
            for item in section_items[:2]:
                cleaned = normalize_bullet_text(item)
                if cleaned:
                    executive_bullets.append(cleaned)

        risk_lines: List[str] = []
        for note in notes:
            week = note.get("week", "")
            date = note.get("report_date", "")
            for fact in note.get("key_facts", [])[:2]:
                cleaned = normalize_bullet_text(fact)
                low = cleaned.lower()
                if cleaned and any(k in low for k in ["risk", "delay", "pending", "constraint", "approval", "readiness", "resource"]):
                    line = (f"{week} ({date}): " if week else "") + cleaned
                    if line.lower() not in {x.lower() for x in risk_lines}:
                        risk_lines.append(line)
                if len(risk_lines) >= 3:
                    break
            if len(risk_lines) >= 3:
                break

        executive_bullets.extend(risk_lines[:2])
        return _render_bullets(executive_bullets)

    if intent == "fact_lookup" and any(term in (query or "").lower() for term in ["rfp", "rfx", "status"]):
        latest_week = scope_weeks[-1] if scope_weeks else ""
        latest_date = week_dates.get(latest_week, "")
        rfp = extract_latest_rfp_status(latest_week, notes, selected_chunks=selected_chunks)
        bullets = [
            f"Scope: {latest_week}{' (' + latest_date + ')' if latest_date else scope_line}",
            f"Total Received: {rfp.get('total_received', 'missing')}",
            f"Total Approved: {rfp.get('total_approved', 'missing')}",
            f"Total In-Progress: {rfp.get('total_in_progress', 'missing')}",
        ]
        projects_2026 = rfp.get("total_2026_projects", "missing")
        if projects_2026 != "missing":
            bullets.append(f"2026 Projects: {projects_2026}")
        cf_projects = rfp.get("total_cf_projects", "missing")
        if cf_projects != "missing":
            bullets.append(f"CF Projects: {cf_projects}")

        delayed_items = rfp.get("delayed_high_budget_rfps", [])
        if delayed_items:
            for item in delayed_items[:4]:
                bullets.append(
                    f"Delayed: {item.get('name', 'missing')} | Budget: {item.get('budget', 'missing')} | "
                    f"Domain: {item.get('domain', 'missing')} | Status: {item.get('status', 'missing')}"
                )
        return _render_bullets(bullets)

    if target_major_sections and intent in {"weekly_summary", "hot_topics", "progress_comparison", "trend_analysis", "risk_analysis"}:
        bullets: List[str] = []
        if scope_weeks:
            bullets.append("Scope: " + ", ".join(_wk_label(week) for week in reversed(scope_weeks)))
        else:
            bullets.append(f"Scope: {scope_line}")

        section_lines: List[str] = []
        for section in target_major_sections:
            section_lines.extend(_section_updates_from_chunks(section))
        if not section_lines and target_major_sections:
            for note in notes:
                section_text = " ".join(
                    [
                        note.get("section_title", ""),
                        note.get("section_header", ""),
                        note.get("section_family", ""),
                    ]
                ).lower()
                if any(term in section_text for term in MAJOR_SECTION_MATCH_TERMS.get(target_major_sections[0], [])):
                    for fact in note.get("key_facts", [])[:2]:
                        cleaned = normalize_bullet_text(fact)
                        if cleaned:
                            week = note.get("week", "")
                            date = note.get("report_date", "")
                            label = f"{week} ({date}): " if week else ""
                            section_lines.append(f"{label}{cleaned}")

        bullets.extend(section_lines[:8])
        return _render_bullets(bullets)

    if intent == "delayed_initiatives" and any(term in (query or "").lower() for term in ["delayed rfp", "delayed rfps"]):
        weeks_for_lookup = scope_weeks[:] if scope_weeks else [""]
        aggregated_items: List[Dict[str, str]] = []
        seen_items = set()

        for week in reversed(weeks_for_lookup):
            rfp = extract_latest_rfp_status(week, notes, selected_chunks=selected_chunks)
            for item in rfp.get("delayed_high_budget_rfps", []):
                name = (item.get("name") or "missing").strip()
                if not name:
                    continue
                key = name.lower()
                if key in seen_items:
                    continue
                seen_items.add(key)
                aggregated_items.append(
                    {
                        "name": name,
                        "budget": item.get("budget", "missing"),
                        "domain": item.get("domain", "missing"),
                        "status": item.get("status", "pending/delayed"),
                        "week": week,
                    }
                )
                if len(aggregated_items) >= 12:
                    break
            if len(aggregated_items) >= 12:
                break

        bullets = [f"Scope: {scope_line}"]
        if aggregated_items:
            for item in aggregated_items:
                wk = item.get("week", "")
                wk_label = _wk_label(wk) if wk else ""
                bullets.append(
                    f"{item.get('name', 'missing')} | Budget: {item.get('budget', 'missing')} | "
                    f"Domain: {item.get('domain', 'missing')} | Status: {item.get('status', 'pending/delayed')}"
                    + (f" | Week: {wk_label}" if wk_label else "")
                )
        else:
            top_facts: List[str] = []
            for note in notes:
                for fact in (note.get("key_facts") or [])[:2]:
                    cleaned = normalize_bullet_text(fact)
                    if cleaned and "delay" in cleaned.lower() and cleaned.lower() not in {x.lower() for x in top_facts}:
                        top_facts.append(cleaned)
                if len(top_facts) >= 8:
                    break
            bullets.extend(top_facts)
        return _render_bullets(bullets)

    if intent in {"fact_lookup", "hot_topics", "progress_comparison", "trend_analysis", "delayed_initiatives"}:
        title_map = {
            "fact_lookup": "Direct Answer",
            "hot_topics": "Major Hot Topics",
            "progress_comparison": "Progress Comparison – TSA Sector Weekly Reports",
            "trend_analysis": "Key Trends & Anomalies",
            "delayed_initiatives": "Delayed or Pending Initiatives",
        }
        bullets = [f"Scope: {scope_line}"]

        top_facts: List[str] = []
        for note in notes:
            week = note.get("week", "")
            date = note.get("report_date", "")
            for fact in (note.get("key_facts") or [])[:2]:
                fact_line = ((f"{week} ({date}): " if week else "") + fact).strip()
                if fact_line and fact_line.lower() not in {f.lower() for f in top_facts}:
                    top_facts.append(fact_line)
                if len(top_facts) >= 6:
                    break
            if len(top_facts) >= 6:
                break

        bullets.extend(top_facts)
        return _render_bullets(bullets)

    theme_lines = []
    for item in merged_themes[:4]:
        facts = item.get("facts") or []
        if facts:
            theme_lines.append(f"- {item.get('theme', 'Theme')}: {facts[0]}")
    if not theme_lines:
        theme_lines = ["- I don't have enough information."]

    return _render_bullets([f"Scope: {scope_line}"] + [line.lstrip("- ") for line in theme_lines])
