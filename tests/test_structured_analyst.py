import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common.structured_analyst import (
    _extract_weekly_digest_tail_from_key_projects,
    _split_weekly_keyprojects_boundary,
    build_structured_prompt,
    classify_query_intent,
    extract_gcto_updates_fallback,
    get_structured_context,
    parse_structured_reports_from_pages,
    resolve_target_weeks,
)


SAMPLE_DATA = [
    {
        "week_label": "WK-06",
        "week_num": 6,
        "report_date": "2026-02-11",
        "sections": {
            "gcto_updates": "Presented EA repository engagement model.",
            "weekly_digest": "Achieved OPEX savings and progressed governance approvals.",
            "key_projects_hot_topics": "Databricks TCO analysis initiated.",
            "cost_optimization": "OPEX savings tracked for ADTAN.",
            "executive_summary_rfx_cost": "Cost optimization and RFx governance improved.",
            "rfx_status": {
                "total_received": 64,
                "total_approved": 32,
                "total_in_progress": 22,
                "total_cf_projects": 21,
                "raw_section_text": "64 RFPs, 32 approved, 22 in progress, 21 CF.",
            },
            "delayed_rfps": [
                {
                    "initiative_name": "Group ERP Transformation",
                    "domain": "Corporate Enablement",
                    "budget_sar": 765000000,
                    "status": "delayed",
                    "pending_with": "TA-Domain",
                    "expense_type": "CAPEX",
                    "raw_row_text": "Group ERP delayed",
                }
            ],
        },
    },
    {
        "week_label": "WK-07",
        "week_num": 7,
        "report_date": "2026-02-18",
        "sections": {
            "gcto_updates": "On-track circular economy proposal and repository progress.",
            "weekly_digest": "Cloud HW reclamation and assets registration approved.",
            "key_projects_hot_topics": "NTN coordination and DR resiliency updates.",
            "cost_optimization": "3.747M OPEX savings through timeline reduction.",
            "executive_summary_rfx_cost": "RFx and optimization require governance acceleration.",
            "rfx_status": {
                "total_received": 75,
                "total_approved": 37,
                "total_in_progress": 38,
                "total_cf_projects": 34,
                "raw_section_text": "75 RFPs, 37 approved, 38 in progress, 34 CF.",
            },
            "delayed_rfps": [
                {
                    "initiative_name": "Huawei Spare Parts for Transmission",
                    "domain": "Field Operation Center",
                    "budget_sar": 36000000,
                    "status": "delayed",
                    "pending_with": "TA-Domain",
                    "expense_type": "OPEX",
                    "raw_row_text": "Huawei delayed",
                }
            ],
        },
    },
    {
        "week_label": "WK-08",
        "week_num": 8,
        "report_date": "2026-02-25",
        "sections": {
            "gcto_updates": "Updated GCTO ownership and completed card-level tracking.",
            "weekly_digest": "Compliance cases linked with AI use-cases; governance advanced.",
            "key_projects_hot_topics": "Tech refresh cloud migration and ERM risk engagement.",
            "cost_optimization": "Cost programs under validation for TSA and TEC.",
            "executive_summary_rfx_cost": "Executive RFx and cost posture improved with some constraints.",
            "rfx_status": {
                "total_received": 89,
                "total_approved": 44,
                "total_in_progress": 45,
                "total_cf_projects": 44,
                "raw_section_text": "89 RFPs, 44 approved, 45 in progress, 44 CF.",
            },
            "delayed_rfps": [
                {
                    "initiative_name": "Operation and maintenance of Transport network",
                    "domain": "Field Operation Center",
                    "budget_sar": 900000000,
                    "status": "delayed",
                    "pending_with": "TA-Domain",
                    "expense_type": "OPEX",
                    "raw_row_text": "Transport delayed",
                }
            ],
        },
    },
]


class TestStructuredCoreQueries(unittest.TestCase):
    def test_gcto_phrase_routes_direct(self):
        for query in [
            "gcto updates",
            "latest gcto updates",
            "show gcto updates",
            "what are the latest gcto updates",
        ]:
            intent = classify_query_intent(query)["intent"]
            self.assertEqual(intent, "gcto_updates")

    def test_query_1_latest_rfx_status(self):
        query = "What is the latest RFP status? Include total received, approved, in-progress, and top delayed high-budget RFPs."
        intent = classify_query_intent(query)["intent"]
        self.assertEqual(intent, "rfx_status")
        weeks = resolve_target_weeks(query, ["WK-06", "WK-07", "WK-08"], intent)
        self.assertEqual(weeks, ["WK-08"])
        context = get_structured_context(intent, weeks, SAMPLE_DATA, query)
        self.assertIn("WK-08", context["metrics"])
        self.assertGreaterEqual(len(context["delayed_rfps"]), 1)

    def test_query_2_summary_last_2_weeks(self):
        query = "Summary of overall updates from last 2 weeks, focused on strategic impact, and risks."
        intent = classify_query_intent(query)["intent"]
        weeks = resolve_target_weeks(query, ["WK-06", "WK-07", "WK-08"], intent)
        self.assertEqual(weeks, ["WK-07", "WK-08"])
        context = get_structured_context(intent, weeks, SAMPLE_DATA, query)
        self.assertGreaterEqual(len(context["evidence"]), 2)

    def test_query_3_hot_topics(self):
        query = "What are the major hot topics?"
        intent = classify_query_intent(query)["intent"]
        self.assertEqual(intent, "hot_topics")
        weeks = resolve_target_weeks(query, ["WK-06", "WK-07", "WK-08"], intent)
        context = get_structured_context(intent, weeks, SAMPLE_DATA, query)
        joined = " ".join(context["evidence"]).lower()
        self.assertIn("key projects & hot topics", joined)

    def test_ntn_satellite_progress_routes_to_topic_search(self):
        # NTN/satellite queries are topic-specific and should search all sections
        query = "What is the progress on NTN and satellite initiatives"
        intent = classify_query_intent(query)["intent"]
        self.assertEqual(intent, "topic_search")

    def test_query_4_progress_comparison(self):
        query = "Progress comparisons across different weeks."
        intent = classify_query_intent(query)["intent"]
        self.assertEqual(intent, "progress_comparison")
        weeks = resolve_target_weeks(query, ["WK-06", "WK-07", "WK-08"], intent)
        self.assertEqual(weeks, ["WK-06", "WK-07", "WK-08"])
        context = get_structured_context(intent, weeks, SAMPLE_DATA, query)
        self.assertGreaterEqual(len(context["metrics"]), 3)

    def test_query_5_delayed_initiatives_last_3_months(self):
        query = "Identification of delayed or pending initiatives from last 3 months."
        intent = classify_query_intent(query)["intent"]
        self.assertEqual(intent, "delayed_initiatives")
        weeks = resolve_target_weeks(query, ["WK-06", "WK-07", "WK-08"], intent)
        context = get_structured_context(intent, weeks, SAMPLE_DATA, query)
        self.assertGreaterEqual(len(context["delayed_rfps"]), 2)

    def test_query_6_trend_analysis_last_3_weeks(self):
        query = "Insights into trends or anomalies in last 3 weeks."
        intent = classify_query_intent(query)["intent"]
        self.assertEqual(intent, "trend_analysis")
        weeks = resolve_target_weeks(query, ["WK-06", "WK-07", "WK-08"], intent)
        self.assertEqual(weeks, ["WK-06", "WK-07", "WK-08"])
        context = get_structured_context(intent, weeks, SAMPLE_DATA, query)
        prompt = build_structured_prompt(query, intent, context)
        self.assertIn("Key Trends", prompt)

    def test_gcto_query_routes_to_latest_week_only(self):
        query = "what are the latest gcto updates"
        intent = classify_query_intent(query)["intent"]
        self.assertEqual(intent, "gcto_updates")
        weeks = resolve_target_weeks(query, ["WK-06", "WK-07", "WK-08"], intent)
        self.assertEqual(weeks, ["WK-08"])
        context = get_structured_context(intent, weeks, SAMPLE_DATA, query)
        self.assertEqual(context["target_weeks"], ["WK-08"])
        joined = " ".join(context["evidence"]).lower()
        self.assertIn("gcto updates", joined)


class TestStructuredParser(unittest.TestCase):
    def test_split_weekly_keyprojects_boundary(self):
        weekly = "\n".join(
            [
                "Satellite/ NTN",
                "Some digest item",
                "Tech-Refresh and Migration to public Cloud",
                "A meeting with ITP team",
                "GTU Blueprint 2026",
            ]
        )
        head, tail = _split_weekly_keyprojects_boundary(weekly)
        self.assertIn("Satellite/ NTN", head)
        self.assertIn("Tech-Refresh and Migration to public Cloud", tail)

    def test_extract_weekly_digest_tail_from_key_projects(self):
        key_text = "\n".join(
            [
                "Tech-Refresh and Migration to public Cloud",
                "Key projects line",
                "Tech Enablement",
                "Mobile App Assessment (Group Level)",
                "IPNOC Assessment",
            ]
        )
        tail, main = _extract_weekly_digest_tail_from_key_projects(key_text)
        self.assertIn("Tech Enablement", tail)
        self.assertIn("Tech-Refresh and Migration to public Cloud", main)

    def test_parse_structured_sections_from_page_text(self):
        pages = [
            (
                1,
                "\n".join(
                    [
                        "WK-08 25-Feb-2026",
                        "GCTO Updates",
                        "Owner update content",
                        "RFx Status",
                        "89 RFPs Received in 2026",
                        "44 Approved Projects",
                        "In Progress RFPs 45",
                        "Delayed RFPs",
                        "Transport Network delayed OPEX 900,000,000 TA-Domain",
                    ]
                ),
            )
        ]
        reports = parse_structured_reports_from_pages(pages)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["week_label"], "WK-08")
        self.assertEqual(reports[0]["sections"]["rfx_status"]["total_received"], 89)

    def test_executive_summary_struct_is_populated(self):
        pages = [
            (
                1,
                "\n".join(
                    [
                        "WK-08 25-Feb-2026",
                        "Executive Summary – RFx & Cost Optimization",
                        "Capex Savings 2026 Estimate",
                        "Opex Savings 2026 Estimate",
                        "00.00 M",
                        "IT Platforms",
                        "SEA",
                        "TEC Validated",
                        "TSA Efforts",
                    ]
                ),
            )
        ]
        reports = parse_structured_reports_from_pages(pages)
        struct = reports[0]["sections"].get("executive_summary_rfx_cost_struct", {})
        self.assertIn("capex_savings_2026_estimate", struct)
        self.assertIn("raw_table_text", struct)

    def test_rfx_status_struct_is_populated(self):
        pages = [
            (
                1,
                "\n".join(
                    [
                        "WK-08 25-Feb-2026",
                        "RFx Status",
                        "89 RFPs Received in 2026",
                        "44 Approved Projects",
                        "45 In Progress RFPs",
                        "45 2026 Projects",
                        "44 CF Projects",
                        "Envelope 2026 07",
                        "Envelope 2025 11",
                        "CF 2024 15",
                        "CF 2023 00",
                        "Project without FN 01",
                        "Total 34",
                        "Approved by RFX 16",
                        "MPA Review in RFX 24",
                        "PIB In-Progress 00",
                        "Total 40",
                    ]
                ),
            )
        ]
        reports = parse_structured_reports_from_pages(pages)
        struct = reports[0]["sections"].get("rfx_status_struct", {})
        self.assertEqual(struct.get("overview", {}).get("received_2026"), 89)
        self.assertEqual(struct.get("pib_not_received_by_rfx", {}).get("total"), 34)
        self.assertEqual(struct.get("direct_value_mpa_projects_status", {}).get("total"), 40)

    def test_delayed_rfps_struct_is_populated(self):
        pages = [
            (
                1,
                "\n".join(
                    [
                        "WK-08 25-Feb-2026",
                        "Delayed RFPs",
                        "Sub RFP Name Impacted Domain Status Pending With Expense GD Name Budget (SAR)",
                        "CorpE – CBU Demand – Tribe Q3 DA - AA TA-Domain CAPEXDELAYED 2,935,210 Corporate Enablement",
                    ]
                ),
            )
        ]
        reports = parse_structured_reports_from_pages(pages)
        struct = reports[0]["sections"].get("delayed_rfps_struct", {})
        rows = struct.get("rows", [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("sub_rfp_name"), "CorpE – CBU Demand – Tribe Q3")
        self.assertEqual(rows[0].get("impacted_domain"), "DA - AA")
        self.assertEqual(rows[0].get("status"), "delayed")
        self.assertEqual(rows[0].get("pending_with"), "TA-Domain")
        self.assertEqual(rows[0].get("expense"), "CAPEX")
        self.assertEqual(rows[0].get("budget_sar"), 2935210)

    def test_delayed_rows_captured_when_delayed_section_precedes_rfx(self):
        pages = [
            (
                1,
                "\n".join(
                    [
                        "WK-08 25-Feb-2026",
                        "Delayed RFPs",
                        "Internal-Wireless Network Improvements 2025 - Hajj Scope IBS 1447 (ESM + RF) SPG - HPG Supplier CAPEXDELAYED 67,519,408 Mobility Services",
                        "RFx Status",
                        "89 RFPs Received in 2026",
                    ]
                ),
            )
        ]
        reports = parse_structured_reports_from_pages(pages)
        rows = reports[0]["sections"].get("delayed_rfps", [])
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0].get("budget_sar"), 67519408)

    def test_extract_gcto_updates_fallback_from_card_block(self):
        raw = "\n".join(
            [
                "WK-08 25-Feb-2026",
                "GCTO Updates",
                "Completed | 22 Jan 2026",
                "Abdullah H. F Alfaifi Project Owner",
                "Joining the investigation force led by Infrastructure sector.",
                "On Track | 30 June 2026",
                "Sami H. Alzomaia Project Owner",
                "Develop a Proposal For Implementing Circular Economy Principles.",
                "Weekly Digest",
                "Other section starts here.",
            ]
        )
        block = extract_gcto_updates_fallback(raw)
        self.assertIn("Owner:", block)
        self.assertIn("Circular Economy", block)

    def test_extract_gcto_updates_fallback_between_headings(self):
        raw = "\n".join(
            [
                "WK-08 25-Feb-2026",
                "GCTO Updates",
                "On Track",
                "Sami H. Alzomaia Project Owner",
                "30 June 2026",
                "Develop a Proposal For Implementing Circular Economy Principles Across All Subsidiaries.",
                "Weekly Digest",
                "Other section",
            ]
        )
        block = extract_gcto_updates_fallback(raw)
        self.assertIn("Status: On Track", block)
        self.assertIn("Owner:", block)
        self.assertIn("Due date: 30 June 2026", block)
        self.assertNotIn("Weekly Digest", block)

    def test_extract_gcto_updates_fallback_when_weekly_digest_noise_precedes_content(self):
        # When GCTO header is immediately followed by a section stop with no real card,
        # strategy 2 (direct card scan) should find the card embedded later in the text.
        raw = "\n".join(
            [
                "WK-08 25-Feb-2026",
                "Sector Weekly Report",
                "GCTO Updates",
                "Sector Weekly Report",
                "Weekly Digest",
                "1",
                "Satellite/ NTN",
                "Deep dive with OQ proposed options analysis for NTN Nb-IoT connectivity.",
                "ESM Optimization",
                "Share the Enhanced Subscription Model proposal with TEC for GCTO.",
                "10 11 12",
                "On Track",
                "Sami H. Alzomaia",
                "Project Owner",
                "Develop a Proposal For Implementing Circular Economy Principles",
                "30 June 2026",
            ]
        )
        block = extract_gcto_updates_fallback(raw)
        # Strategy 2 should find the card via direct scan
        self.assertIn("On Track", block)
        self.assertIn("Sami H. Alzomaia", block)
        self.assertIn("Due date: 30 June 2026", block)
        # Weekly digest content should NOT be in the GCTO block
        self.assertNotIn("Satellite/ NTN", block)
        self.assertNotIn("Sector Weekly Report", block)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# New unit tests for the five parser fixes
# ---------------------------------------------------------------------------
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common.structured_analyst import (
    _normalize_week,
    _extract_sections_by_order,
    _clean_section_text,
    _parse_delayed_rows,
)


class TestNormalizeWeekMultiLine(unittest.TestCase):
    """Fix 1 — multi-line week label detection."""

    def test_same_line_still_works(self):
        week, num = _normalize_week("WK-08 25-Feb-2026")
        self.assertEqual(week, "WK-08")
        self.assertEqual(num, 8)

    def test_week_and_date_on_separate_lines(self):
        text = "WK-07\n18-Feb-2026\nSome content"
        week, num = _normalize_week(text)
        self.assertEqual(week, "WK-07")
        self.assertEqual(num, 7)

    def test_week_and_date_separated_by_two_lines(self):
        text = "WK-06\nSector Weekly Report\n11-Feb-2026"
        week, num = _normalize_week(text)
        self.assertEqual(week, "WK-06")
        self.assertEqual(num, 6)

    def test_week_label_no_date_still_returns_week(self):
        text = "WK-05\nSome content without a date"
        week, num = _normalize_week(text)
        self.assertEqual(week, "WK-05")
        self.assertEqual(num, 5)

    def test_no_week_returns_empty(self):
        week, num = _normalize_week("Just some random text")
        self.assertEqual(week, "")
        self.assertIsNone(num)


class TestExtractSectionsResilient(unittest.TestCase):
    """Fix 2 — resilient section scanning."""

    def test_missing_middle_section_does_not_block_later_sections(self):
        # weekly_digest is missing — rfx_status should still be found
        text = "\n".join([
            "GCTO Updates",
            "Some gcto content",
            # weekly_digest intentionally absent
            "RFx Status",
            "89 RFPs Received in 2026",
            "Delayed RFPs",
            "Some delayed row DELAYED OPEX 1000000",
        ])
        result = _extract_sections_by_order(text)
        self.assertIn("gcto_updates", result)
        self.assertIn("rfx_status", result)
        self.assertIn("delayed_rfps", result)
        self.assertNotIn("weekly_digest", result)

    def test_all_sections_present(self):
        text = "\n".join([
            "GCTO Updates", "gcto content",
            "Weekly Digest", "digest content",
            "Key Projects & Hot Topics", "projects content",
            "IT Efficiency Initiatives - Cost Optimization", "cost content",
            "Executive Summary – RFx & Cost Optimization", "exec content",
            "RFx Status", "rfx content",
            "Delayed RFPs", "delayed content DELAYED OPEX 500000",
        ])
        result = _extract_sections_by_order(text)
        for key in ["gcto_updates", "weekly_digest", "key_projects_hot_topics",
                    "cost_optimization", "executive_summary_rfx_cost",
                    "rfx_status", "delayed_rfps"]:
            self.assertIn(key, result)

    def test_out_of_order_section_still_captured(self):
        # delayed_rfps appears before rfx_status
        text = "\n".join([
            "Delayed RFPs", "delayed row DELAYED CAPEX 200000",
            "RFx Status", "64 RFPs Received in 2026",
        ])
        result = _extract_sections_by_order(text)
        self.assertIn("delayed_rfps", result)
        self.assertIn("rfx_status", result)


class TestCleanSectionTextRfxFilter(unittest.TestCase):
    """Fix 3 — rfx_status numeric line preservation."""

    def test_approved_projects_line_preserved(self):
        result = _clean_section_text("rfx_status", "44 Approved Projects")
        self.assertIn("44 Approved Projects", result)

    def test_in_progress_line_preserved(self):
        result = _clean_section_text("rfx_status", "45 In Progress RFPs")
        self.assertIn("45 In Progress RFPs", result)

    def test_bare_date_token_dropped(self):
        result = _clean_section_text("rfx_status", "25-Feb\nSome valid line")
        self.assertNotIn("25-Feb", result)

    def test_rfps_received_line_preserved(self):
        result = _clean_section_text("rfx_status", "89 RFPs Received in 2026")
        self.assertIn("89 RFPs Received in 2026", result)


class TestParseDelayedRowsRobust(unittest.TestCase):
    """Fix 4 — robust delayed row parsing."""

    def test_capexdelayed_fused_token(self):
        rows = _parse_delayed_rows(
            "Internal-Wireless Network Improvements 2025 SPG - HPG Supplier CAPEXDELAYED 67519408 Mobility Services"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["expense"], "CAPEX")
        self.assertEqual(rows[0]["status"], "delayed")

    def test_budget_with_commas(self):
        rows = _parse_delayed_rows(
            "Group ERP Transformation FUs Enablement DELAYED TA-Domain CAPEX 765,000,000"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["budget_sar"], 765000000)
        self.assertIsInstance(rows[0]["budget_sar"], int)

    def test_multi_word_domain_extracted(self):
        # Real PDF format: shortcode domain sits immediately before pending_with
        # Multi-word GD names appear after the budget as the tail
        rows = _parse_delayed_rows(
            "Huawei Spare Parts for Transmission HPG TA-Domain OPEXDELAYED 36,000,000 Field Operation Center"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["impacted_domain"], "HPG")
        self.assertEqual(rows[0]["gd_name"], "Field Operation Center")

    def test_pending_with_ta_domain(self):
        rows = _parse_delayed_rows(
            "Some Initiative DELAYED TA-Domain CAPEX 1000000"
        )
        self.assertEqual(rows[0]["pending_with"], "TA-Domain")

    def test_pending_with_supplier(self):
        rows = _parse_delayed_rows(
            "Some Initiative DELAYED Supplier OPEX 500000"
        )
        self.assertEqual(rows[0]["pending_with"], "Supplier")

    def test_header_row_skipped(self):
        rows = _parse_delayed_rows(
            "Sub RFP Name Impacted Domain Status Pending With Expense GD Name Budget (SAR)"
        )
        self.assertEqual(rows, [])

    def test_non_delayed_line_skipped(self):
        rows = _parse_delayed_rows("Some random line with no status keyword")
        self.assertEqual(rows, [])


# ---------------------------------------------------------------------------
# Property-based tests using hypothesis
# ---------------------------------------------------------------------------
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st


SECTION_HEADERS = [
    "GCTO Updates",
    "Weekly Digest",
    "Key Projects & Hot Topics",
    "IT Efficiency Initiatives - Cost Optimization",
    "Executive Summary – RFx & Cost Optimization",
    "RFx Status",
    "Delayed RFPs",
]

REQUIRED_SECTION_KEYS = [
    "gcto_updates",
    "weekly_digest",
    "key_projects_hot_topics",
    "cost_optimization",
    "executive_summary_rfx_cost",
    "rfx_status",
    "delayed_rfps",
]


def _make_week_page(week_num: int, include_sections: list) -> str:
    """Build a minimal synthetic page for a given week."""
    lines = [f"WK-{week_num:02d} 01-Jan-2026"]
    for header in include_sections:
        lines.append(header)
        lines.append(f"Content for {header} week {week_num}")
    return "\n".join(lines)


class TestPropertySectionCompleteness(unittest.TestCase):
    """Property 1 — all 7 section keys present in every Week Record.
    Validates: Requirements 1.4, 6.1, 6.2
    """

    @h_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
    @given(
        week_num=st.integers(min_value=1, max_value=52),
        sections=st.lists(
            st.sampled_from(SECTION_HEADERS),
            min_size=0,
            max_size=7,
            unique=True,
        ),
    )
    def test_all_section_keys_always_present(self, week_num, sections):
        """**Validates: Requirements 1.4, 6.1, 6.2**"""
        page_text = _make_week_page(week_num, sections)
        reports = parse_structured_reports_from_pages([(1, page_text)])
        self.assertGreaterEqual(len(reports), 1)
        for report in reports:
            sec = report["sections"]
            for key in REQUIRED_SECTION_KEYS:
                self.assertIn(key, sec, f"Missing section key '{key}' in week {report.get('week_label')}")


class TestPropertyWeekCount(unittest.TestCase):
    """Property 2 — week count matches detected week labels.
    Validates: Requirements 2.1, 6.4
    """

    @h_settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    @given(
        week_nums=st.lists(
            st.integers(min_value=1, max_value=52),
            min_size=1,
            max_size=8,
            unique=True,
        )
    )
    def test_week_count_matches_labels(self, week_nums):
        """**Validates: Requirements 2.1, 6.4**"""
        pages = [
            (i + 1, _make_week_page(wn, ["GCTO Updates", "RFx Status"]))
            for i, wn in enumerate(week_nums)
        ]
        reports = parse_structured_reports_from_pages(pages)
        self.assertEqual(len(reports), len(week_nums))


class TestPropertyBudgetSarType(unittest.TestCase):
    """Property 3 — budget_sar is always int or None.
    Validates: Requirement 3.3
    """

    @h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(
        budget=st.one_of(
            st.integers(min_value=100000, max_value=999999999),
            st.none(),
        ),
        expense=st.sampled_from(["CAPEX", "OPEX"]),
    )
    def test_budget_sar_is_int_or_none(self, budget, expense):
        """**Validates: Requirement 3.3**"""
        if budget is None:
            line = f"Some Initiative DELAYED TA-Domain {expense}"
        else:
            # Format with commas to test comma-stripping
            budget_str = f"{budget:,}"
            line = f"Some Initiative DELAYED TA-Domain {expense} {budget_str}"
        rows = _parse_delayed_rows(line)
        for row in rows:
            val = row.get("budget_sar")
            self.assertTrue(
                val is None or isinstance(val, int),
                f"budget_sar={val!r} is not int or None",
            )


class TestPropertyRfxTotalsType(unittest.TestCase):
    """Property 4 — RFx totals are int or None.
    Validates: Requirements 4.1–4.4
    """

    @h_settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
    @given(
        received=st.integers(min_value=1, max_value=200),
        approved=st.integers(min_value=1, max_value=200),
        in_progress=st.integers(min_value=1, max_value=200),
        cf=st.integers(min_value=1, max_value=200),
    )
    def test_rfx_totals_are_int_or_none(self, received, approved, in_progress, cf):
        """**Validates: Requirements 4.1–4.4**"""
        page_text = "\n".join([
            "WK-08 25-Feb-2026",
            "RFx Status",
            f"{received} RFPs Received in 2026",
            f"{approved} Approved Projects",
            f"{in_progress} In Progress RFPs",
            f"{cf} CF Projects",
        ])
        reports = parse_structured_reports_from_pages([(1, page_text)])
        self.assertEqual(len(reports), 1)
        rfx = reports[0]["sections"]["rfx_status"]
        for field in ["total_received", "total_approved", "total_in_progress", "total_cf_projects"]:
            val = rfx.get(field)
            self.assertTrue(
                val is None or isinstance(val, int),
                f"{field}={val!r} is not int or None",
            )
        # Also assert the values are correct
        self.assertEqual(rfx["total_received"], received)
        self.assertEqual(rfx["total_approved"], approved)
        self.assertEqual(rfx["total_in_progress"], in_progress)
        self.assertEqual(rfx["total_cf_projects"], cf)
