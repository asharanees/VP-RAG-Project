import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common.weekly_analyst import (
    build_deterministic_fallback_response,
    build_deterministic_fallback_response,
    build_intent_prompt,
    classify_query_intent,
    detect_target_weeks,
    extract_latest_rfp_status,
    extract_structured_notes,
    merge_structured_notes,
    normalize_bullet_text,
    retrieve_context,
)
from common.pdf_utils import read_pdf_pages
from common.chunking import split_into_chunks
from common.chunking import normalize_week_metadata


class TestWeeklyAnalystIntent(unittest.TestCase):
    def test_hot_topics_intent(self):
        result = classify_query_intent("What are the major hot topics?")
        self.assertEqual(result["intent"], "hot_topics")

    def test_progress_comparison_intent(self):
        result = classify_query_intent("Progress comparisons across different weeks")
        self.assertEqual(result["intent"], "progress_comparison")

    def test_delayed_initiatives_intent(self):
        result = classify_query_intent("Identification of delayed or pending initiatives from last 3 months")
        self.assertEqual(result["intent"], "delayed_initiatives")

    def test_trend_anomaly_intent(self):
        result = classify_query_intent("Insights into trends or anomalies in last 3 weeks")
        self.assertEqual(result["intent"], "trend_analysis")

    def test_last_4_weeks_summary_intent(self):
        result = classify_query_intent("Summary of overall updates from last 4 weeks")
        self.assertEqual(result["intent"], "weekly_summary")
        self.assertEqual(result["latest_n_weeks"], 4)

    def test_gcto_updates_sets_section_focus(self):
        result = classify_query_intent("what are the latest GCTO updates")
        self.assertEqual(result["intent"], "weekly_summary")
        self.assertIn("GCTO Updates", result.get("target_major_sections", []))

    def test_delayed_rfps_sets_section_focus(self):
        result = classify_query_intent("show me all delayed rfps")
        self.assertEqual(result["intent"], "delayed_initiatives")
        self.assertIn("Delayed RFPs", result.get("target_major_sections", []))

        def test_rfp_status_with_delayed_includes_rfx_and_delayed_sections(self):
            result = classify_query_intent("What is the latest RFP status including delayed high-budget RFPs")
            self.assertEqual(result["intent"], "fact_lookup")
            self.assertIn("RFx Status", result.get("target_major_sections", []))
            self.assertIn("Delayed RFPs", result.get("target_major_sections", []))


class TestChunkingMajorSections(unittest.TestCase):
    def test_split_into_chunks_keeps_major_section_and_multiple_windows(self):
        long_body = " ".join([f"token{i}" for i in range(120)])
        pages = [
            (
                1,
                "\n".join(
                    [
                        "GCTO Updates",
                        "Owner update line",
                        "Delayed RFPs",
                        long_body,
                    ]
                ),
            )
        ]

        chunks = split_into_chunks(pages, chunk_size_tokens=40, overlap_tokens=10)
        delayed_chunks = [c for c in chunks if c.get("major_section") == "Delayed RFPs"]

        self.assertGreaterEqual(len(delayed_chunks), 3)
        self.assertTrue(all(c.get("token_count", 0) <= 40 for c in delayed_chunks))
        self.assertTrue(all(c.get("section_block_text") for c in delayed_chunks))


class TestWeeklyAnalystNotes(unittest.TestCase):
    def test_extract_and_merge_notes(self):
        chunks = [
            {
                "week": "WK-06",
                "report_date": "11-Feb-2026",
                "section_title": "Cloud Roadmap",
                "section_family": "Cloud & Infrastructure",
                "chunk_text": "WK-06 Cloud roadmap shared. SAR 4,700,000 savings. delayed items are tracked.",
                "page_number": 3,
            },
            {
                "week": "WK-07",
                "report_date": "18-Feb-2026",
                "section_title": "STAR compliance",
                "section_family": "Governance & Compliance",
                "chunk_text": "WK-07 STAR non-compliance cases increased by 21 cases. In progress governance fixes.",
                "page_number": 4,
            },
        ]
        intent = {"intent": "weekly_summary"}
        notes = extract_structured_notes(chunks, intent)
        self.assertGreaterEqual(len(notes), 2)

        merged = merge_structured_notes(notes, intent)
        self.assertGreaterEqual(len(merged), 1)
        self.assertIn("theme", merged[0])

    def test_normalize_bullet_text_removes_incomplete_tails(self):
        self.assertEqual(normalize_bullet_text("Linked 150+ validated compliance cases and aligned open items to the"), "")


class TestDeterministicGctoOutput(unittest.TestCase):
    def test_gcto_output_does_not_include_non_gcto_chunks(self):
        intent = {
            "intent": "weekly_summary",
            "resolved_scope_weeks": ["WK-07", "WK-08"],
            "resolved_week_dates": {"WK-07": "18-Feb-2026", "WK-08": "25-Feb-2026"},
            "target_major_sections": ["GCTO Updates"],
        }

        selected_chunks = [
            {
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "major_section": "GCTO Updates",
                "section_title": "GCTO Updates",
                "section_header": "GCTO Updates",
                "parent_section_header": "GCTO Updates",
                "section_block_text": "Develop a Proposal For Implementing Circular Economy Principles Across All Subsidiaries.",
            },
            {
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "major_section": "Weekly Digest",
                "section_title": "Governance",
                "section_header": "Governance",
                "parent_section_header": "Governance",
                "section_block_text": "Compliance & AI Enablement: Linked 150+ validated compliance cases with AI use-cases.",
            },
        ]

        result = build_deterministic_fallback_response(
            "what are the latest gcto updates",
            intent,
            merged_themes=[],
            notes=[],
            selected_chunks=selected_chunks,
        )

        output = result.lower()
        self.assertIn("scope:", output)
        self.assertIn("circular economy", output)
        self.assertNotIn("compliance & ai enablement", output)


class _FakeVectorStore:
    def __init__(self, chunk_ids):
        self._chunk_ids = chunk_ids

    def query(self, _embedding, _top_k):
        return self._chunk_ids


class _FakeChunkRepo:
    def __init__(self, by_id, week_rows=None, supplemental=None):
        self._by_id = by_id
        self._week_rows = week_rows or []
        self._supplemental = supplemental or []

    def batch_get_chunks(self, chunk_ids):
        return [self._by_id[cid] for cid in chunk_ids if cid in self._by_id]

    def list_available_weeks(self):
        return self._week_rows

    def scan_chunks_by_weeks(self, weeks, limit=40):
        return [chunk for chunk in self._supplemental if chunk.get("week") in set(weeks)][:limit]


class TestRetrieveContextScope(unittest.TestCase):
    def test_last_two_weeks_is_strictly_applied(self):
        chunk_ids = ["c1", "c2", "c3", "c4"]
        by_id = {
            "c1": {"chunk_id": "c1", "week": "WK-01", "report_date": "08-Jan-2026", "chunk_text": "Older note", "section_title": "General", "section_family": "General"},
            "c2": {"chunk_id": "c2", "week": "WK-07", "report_date": "18-Feb-2026", "chunk_text": "Recent note A", "section_title": "Cloud", "section_family": "Cloud & Infrastructure"},
            "c3": {"chunk_id": "c3", "week": "WK-08", "report_date": "25-Feb-2026", "chunk_text": "Recent note B", "section_title": "Governance", "section_family": "Governance & Compliance"},
            "c4": {"chunk_id": "c4", "week": "WK-03", "report_date": "22-Jan-2026", "chunk_text": "Older note 2", "section_title": "General", "section_family": "General"},
        }
        intent = {
            "intent": "weekly_summary",
            "explicit_weeks": [],
            "latest_n_weeks": 2,
            "requested_time_scope": "latest_n_weeks",
        }

        result = retrieve_context(
            "summary of overall updates from last 2 weeks",
            intent,
            [0.1, 0.2],
            _FakeVectorStore(chunk_ids),
            _FakeChunkRepo(
                by_id,
                week_rows=[
                    {"week": "WK-01", "report_date": "08-Jan-2026"},
                    {"week": "WK-03", "report_date": "22-Jan-2026"},
                    {"week": "WK-07", "report_date": "18-Feb-2026"},
                    {"week": "WK-08", "report_date": "25-Feb-2026"},
                ],
            ),
        )

        selected_weeks = {chunk.get("week") for chunk in result["selected_chunks"]}
        self.assertTrue(selected_weeks.issubset({"WK-07", "WK-08"}))
        self.assertEqual(result["resolved_scope_weeks"], ["WK-07", "WK-08"])

    def test_missing_target_week_is_supplemented(self):
        chunk_ids = ["c1", "c2"]
        by_id = {
            "c1": {"chunk_id": "c1", "week": "WK-07", "report_date": "18-Feb-2026", "chunk_text": "Week 7 strategic update", "section_title": "Weekly Digest", "section_family": "Governance & Compliance"},
            "c2": {"chunk_id": "c2", "week": "WK-06", "report_date": "11-Feb-2026", "chunk_text": "Week 6 update", "section_title": "Operational", "section_family": "Operational updates"},
        }
        supplemental = [
            {"chunk_id": "s1", "week": "WK-08", "report_date": "25-Feb-2026", "chunk_text": "Week 8 cloud strategy", "section_title": "Weekly Digest", "section_family": "Cloud & Infrastructure"}
        ]
        intent = {
            "intent": "weekly_summary",
            "explicit_weeks": [],
            "latest_n_weeks": 2,
            "requested_time_scope": "latest_n_weeks",
        }

        result = retrieve_context(
            "latest updates from last 2 weeks",
            intent,
            [0.1, 0.2],
            _FakeVectorStore(chunk_ids),
            _FakeChunkRepo(
                by_id,
                week_rows=[
                    {"week": "WK-07", "report_date": "18-Feb-2026"},
                    {"week": "WK-08", "report_date": "25-Feb-2026"},
                ],
                supplemental=supplemental,
            ),
        )

        selected_weeks = {chunk.get("week") for chunk in result["selected_chunks"]}
        self.assertIn("WK-07", selected_weeks)
        self.assertIn("WK-08", selected_weeks)

    def test_gcto_query_filters_to_gcto_major_section(self):
        chunk_ids = ["c1", "c2", "c3"]
        by_id = {
            "c1": {
                "chunk_id": "c1",
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "chunk_text": "GCTO weekly update on engagement model",
                "major_section": "GCTO Updates",
                "section_title": "GCTO Updates",
                "section_family": "General",
            },
            "c2": {
                "chunk_id": "c2",
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "chunk_text": "Delayed RFP rows",
                "major_section": "Delayed RFPs",
                "section_title": "Delayed RFPs",
                "section_family": "Risks & Delays",
            },
            "c3": {
                "chunk_id": "c3",
                "week": "WK-07",
                "report_date": "18-Feb-2026",
                "chunk_text": "Weekly digest highlights",
                "major_section": "Weekly Digest",
                "section_title": "Weekly Digest",
                "section_family": "General",
            },
        }

        intent = classify_query_intent("what are the latest gcto updates")
        result = retrieve_context(
            "what are the latest gcto updates",
            intent,
            [0.1, 0.2],
            _FakeVectorStore(chunk_ids),
            _FakeChunkRepo(
                by_id,
                week_rows=[
                    {"week": "WK-07", "report_date": "18-Feb-2026"},
                    {"week": "WK-08", "report_date": "25-Feb-2026"},
                ],
            ),
        )

        self.assertTrue(result["selected_chunks"])
        self.assertTrue(all((chunk.get("major_section") or "") == "GCTO Updates" for chunk in result["selected_chunks"]))

    def test_delayed_rfp_query_filters_to_delayed_major_section(self):
        chunk_ids = ["c1", "c2", "c3"]
        by_id = {
            "c1": {
                "chunk_id": "c1",
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "chunk_text": "Delayed RFP item A",
                "major_section": "Delayed RFPs",
                "section_title": "Delayed RFPs",
                "section_family": "Risks & Delays",
            },
            "c2": {
                "chunk_id": "c2",
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "chunk_text": "RFx status totals",
                "major_section": "RFx Status",
                "section_title": "RFx Status",
                "section_family": "Portfolio & Financials",
            },
            "c3": {
                "chunk_id": "c3",
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "chunk_text": "General updates",
                "major_section": "Weekly Digest",
                "section_title": "Weekly Digest",
                "section_family": "General",
            },
        }

        intent = classify_query_intent("show me all delayed rfps")
        result = retrieve_context(
            "show me all delayed rfps",
            intent,
            [0.1, 0.2],
            _FakeVectorStore(chunk_ids),
            _FakeChunkRepo(
                by_id,
                week_rows=[{"week": "WK-08", "report_date": "25-Feb-2026"}],
            ),
        )

        self.assertTrue(result["selected_chunks"])
        self.assertTrue(all((chunk.get("major_section") or "") == "Delayed RFPs" for chunk in result["selected_chunks"]))

    def test_weekly_digest_query_filters_to_weekly_digest_major_section(self):
        chunk_ids = ["c1", "c2", "c3"]
        by_id = {
            "c1": {
                "chunk_id": "c1",
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "chunk_text": "Weekly digest: asset registration approved",
                "major_section": "Weekly Digest",
                "section_title": "Weekly Digest",
                "section_family": "General",
            },
            "c2": {
                "chunk_id": "c2",
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "chunk_text": "GCTO card updates",
                "major_section": "GCTO Updates",
                "section_title": "GCTO Updates",
                "section_family": "General",
            },
            "c3": {
                "chunk_id": "c3",
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "chunk_text": "Delayed RFP row",
                "major_section": "Delayed RFPs",
                "section_title": "Delayed RFPs",
                "section_family": "Risks & Delays",
            },
        }

        intent = classify_query_intent("what are the latest weekly digest updates")
        result = retrieve_context(
            "what are the latest weekly digest updates",
            intent,
            [0.1, 0.2],
            _FakeVectorStore(chunk_ids),
            _FakeChunkRepo(
                by_id,
                week_rows=[{"week": "WK-08", "report_date": "25-Feb-2026"}],
            ),
        )

        self.assertTrue(result["selected_chunks"])
        self.assertTrue(all((chunk.get("major_section") or "") == "Weekly Digest" for chunk in result["selected_chunks"]))


class TestWeekDetection(unittest.TestCase):
    def test_detect_latest_updates_defaults_to_latest_two(self):
        intent = classify_query_intent("latest updates")
        result = detect_target_weeks(
            "latest updates",
            intent,
            [
                {"week": "WK-06", "report_date": "11-Feb-2026", "report_date_iso": "2026-02-11"},
                {"week": "WK-07", "report_date": "18-Feb-2026", "report_date_iso": "2026-02-18"},
                {"week": "WK-08", "report_date": "25-Feb-2026", "report_date_iso": "2026-02-25"},
            ],
        )
        self.assertEqual(result["target_weeks"], ["WK-07", "WK-08"])

    def test_detect_explicit_weeks(self):
        intent = classify_query_intent("compare WK-07 and WK-08")
        result = detect_target_weeks(
            "compare WK-07 and WK-08",
            intent,
            [
                {"week": "WK-06", "report_date": "11-Feb-2026", "report_date_iso": "2026-02-11"},
                {"week": "WK-07", "report_date": "18-Feb-2026", "report_date_iso": "2026-02-18"},
                {"week": "WK-08", "report_date": "25-Feb-2026", "report_date_iso": "2026-02-25"},
            ],
        )
        self.assertEqual(result["target_weeks"], ["WK-07", "WK-08"])


class TestWeekNormalization(unittest.TestCase):
    def test_timeline_week_date_is_preferred_over_unrelated_date(self):
        text = "Technology Strategy report WK-08. 30 June 2026. timeline: W07 18-Feb W08 25-Feb"
        normalized = normalize_week_metadata(text, source_page=1)
        self.assertIn("WK-08", normalized)
        self.assertEqual(normalized["WK-08"]["report_date_iso"], "2026-02-25")
        self.assertEqual(normalized["WK-07"]["report_date_iso"], "2026-02-18")


class TestUserQueryRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pdf_path = Path(__file__).resolve().parents[1] / "TSA Sector Report February 26,2026.pdf"
        with pdf_path.open("rb") as handle:
            pages = read_pdf_pages(handle.read())

        chunks = split_into_chunks(pages, chunk_size_tokens=700, overlap_tokens=100)
        cls.by_id = {f"c{i}": dict(chunk, chunk_id=f"c{i}") for i, chunk in enumerate(chunks)}

        cls.week_rows = []
        seen_weeks = set()
        for chunk in cls.by_id.values():
            week = chunk.get("week", "")
            if not week or week in seen_weeks:
                continue
            seen_weeks.add(week)
            cls.week_rows.append(
                {
                    "week": week,
                    "report_date": chunk.get("report_date", ""),
                    "report_date_iso": chunk.get("report_date_iso", ""),
                }
            )

        class _AllVectorStore:
            def __init__(self, chunk_ids):
                self.chunk_ids = chunk_ids

            def query(self, _embedding, _top_k):
                return self.chunk_ids

        class _Repo:
            def __init__(self, rows, mapping):
                self.rows = rows
                self.mapping = mapping

            def batch_get_chunks(self, chunk_ids):
                return [self.mapping[cid] for cid in chunk_ids if cid in self.mapping]

            def list_available_weeks(self):
                return self.rows

            def scan_chunks_by_weeks(self, weeks, limit=220):
                week_set = set(weeks)
                return [chunk for chunk in self.mapping.values() if chunk.get("week") in week_set][:limit]

        cls.vector_store = _AllVectorStore(list(cls.by_id.keys()))
        cls.repo = _Repo(cls.week_rows, cls.by_id)

    def _retrieve_text(self, query: str):
        intent = classify_query_intent(query)
        result = retrieve_context(query, intent, [0.1], self.vector_store, self.repo)
        selected_text = " ".join(
            (chunk.get("section_block_text") or chunk.get("chunk_text") or "")
            for chunk in result["selected_chunks"]
        ).lower()
        return intent, result, selected_text

    def test_hot_topics_last_week_classifies_as_hot_topics(self):
        intent = classify_query_intent("What are the hot topics last week")
        self.assertEqual(intent["intent"], "hot_topics")
        self.assertEqual(intent["latest_n_weeks"], 1)

    def test_latest_rfp_status_has_rfx_markers(self):
        _, result, selected_text = self._retrieve_text("What is the latest RFP status")
        self.assertEqual(result["resolved_scope_weeks"], ["WK-07", "WK-08"])
        key_markers = ["89 rfps", "approved projects", "rfx status"]
        hits = [marker for marker in key_markers if marker in selected_text]
        self.assertGreaterEqual(len(hits), 2)

    def test_ntn_progress_has_ntn_markers(self):
        _, result, selected_text = self._retrieve_text("What is the progress on NTN")
        self.assertEqual(result["resolved_scope_weeks"], ["WK-07", "WK-08"])
        key_markers = ["ntn", "satellite", "oq", "nb-iot"]
        hits = [marker for marker in key_markers if marker in selected_text]
        self.assertGreaterEqual(len(hits), 2)

    def test_weekly_summary_prompt_requires_bulleted_exec_summary(self):
        query = "Summary of overall updates from last 2 weeks"
        intent = classify_query_intent(query)
        intent = {
            **intent,
            "resolved_scope_weeks": ["WK-07", "WK-08"],
            "resolved_week_dates": {"WK-07": "18-Feb-2026", "WK-08": "25-Feb-2026"},
        }
        notes = [
            {
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "section_title": "Governance & Compliance",
                "section_header": "Governance & Compliance",
                "section_family": "Architecture / Strategy",
                "theme_candidate": "Governance & Compliance",
                "key_facts": ["Linked 150+ validated compliance cases with AI use-cases"],
                "risks_blockers": [],
                "metrics_budgets": ["150"],
                "source_page": 2,
            }
        ]
        merged = merge_structured_notes(notes, intent)
        prompt = build_intent_prompt(query, intent, merged, notes)
        self.assertIn("Return ONLY concise executive bullets", prompt)
        self.assertIn("No predefined sections", prompt)


class TestDeterministicRfpExtractor(unittest.TestCase):
    def test_extract_latest_rfp_status_parses_required_kpis(self):
        notes = [
            {
                "week": "WK-08",
                "report_date": "25-Feb-2026",
                "key_facts": [
                    "89 RFPs Received in 2026",
                    "44 Approved Projects",
                    "In Progress RFPs 45",
                    "44 CF Projects",
                ],
            }
        ]
        selected_chunks = [
            {
                "week": "WK-08",
                "section_title": "RFx Status",
                "section_header": "RFx Status",
                "section_family": "Architecture / Strategy",
                "chunk_text": "89 RFPs Received in 2026 44 Approved Projects In Progress RFPs 45 44 CF Projects",
            }
        ]

        result = extract_latest_rfp_status("WK-08", notes, selected_chunks=selected_chunks)

        self.assertEqual(result["total_received"], "89")
        self.assertEqual(result["total_approved"], "44")
        self.assertEqual(result["total_in_progress"], "45")
        self.assertEqual(result["total_2026_projects"], "45")
        self.assertEqual(result["total_cf_projects"], "44")

        def test_fact_lookup_rfp_response_keeps_kpi_lines(self):
            query = "What is the latest RFP status? Include total received, approved, in-progress, and top delayed high-budget RFPs."
            intent = {
                "intent": "fact_lookup",
                "resolved_scope_weeks": ["WK-07", "WK-08"],
                "resolved_week_dates": {"WK-07": "18-Feb-2026", "WK-08": "25-Feb-2026"},
                "target_major_sections": ["RFx Status", "Delayed RFPs"],
            }
            notes = [
                {
                    "week": "WK-08",
                    "report_date": "25-Feb-2026",
                    "section_title": "RFx Status",
                    "section_header": "RFx Status",
                    "section_family": "Portfolio & Financials",
                    "key_facts": ["89 RFPs Received in 2026", "44 Approved Projects", "In Progress RFPs 45"],
                    "risks_blockers": [],
                    "metrics_budgets": [],
                }
            ]
            selected_chunks = [
                {
                    "week": "WK-08",
                    "report_date": "25-Feb-2026",
                    "major_section": "RFx Status",
                    "section_title": "RFx Status",
                    "section_header": "RFx Status",
                    "chunk_text": "89 RFPs Received in 2026 44 Approved Projects In Progress RFPs 45 44 CF Projects",
                }
            ]

            answer = build_deterministic_fallback_response(query, intent, [], notes, selected_chunks=selected_chunks)
            self.assertIn("Total Received", answer)
            self.assertIn("Total Approved", answer)
            self.assertIn("Total In-Progress", answer)


class TestSampleInformationCoverage(unittest.TestCase):
    def test_last_two_weeks_retrieval_covers_major_sample_facts(self):
        pdf_path = Path(__file__).resolve().parents[1] / "TSA Sector Report February 26,2026.pdf"
        self.assertTrue(pdf_path.exists())

        with pdf_path.open("rb") as handle:
            pages = read_pdf_pages(handle.read())

        chunks = split_into_chunks(pages, chunk_size_tokens=700, overlap_tokens=100)
        by_id = {f"c{i}": dict(chunk, chunk_id=f"c{i}") for i, chunk in enumerate(chunks)}

        week_rows = []
        seen_weeks = set()
        for chunk in by_id.values():
            week = chunk.get("week", "")
            if not week or week in seen_weeks:
                continue
            seen_weeks.add(week)
            week_rows.append(
                {
                    "week": week,
                    "report_date": chunk.get("report_date", ""),
                    "report_date_iso": chunk.get("report_date_iso", ""),
                }
            )

        class _AllVectorStore:
            def __init__(self, chunk_ids):
                self.chunk_ids = chunk_ids

            def query(self, _embedding, _top_k):
                return self.chunk_ids

        class _Repo:
            def __init__(self, rows, mapping):
                self.rows = rows
                self.mapping = mapping

            def batch_get_chunks(self, chunk_ids):
                return [self.mapping[cid] for cid in chunk_ids if cid in self.mapping]

            def list_available_weeks(self):
                return self.rows

            def scan_chunks_by_weeks(self, weeks, limit=220):
                week_set = set(weeks)
                return [chunk for chunk in self.mapping.values() if chunk.get("week") in week_set][:limit]

        intent = classify_query_intent("Summary of overall updates from last 2 weeks")
        result = retrieve_context(
            "Summary of overall updates from last 2 weeks",
            intent,
            [0.1],
            _AllVectorStore(list(by_id.keys())),
            _Repo(week_rows, by_id),
        )

        self.assertEqual(result["resolved_scope_weeks"], ["WK-07", "WK-08"])

        selected_text = " ".join(
            (chunk.get("section_block_text") or chunk.get("chunk_text") or "")
            for chunk in result["selected_chunks"]
        ).lower()

        key_markers = [
            "cloud roadmap",
            "nokia",
            "adobe experience manager",
            "4.7",
            "gtu dashboard",
            "site forecasting",
        ]
        hits = [marker for marker in key_markers if marker in selected_text]

        self.assertGreaterEqual(len(hits), 5)


class TestSampleFourQuestionCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pdf_path = Path(__file__).resolve().parents[1] / "TSA Sector Report February 26,2026.pdf"
        with pdf_path.open("rb") as handle:
            pages = read_pdf_pages(handle.read())

        chunks = split_into_chunks(pages, chunk_size_tokens=700, overlap_tokens=100)
        cls.by_id = {f"c{i}": dict(chunk, chunk_id=f"c{i}") for i, chunk in enumerate(chunks)}

        cls.week_rows = []
        seen_weeks = set()
        for chunk in cls.by_id.values():
            week = chunk.get("week", "")
            if not week or week in seen_weeks:
                continue
            seen_weeks.add(week)
            cls.week_rows.append(
                {
                    "week": week,
                    "report_date": chunk.get("report_date", ""),
                    "report_date_iso": chunk.get("report_date_iso", ""),
                }
            )

        class _AllVectorStore:
            def __init__(self, chunk_ids):
                self.chunk_ids = chunk_ids

            def query(self, _embedding, _top_k):
                return self.chunk_ids

        class _Repo:
            def __init__(self, rows, mapping):
                self.rows = rows
                self.mapping = mapping

            def batch_get_chunks(self, chunk_ids):
                return [self.mapping[cid] for cid in chunk_ids if cid in self.mapping]

            def list_available_weeks(self):
                return self.rows

            def scan_chunks_by_weeks(self, weeks, limit=220):
                week_set = set(weeks)
                return [chunk for chunk in self.mapping.values() if chunk.get("week") in week_set][:limit]

        cls.vector_store = _AllVectorStore(list(cls.by_id.keys()))
        cls.repo = _Repo(cls.week_rows, cls.by_id)

    def _run_query(self, query: str):
        intent = classify_query_intent(query)
        result = retrieve_context(query, intent, [0.1], self.vector_store, self.repo)
        selected_text = " ".join(
            (chunk.get("section_block_text") or chunk.get("chunk_text") or "")
            for chunk in result["selected_chunks"]
        ).lower()
        return result, selected_text

    def test_q1_progress_comparison_has_multi_week_core_markers(self):
        result, selected_text = self._run_query("Progress comparisons across different weeks")
        self.assertEqual(result["resolved_scope_weeks"], ["WK-06", "WK-07", "WK-08"])
        key_markers = ["4.7", "adobe experience manager", "89 rfps", "cloud roadmap"]
        hits = [marker for marker in key_markers if marker in selected_text]
        self.assertGreaterEqual(len(hits), 3)

    def test_q2_delayed_initiatives_has_high_impact_delayed_markers(self):
        result, selected_text = self._run_query("Identification of delayed or pending initiatives from last 3 months")
        self.assertGreaterEqual(len(result["resolved_scope_weeks"]), 4)
        key_markers = [
            "group erp transformation",
            "765",
            "internal wireless network improvements",
            "huawei spare parts",
            "cow network",
        ]
        hits = [marker for marker in key_markers if marker in selected_text]
        self.assertGreaterEqual(len(hits), 4)

    def test_q3_trends_anomalies_has_pipeline_and_governance_markers(self):
        result, selected_text = self._run_query("Insights into trends or anomalies in last 3 weeks")
        self.assertEqual(result["resolved_scope_weeks"], ["WK-06", "WK-07", "WK-08"])
        key_markers = ["64 rfps", "75 rfps", "89 rfps", "star", "150+"]
        hits = [marker for marker in key_markers if marker in selected_text]
        self.assertGreaterEqual(len(hits), 4)

    def test_q4_last_4_weeks_summary_has_cross_domain_markers(self):
        result, selected_text = self._run_query("Summary of overall updates from last 4 weeks")
        self.assertEqual(result["resolved_scope_weeks"], ["WK-05", "WK-06", "WK-07", "WK-08"])
        key_markers = ["ai-ran strategy", "databricks", "21 new star", "4.7", "optical network"]
        hits = [marker for marker in key_markers if marker in selected_text]
        self.assertGreaterEqual(len(hits), 3)


if __name__ == "__main__":
    unittest.main()
