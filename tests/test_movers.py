"""Tests for movers.py -- movers and shakers analysis.

Covers:
- Deduplication (dedup_history)
- Grade boundary alerts (find_grade_boundary_alerts)
- New entrant detection (find_new_entrants)
- Session comparison (compare_sessions)
- Website trends export (export_trends_json)
- Full report generation (generate_movers_report)
- Report serialization (to_dict, to_json, to_markdown)
- CLI integration (movers subcommand)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.movers import (
    GradeBoundaryAlert,
    NewEntrant,
    SessionComparison,
    MoversReport,
    dedup_history,
    find_grade_boundary_alerts,
    find_new_entrants,
    compare_sessions,
    export_trends_json,
    generate_movers_report,
    BOUNDARY_PROXIMITY,
)


# ---------------------------------------------------------------------------
# Fixtures: synthetic score history
# ---------------------------------------------------------------------------

def _snap(slug: str, session: int, overall: float, grade: str) -> dict:
    """Create a minimal snapshot entry."""
    return {
        "project_slug": slug,
        "session": session,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "scores": {
            "health": 80.0,
            "complexity": 70.0,
            "security": 75.0,
            "dead_code": 90.0,
            "coverage": 60.0,
            "overall": overall,
            "grade": grade,
        },
    }


BASIC_HISTORY = [
    _snap("owner/alpha", 1, 85.0, "A"),
    _snap("owner/beta", 1, 74.0, "B"),
    _snap("owner/gamma", 1, 60.0, "C+"),
    _snap("owner/alpha", 2, 85.0, "A"),
    _snap("owner/beta", 2, 74.0, "B"),
    _snap("owner/gamma", 2, 60.0, "C+"),
]

HISTORY_WITH_NEW_ENTRANT = [
    _snap("owner/alpha", 1, 85.0, "A"),
    _snap("owner/alpha", 2, 85.0, "A"),
    _snap("owner/alpha", 3, 85.0, "A"),
    _snap("owner/newbie", 2, 70.0, "B"),
    _snap("owner/newbie", 3, 70.0, "B"),
]

HISTORY_WITH_DUPLICATES = [
    _snap("owner/alpha", 1, 85.0, "A"),
    _snap("owner/alpha", 1, 85.0, "A"),  # duplicate
    _snap("owner/beta", 1, 74.0, "B"),
    _snap("owner/alpha", 2, 85.0, "A"),
    _snap("owner/alpha", 2, 85.0, "A"),  # duplicate
    _snap("owner/beta", 2, 74.0, "B"),
]

# Projects near grade boundaries:
# 89.8 -- just below A+ (90), distance = -0.2
# 80.5 -- just above A- (80), distance = +0.5
# 65.1 -- just above B- (65), distance = +0.1
BOUNDARY_HISTORY = [
    _snap("owner/near-aplus", 1, 89.8, "A"),
    _snap("owner/above-aminus", 1, 80.5, "A-"),
    _snap("owner/above-bminus", 1, 65.1, "B-"),
    _snap("owner/safe-middle", 1, 77.5, "B+"),  # not near any boundary
]


# ---------------------------------------------------------------------------
# dedup_history
# ---------------------------------------------------------------------------


class TestDedupHistory:
    def test_no_duplicates(self):
        cleaned, removed = dedup_history(BASIC_HISTORY)
        assert removed == 0
        assert len(cleaned) == len(BASIC_HISTORY)

    def test_removes_duplicates(self):
        cleaned, removed = dedup_history(HISTORY_WITH_DUPLICATES)
        assert removed == 2
        assert len(cleaned) == 4

    def test_keeps_first_occurrence(self):
        cleaned, _ = dedup_history(HISTORY_WITH_DUPLICATES)
        slugs_s1 = [e["project_slug"] for e in cleaned if e["session"] == 1]
        assert slugs_s1 == ["owner/alpha", "owner/beta"]

    def test_empty_history(self):
        cleaned, removed = dedup_history([])
        assert cleaned == []
        assert removed == 0

    def test_preserves_order(self):
        cleaned, _ = dedup_history(BASIC_HISTORY)
        sessions = [e["session"] for e in cleaned]
        slugs = [e["project_slug"] for e in cleaned]
        assert sessions == [1, 1, 1, 2, 2, 2]
        assert slugs == ["owner/alpha", "owner/beta", "owner/gamma",
                         "owner/alpha", "owner/beta", "owner/gamma"]


# ---------------------------------------------------------------------------
# find_grade_boundary_alerts
# ---------------------------------------------------------------------------


class TestGradeBoundaryAlerts:
    def test_empty_history(self):
        assert find_grade_boundary_alerts([]) == []

    def test_finds_near_promotion(self):
        alerts = find_grade_boundary_alerts(BOUNDARY_HISTORY)
        promos = [a for a in alerts if a.direction == "promotion"]
        # 89.8 is 0.2 below A+ (90) -- should be promotion alert
        aplus_alerts = [a for a in promos if a.target_grade == "A+"]
        assert len(aplus_alerts) >= 1
        assert aplus_alerts[0].project_slug == "owner/near-aplus"
        assert aplus_alerts[0].distance == pytest.approx(-0.2, abs=0.01)

    def test_finds_near_demotion(self):
        alerts = find_grade_boundary_alerts(BOUNDARY_HISTORY)
        demos = [a for a in alerts if a.direction == "demotion"]
        # 80.5 is 0.5 above A- (80) -- could be demoted to B+
        aminus_demos = [a for a in demos if a.project_slug == "owner/above-aminus"]
        assert len(aminus_demos) >= 1

    def test_safe_project_no_alert(self):
        alerts = find_grade_boundary_alerts(BOUNDARY_HISTORY)
        safe = [a for a in alerts if a.project_slug == "owner/safe-middle"]
        assert len(safe) == 0

    def test_uses_latest_session(self):
        history = [
            _snap("owner/old", 1, 89.8, "A"),
            _snap("owner/old", 2, 77.0, "B+"),  # latest is safe
        ]
        alerts = find_grade_boundary_alerts(history)
        # Should only look at session 2
        assert all(a.project_slug != "owner/old" or a.current_score == 77.0
                   for a in alerts)

    def test_custom_proximity(self):
        alerts_narrow = find_grade_boundary_alerts(BOUNDARY_HISTORY, proximity=0.3)
        alerts_wide = find_grade_boundary_alerts(BOUNDARY_HISTORY, proximity=5.0)
        assert len(alerts_narrow) <= len(alerts_wide)

    def test_alert_fields(self):
        alerts = find_grade_boundary_alerts(BOUNDARY_HISTORY)
        for a in alerts:
            assert isinstance(a.project_slug, str)
            assert isinstance(a.current_score, float)
            assert isinstance(a.current_grade, str)
            assert isinstance(a.nearest_boundary, (int, float))
            assert isinstance(a.target_grade, str)
            assert isinstance(a.distance, float)
            assert a.direction in ("promotion", "demotion")

    def test_to_dict(self):
        alert = GradeBoundaryAlert(
            project_slug="a/b", current_score=89.8, current_grade="A",
            nearest_boundary=90, target_grade="A+", distance=-0.2,
            direction="promotion",
        )
        d = alert.to_dict()
        assert d["project_slug"] == "a/b"
        assert d["direction"] == "promotion"


# ---------------------------------------------------------------------------
# find_new_entrants
# ---------------------------------------------------------------------------


class TestNewEntrants:
    def test_empty_history(self):
        assert find_new_entrants([]) == []

    def test_no_new_entrants(self):
        entrants = find_new_entrants(BASIC_HISTORY, slug_categories={})
        assert len(entrants) == 0

    def test_finds_new_project(self):
        entrants = find_new_entrants(HISTORY_WITH_NEW_ENTRANT, slug_categories={})
        assert len(entrants) == 1
        assert entrants[0].project_slug == "owner/newbie"
        assert entrants[0].first_session == 2

    def test_entrant_fields(self):
        entrants = find_new_entrants(
            HISTORY_WITH_NEW_ENTRANT,
            slug_categories={"owner/newbie": "web-framework"},
        )
        e = entrants[0]
        assert e.score == 70.0
        assert e.grade == "B"
        assert e.category == "web-framework"

    def test_default_category_is_other(self):
        entrants = find_new_entrants(HISTORY_WITH_NEW_ENTRANT, slug_categories={})
        assert entrants[0].category == "other"

    def test_to_dict(self):
        e = NewEntrant(
            project_slug="a/b", first_session=3,
            score=75.0, grade="B+", category="testing",
        )
        d = e.to_dict()
        assert d["first_session"] == 3

    def test_sorted_by_session_then_score(self):
        history = [
            _snap("owner/a", 1, 80.0, "A-"),
            _snap("owner/b", 2, 90.0, "A+"),
            _snap("owner/c", 2, 70.0, "B"),
            _snap("owner/d", 3, 85.0, "A"),
        ]
        entrants = find_new_entrants(history, slug_categories={})
        sessions = [e.first_session for e in entrants]
        assert sessions == sorted(sessions)


# ---------------------------------------------------------------------------
# compare_sessions
# ---------------------------------------------------------------------------


class TestCompareSessions:
    def test_same_session(self):
        sc = compare_sessions(BASIC_HISTORY, 1, 1)
        assert sc.session_from == 1
        assert sc.session_to == 1
        assert sc.new_projects == []
        assert sc.avg_change == 0.0

    def test_no_new_projects(self):
        sc = compare_sessions(BASIC_HISTORY, 1, 2)
        assert sc.projects_from == 3
        assert sc.projects_to == 3
        assert sc.new_projects == []

    def test_detects_new_projects(self):
        sc = compare_sessions(HISTORY_WITH_NEW_ENTRANT, 1, 2)
        assert "owner/newbie" in sc.new_projects

    def test_avg_scores(self):
        sc = compare_sessions(BASIC_HISTORY, 1, 2)
        expected = round((85.0 + 74.0 + 60.0) / 3, 1)
        assert sc.avg_score_from == expected
        assert sc.avg_score_to == expected

    def test_grade_distributions(self):
        sc = compare_sessions(BASIC_HISTORY, 1, 2)
        assert "A" in sc.grade_distribution_from
        assert "B" in sc.grade_distribution_from

    def test_empty_session(self):
        sc = compare_sessions(BASIC_HISTORY, 1, 999)
        assert sc.projects_to == 0
        assert sc.avg_score_to == 0.0

    def test_to_dict(self):
        sc = SessionComparison(
            session_from=1, session_to=2,
            projects_from=10, projects_to=12,
            new_projects=["a/b"], avg_score_from=75.0,
            avg_score_to=76.0, avg_change=1.0,
            grade_distribution_from={"A": 5}, grade_distribution_to={"A": 6},
        )
        d = sc.to_dict()
        assert d["new_projects"] == ["a/b"]


# ---------------------------------------------------------------------------
# export_trends_json
# ---------------------------------------------------------------------------


class TestExportTrendsJson:
    def test_empty_history(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text("[]")
        result = export_trends_json(data_dir)
        assert result["sessions"] == []
        assert result["projects"] == {}

    def test_returns_correct_structure(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(json.dumps(BASIC_HISTORY))
        result = export_trends_json(data_dir)
        assert result["sessions"] == [1, 2]
        assert "owner/alpha" in result["projects"]
        assert len(result["summary"]) == 2

    def test_sparkline_data(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(json.dumps(BASIC_HISTORY))
        result = export_trends_json(data_dir)
        sparkline = result["projects"]["owner/alpha"]
        assert len(sparkline) == 2
        assert sparkline[0]["session"] == 1
        assert sparkline[0]["score"] == 85.0

    def test_writes_file(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(json.dumps(BASIC_HISTORY))
        out = tmp_path / "trends.json"
        export_trends_json(data_dir, output=out)
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert "sessions" in loaded

    def test_session_summaries(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(json.dumps(BASIC_HISTORY))
        result = export_trends_json(data_dir)
        s1 = result["summary"][0]
        assert s1["session"] == 1
        assert s1["project_count"] == 3
        assert s1["avg_score"] > 0

    def test_no_history_file(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        result = export_trends_json(data_dir)
        assert result == {"sessions": [], "projects": {}, "summary": {}}


# ---------------------------------------------------------------------------
# generate_movers_report
# ---------------------------------------------------------------------------


class TestGenerateMoversReport:
    def test_basic_report(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(json.dumps(BASIC_HISTORY))
        report = generate_movers_report(data_dir)
        assert report.total_projects == 3
        assert report.sessions_analyzed == [1, 2]

    def test_dedup_cleans_history(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(
            json.dumps(HISTORY_WITH_DUPLICATES)
        )
        report = generate_movers_report(data_dir)
        assert report.duplicates_removed == 2
        # Verify file was actually cleaned
        cleaned = json.loads((data_dir / "score_history.json").read_text())
        assert len(cleaned) == 4

    def test_dedup_skip(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(
            json.dumps(HISTORY_WITH_DUPLICATES)
        )
        report = generate_movers_report(data_dir, fix_duplicates=False)
        assert report.duplicates_removed == 0

    def test_includes_boundary_alerts(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(
            json.dumps(BOUNDARY_HISTORY)
        )
        report = generate_movers_report(data_dir)
        assert len(report.boundary_alerts) > 0

    def test_includes_new_entrants(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(
            json.dumps(HISTORY_WITH_NEW_ENTRANT)
        )
        report = generate_movers_report(data_dir)
        assert len(report.new_entrants) == 1

    def test_session_comparisons(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "score_history.json").write_text(json.dumps(BASIC_HISTORY))
        report = generate_movers_report(data_dir)
        assert len(report.session_comparisons) == 1
        sc = report.session_comparisons[0]
        assert sc.session_from == 1
        assert sc.session_to == 2


# ---------------------------------------------------------------------------
# MoversReport serialization
# ---------------------------------------------------------------------------


class TestMoversReportSerialization:
    def _sample_report(self) -> MoversReport:
        return MoversReport(
            sessions_analyzed=[1, 2],
            total_projects=3,
            boundary_alerts=[
                GradeBoundaryAlert(
                    project_slug="a/b", current_score=89.8, current_grade="A",
                    nearest_boundary=90, target_grade="A+", distance=-0.2,
                    direction="promotion",
                ),
            ],
            new_entrants=[
                NewEntrant(
                    project_slug="c/d", first_session=2,
                    score=70.0, grade="B", category="testing",
                ),
            ],
            session_comparisons=[
                SessionComparison(
                    session_from=1, session_to=2,
                    projects_from=2, projects_to=3,
                    new_projects=["c/d"],
                    avg_score_from=80.0, avg_score_to=78.0,
                    avg_change=-2.0,
                    grade_distribution_from={"A": 1, "B": 1},
                    grade_distribution_to={"A": 1, "B": 2},
                ),
            ],
            duplicates_removed=5,
        )

    def test_to_dict_structure(self):
        d = self._sample_report().to_dict()
        assert d["sessions_analyzed"] == [1, 2]
        assert d["total_projects"] == 3
        assert len(d["boundary_alerts"]) == 1
        assert len(d["new_entrants"]) == 1
        assert d["duplicates_removed"] == 5

    def test_to_json_valid(self):
        j = self._sample_report().to_json()
        parsed = json.loads(j)
        assert parsed["total_projects"] == 3

    def test_to_markdown_has_title(self):
        md = self._sample_report().to_markdown()
        assert "# Movers and Shakers Report" in md

    def test_to_markdown_has_promotion_section(self):
        md = self._sample_report().to_markdown()
        assert "Near Promotion" in md
        assert "a/b" in md

    def test_to_markdown_has_new_entrants(self):
        md = self._sample_report().to_markdown()
        assert "New Entrants" in md
        assert "c/d" in md

    def test_to_markdown_has_session_comparison(self):
        md = self._sample_report().to_markdown()
        assert "Session Comparisons" in md
        assert "Session 1 -> 2" in md

    def test_to_markdown_mentions_duplicates(self):
        md = self._sample_report().to_markdown()
        assert "5 duplicate" in md

    def test_empty_report_markdown(self):
        report = MoversReport(
            sessions_analyzed=[], total_projects=0,
            boundary_alerts=[], new_entrants=[],
            session_comparisons=[], duplicates_removed=0,
        )
        md = report.to_markdown()
        assert "Movers and Shakers" in md
        # Should not contain section headers for empty data
        assert "Near Promotion" not in md


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLI:
    def test_movers_subcommand_exists(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["movers"])
        assert args.command == "movers"

    def test_movers_format_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["movers", "--format", "json"])
        assert args.format == "json"

    def test_movers_write_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["movers", "--write"])
        assert args.write is True

    def test_movers_data_dir_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["movers", "--data-dir", "/tmp/test"])
        assert args.data_dir == "/tmp/test"


# ---------------------------------------------------------------------------
# Integration: against real data
# ---------------------------------------------------------------------------


class TestRealData:
    """Run movers against the actual score_history.json if available."""

    @pytest.fixture
    def data_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "data"

    def test_real_data_runs(self, data_dir):
        if not (data_dir / "score_history.json").exists():
            pytest.skip("score_history.json not found")
        report = generate_movers_report(data_dir, fix_duplicates=False)
        assert report.total_projects > 0
        assert isinstance(report.to_json(), str)
        assert isinstance(report.to_markdown(), str)

    def test_real_data_session_12_exists(self, data_dir):
        if not (data_dir / "score_history.json").exists():
            pytest.skip("score_history.json not found")
        history = json.loads((data_dir / "score_history.json").read_text())
        sessions = {e["session"] for e in history}
        assert 12 in sessions, "Session 12 snapshot should exist"

    def test_real_data_no_duplicates(self, data_dir):
        if not (data_dir / "score_history.json").exists():
            pytest.skip("score_history.json not found")
        history = json.loads((data_dir / "score_history.json").read_text())
        _, removed = dedup_history(history)
        assert removed == 0, f"Found {removed} duplicate entries in score_history.json"

    def test_real_data_has_trends_json(self):
        trends_path = Path(__file__).resolve().parent.parent / "website" / "data" / "trends.json"
        if not trends_path.exists():
            pytest.skip("trends.json not found")
        data = json.loads(trends_path.read_text())
        assert "sessions" in data
        assert "projects" in data
        assert len(data["projects"]) > 0
