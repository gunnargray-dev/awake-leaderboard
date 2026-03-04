"""Tests for src/trend_analyzer.py -- trend analysis from score history."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.trend_analyzer import (
    MA_WINDOW,
    MIN_SNAPSHOTS_FOR_TREND,
    STABILITY_THRESHOLD,
    CategoryTrend,
    ProjectTrend,
    TrendReport,
    _classify_direction,
    _compute_momentum,
    _compute_moving_average,
    _group_history_by_project,
    _slug_to_category,
    analyze_all_trends,
    analyze_category_trends,
    analyze_project_trend,
    categorize_trends,
    ensure_baseline_snapshots,
    generate_trend_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temp data directory."""
    return tmp_path / "data"


def _make_snapshot(slug, session, overall, grade="B"):
    """Helper to build a single snapshot dict."""
    return {
        "project_slug": slug,
        "session": session,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "scores": {
            "health": 80.0,
            "complexity": 70.0,
            "security": 75.0,
            "dead_code": 90.0,
            "coverage": 85.0,
            "overall": overall,
            "grade": grade,
        },
    }


def _write_history(data_dir, entries):
    """Write a score_history.json file."""
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "score_history.json").write_text(
        json.dumps(entries, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# _compute_moving_average
# ---------------------------------------------------------------------------


class TestComputeMovingAverage:
    def test_empty_list(self):
        assert _compute_moving_average([]) == 0.0

    def test_single_value(self):
        assert _compute_moving_average([75.0]) == 75.0

    def test_two_values(self):
        assert _compute_moving_average([70.0, 80.0]) == 75.0

    def test_exact_window(self):
        scores = [60.0, 70.0, 80.0]
        expected = round(sum(scores) / 3, 2)
        assert _compute_moving_average(scores, window=3) == expected

    def test_more_than_window(self):
        # Only the last MA_WINDOW values should be used
        scores = [50.0, 60.0, 70.0, 80.0, 90.0]
        expected = round((70.0 + 80.0 + 90.0) / 3, 2)
        assert _compute_moving_average(scores, window=3) == expected

    def test_custom_window(self):
        scores = [10.0, 20.0, 30.0, 40.0]
        assert _compute_moving_average(scores, window=2) == 35.0


# ---------------------------------------------------------------------------
# _compute_momentum
# ---------------------------------------------------------------------------


class TestComputeMomentum:
    def test_empty(self):
        assert _compute_momentum([]) == 0.0

    def test_single_value(self):
        assert _compute_momentum([80.0]) == 0.0

    def test_two_values_positive(self):
        assert _compute_momentum([70.0, 80.0]) == 10.0

    def test_two_values_negative(self):
        assert _compute_momentum([80.0, 70.0]) == -10.0

    def test_steady_increase(self):
        # +5 each step, 3 steps
        assert _compute_momentum([60.0, 65.0, 70.0, 75.0]) == 5.0

    def test_mixed_changes(self):
        # +10, -5 => avg = 2.5
        assert _compute_momentum([70.0, 80.0, 75.0]) == 2.5

    def test_no_change(self):
        assert _compute_momentum([80.0, 80.0, 80.0]) == 0.0


# ---------------------------------------------------------------------------
# _classify_direction
# ---------------------------------------------------------------------------


class TestClassifyDirection:
    def test_improving(self):
        assert _classify_direction(STABILITY_THRESHOLD + 0.1) == "improving"

    def test_declining(self):
        assert _classify_direction(-STABILITY_THRESHOLD - 0.1) == "declining"

    def test_stable_positive(self):
        assert _classify_direction(STABILITY_THRESHOLD - 0.1) == "stable"

    def test_stable_negative(self):
        assert _classify_direction(-STABILITY_THRESHOLD + 0.1) == "stable"

    def test_stable_zero(self):
        assert _classify_direction(0.0) == "stable"

    def test_boundary_positive(self):
        # Exactly at threshold => stable
        assert _classify_direction(STABILITY_THRESHOLD) == "stable"

    def test_boundary_negative(self):
        assert _classify_direction(-STABILITY_THRESHOLD) == "stable"


# ---------------------------------------------------------------------------
# analyze_project_trend
# ---------------------------------------------------------------------------


class TestAnalyzeProjectTrend:
    def test_basic_improving(self):
        snaps = [
            _make_snapshot("a/b", 1, 60.0, "C+"),
            _make_snapshot("a/b", 2, 70.0, "B"),
            _make_snapshot("a/b", 3, 80.0, "A-"),
        ]
        t = analyze_project_trend("a/b", snaps)
        assert t.project_slug == "a/b"
        assert t.snapshots == 3
        assert t.current_score == 80.0
        assert t.direction == "improving"
        assert t.momentum == 10.0
        assert t.current_grade == "A-"
        assert t.min_score == 60.0
        assert t.max_score == 80.0

    def test_declining(self):
        snaps = [
            _make_snapshot("x/y", 1, 90.0, "A+"),
            _make_snapshot("x/y", 2, 80.0, "A-"),
            _make_snapshot("x/y", 3, 70.0, "B"),
        ]
        t = analyze_project_trend("x/y", snaps)
        assert t.direction == "declining"
        assert t.momentum == -10.0

    def test_stable(self):
        snaps = [
            _make_snapshot("s/t", 1, 75.0, "B+"),
            _make_snapshot("s/t", 2, 75.5, "B+"),
            _make_snapshot("s/t", 3, 76.0, "B+"),
        ]
        t = analyze_project_trend("s/t", snaps)
        assert t.direction == "stable"

    def test_sessions_list(self):
        snaps = [
            _make_snapshot("a/b", 3, 60.0),
            _make_snapshot("a/b", 5, 70.0),
        ]
        t = analyze_project_trend("a/b", snaps)
        assert t.sessions == [3, 5]

    def test_scores_list(self):
        snaps = [
            _make_snapshot("a/b", 1, 60.0),
            _make_snapshot("a/b", 2, 70.0),
        ]
        t = analyze_project_trend("a/b", snaps)
        assert t.scores == [60.0, 70.0]

    def test_score_range(self):
        snaps = [
            _make_snapshot("a/b", 1, 50.0),
            _make_snapshot("a/b", 2, 90.0),
        ]
        t = analyze_project_trend("a/b", snaps)
        assert t.score_range == 40.0

    def test_to_dict(self):
        snaps = [_make_snapshot("a/b", 1, 80.0), _make_snapshot("a/b", 2, 85.0)]
        t = analyze_project_trend("a/b", snaps)
        d = t.to_dict()
        assert isinstance(d, dict)
        assert d["project_slug"] == "a/b"
        assert "momentum" in d


# ---------------------------------------------------------------------------
# _group_history_by_project
# ---------------------------------------------------------------------------


class TestGroupHistoryByProject:
    def test_empty(self):
        assert _group_history_by_project([]) == {}

    def test_single_project(self):
        history = [
            _make_snapshot("a/b", 2, 70.0),
            _make_snapshot("a/b", 1, 60.0),
        ]
        groups = _group_history_by_project(history)
        assert len(groups) == 1
        assert "a/b" in groups
        # Sorted by session
        assert groups["a/b"][0]["session"] == 1
        assert groups["a/b"][1]["session"] == 2

    def test_multiple_projects(self):
        history = [
            _make_snapshot("a/b", 1, 60.0),
            _make_snapshot("x/y", 1, 70.0),
            _make_snapshot("a/b", 2, 65.0),
        ]
        groups = _group_history_by_project(history)
        assert len(groups) == 2
        assert len(groups["a/b"]) == 2
        assert len(groups["x/y"]) == 1


# ---------------------------------------------------------------------------
# analyze_all_trends
# ---------------------------------------------------------------------------


class TestAnalyzeAllTrends:
    def test_empty_history(self, tmp_data_dir):
        _write_history(tmp_data_dir, [])
        result = analyze_all_trends(tmp_data_dir)
        assert result == []

    def test_no_history_file(self, tmp_data_dir):
        tmp_data_dir.mkdir(parents=True, exist_ok=True)
        result = analyze_all_trends(tmp_data_dir)
        assert result == []

    def test_single_snapshot_insufficient(self, tmp_data_dir):
        """One snapshot per project is below MIN_SNAPSHOTS_FOR_TREND."""
        _write_history(tmp_data_dir, [_make_snapshot("a/b", 1, 80.0)])
        result = analyze_all_trends(tmp_data_dir)
        assert result == []

    def test_two_snapshots(self, tmp_data_dir):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("a/b", 2, 80.0),
        ]
        _write_history(tmp_data_dir, history)
        result = analyze_all_trends(tmp_data_dir)
        assert len(result) == 1
        assert result[0].project_slug == "a/b"

    def test_sorted_by_momentum(self, tmp_data_dir):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("a/b", 2, 80.0),  # +10
            _make_snapshot("x/y", 1, 90.0),
            _make_snapshot("x/y", 2, 70.0),  # -20
        ]
        _write_history(tmp_data_dir, history)
        result = analyze_all_trends(tmp_data_dir)
        assert len(result) == 2
        # Best momentum first
        assert result[0].project_slug == "a/b"
        assert result[1].project_slug == "x/y"


# ---------------------------------------------------------------------------
# categorize_trends
# ---------------------------------------------------------------------------


class TestCategorizeTrends:
    def test_empty(self):
        improving, declining, stable = categorize_trends([])
        assert improving == []
        assert declining == []
        assert stable == []

    def test_all_three_categories(self):
        trends = [
            ProjectTrend("a/b", 3, [60, 70, 80], [1, 2, 3], 80.0, 70.0, "improving", 10.0, 60.0, 80.0, 20.0, "A-"),
            ProjectTrend("x/y", 3, [80, 70, 60], [1, 2, 3], 60.0, 70.0, "declining", -10.0, 60.0, 80.0, 20.0, "C+"),
            ProjectTrend("s/t", 3, [75, 75, 75], [1, 2, 3], 75.0, 75.0, "stable", 0.0, 75.0, 75.0, 0.0, "B+"),
        ]
        improving, declining, stable = categorize_trends(trends)
        assert len(improving) == 1
        assert improving[0].project_slug == "a/b"
        assert len(declining) == 1
        assert declining[0].project_slug == "x/y"
        assert len(stable) == 1
        assert stable[0].project_slug == "s/t"

    def test_improving_sorted_by_momentum_desc(self):
        trends = [
            ProjectTrend("slow", 2, [70, 73], [1, 2], 73.0, 71.5, "improving", 3.0, 70.0, 73.0, 3.0, "B"),
            ProjectTrend("fast", 2, [60, 80], [1, 2], 80.0, 70.0, "improving", 20.0, 60.0, 80.0, 20.0, "A-"),
        ]
        improving, _, _ = categorize_trends(trends)
        assert improving[0].project_slug == "fast"

    def test_declining_sorted_by_momentum_asc(self):
        trends = [
            ProjectTrend("mild", 2, [80, 78], [1, 2], 78.0, 79.0, "declining", -2.0, 78.0, 80.0, 2.0, "B+"),
            ProjectTrend("steep", 2, [90, 60], [1, 2], 60.0, 75.0, "declining", -30.0, 60.0, 90.0, 30.0, "C+"),
        ]
        _, declining, _ = categorize_trends(trends)
        assert declining[0].project_slug == "steep"


# ---------------------------------------------------------------------------
# analyze_category_trends
# ---------------------------------------------------------------------------


class TestAnalyzeCategoryTrends:
    def test_empty(self):
        result = analyze_category_trends([], {})
        assert result == []

    def test_single_category(self):
        trends = [
            ProjectTrend("a/b", 2, [70, 80], [1, 2], 80.0, 75.0, "improving", 10.0, 70.0, 80.0, 10.0, "A-"),
            ProjectTrend("c/d", 2, [60, 70], [1, 2], 70.0, 65.0, "improving", 10.0, 60.0, 70.0, 10.0, "B"),
        ]
        slug_cats = {"a/b": "web-framework", "c/d": "web-framework"}
        result = analyze_category_trends(trends, slug_cats)
        assert len(result) == 1
        assert result[0].category == "web-framework"
        assert result[0].project_count == 2
        assert result[0].avg_score == 75.0
        assert result[0].improving_count == 2

    def test_multiple_categories(self):
        trends = [
            ProjectTrend("a/b", 2, [70, 80], [1, 2], 80.0, 75.0, "improving", 10.0, 70.0, 80.0, 10.0, "A-"),
            ProjectTrend("x/y", 2, [90, 80], [1, 2], 80.0, 85.0, "declining", -10.0, 80.0, 90.0, 10.0, "A-"),
        ]
        slug_cats = {"a/b": "web-framework", "x/y": "testing"}
        result = analyze_category_trends(trends, slug_cats)
        assert len(result) == 2

    def test_unknown_category_defaults_to_other(self):
        trends = [
            ProjectTrend("unk/repo", 2, [70, 80], [1, 2], 80.0, 75.0, "improving", 10.0, 70.0, 80.0, 10.0, "A-"),
        ]
        result = analyze_category_trends(trends, {})
        assert result[0].category == "other"

    def test_sorted_by_momentum(self):
        trends = [
            ProjectTrend("a/b", 2, [70, 80], [1, 2], 80.0, 75.0, "improving", 10.0, 70.0, 80.0, 10.0, "A-"),
            ProjectTrend("x/y", 2, [90, 60], [1, 2], 60.0, 75.0, "declining", -30.0, 60.0, 90.0, 30.0, "C+"),
        ]
        slug_cats = {"a/b": "web-framework", "x/y": "testing"}
        result = analyze_category_trends(trends, slug_cats)
        # web-framework (+10) first, testing (-30) second
        assert result[0].category == "web-framework"
        assert result[1].category == "testing"


# ---------------------------------------------------------------------------
# CategoryTrend
# ---------------------------------------------------------------------------


class TestCategoryTrend:
    def test_to_dict(self):
        ct = CategoryTrend("web-framework", 5, 80.0, 2.5, "improving", 3, 1, 1)
        d = ct.to_dict()
        assert d["category"] == "web-framework"
        assert d["improving_count"] == 3


# ---------------------------------------------------------------------------
# TrendReport
# ---------------------------------------------------------------------------


class TestTrendReport:
    def _make_report(self):
        imp = [ProjectTrend("a/b", 3, [60, 70, 80], [1, 2, 3], 80.0, 70.0, "improving", 10.0, 60.0, 80.0, 20.0, "A-")]
        dec = [ProjectTrend("x/y", 3, [80, 70, 60], [1, 2, 3], 60.0, 70.0, "declining", -10.0, 60.0, 80.0, 20.0, "C+")]
        stb = [ProjectTrend("s/t", 3, [75, 75, 75], [1, 2, 3], 75.0, 75.0, "stable", 0.0, 75.0, 75.0, 0.0, "B+")]
        cat = [CategoryTrend("web-framework", 2, 70.0, 5.0, "improving", 1, 1, 0)]
        return TrendReport(
            total_projects=3,
            sessions_analyzed=[1, 2, 3],
            improving=imp,
            declining=dec,
            stable=stb,
            category_trends=cat,
            avg_score=71.7,
            avg_momentum=0.0,
        )

    def test_to_dict(self):
        r = self._make_report()
        d = r.to_dict()
        assert d["total_projects"] == 3
        assert len(d["improving"]) == 1
        assert len(d["declining"]) == 1
        assert len(d["stable"]) == 1
        assert len(d["category_trends"]) == 1

    def test_to_json(self):
        r = self._make_report()
        j = r.to_json()
        parsed = json.loads(j)
        assert parsed["total_projects"] == 3

    def test_to_markdown_has_sections(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "# Trend Analysis Report" in md
        assert "## Top Improvers" in md
        assert "## Top Decliners" in md
        assert "## Stable Projects" in md
        assert "## Category Trends" in md
        assert "a/b" in md
        assert "x/y" in md
        assert "s/t" in md

    def test_to_markdown_empty_sections(self):
        r = TrendReport(
            total_projects=0,
            sessions_analyzed=[],
            improving=[],
            declining=[],
            stable=[],
            category_trends=[],
            avg_score=0.0,
            avg_momentum=0.0,
        )
        md = r.to_markdown()
        assert "# Trend Analysis Report" in md
        assert "## Top Improvers" not in md

    def test_to_dict_rounds_values(self):
        r = TrendReport(
            total_projects=1,
            sessions_analyzed=[1],
            improving=[],
            declining=[],
            stable=[],
            category_trends=[],
            avg_score=72.333,
            avg_momentum=1.555,
        )
        d = r.to_dict()
        assert d["avg_score"] == 72.3
        assert d["avg_momentum"] == round(1.555, 2)


# ---------------------------------------------------------------------------
# generate_trend_report
# ---------------------------------------------------------------------------


class TestGenerateTrendReport:
    def test_empty_history(self, tmp_data_dir):
        _write_history(tmp_data_dir, [])
        r = generate_trend_report(tmp_data_dir)
        assert r.total_projects == 0
        assert r.improving == []
        assert r.declining == []

    def test_no_history_file(self, tmp_data_dir):
        tmp_data_dir.mkdir(parents=True, exist_ok=True)
        r = generate_trend_report(tmp_data_dir)
        assert r.total_projects == 0

    def test_with_trends(self, tmp_data_dir):
        history = [
            _make_snapshot("a/b", 1, 60.0, "C+"),
            _make_snapshot("a/b", 2, 70.0, "B"),
            _make_snapshot("a/b", 3, 80.0, "A-"),
            _make_snapshot("x/y", 1, 90.0, "A+"),
            _make_snapshot("x/y", 2, 80.0, "A-"),
            _make_snapshot("x/y", 3, 70.0, "B"),
        ]
        _write_history(tmp_data_dir, history)
        r = generate_trend_report(tmp_data_dir)
        assert r.total_projects == 2
        assert r.sessions_analyzed == [1, 2, 3]
        assert len(r.improving) == 1
        assert len(r.declining) == 1

    def test_top_limits_results(self, tmp_data_dir):
        history = []
        for i in range(10):
            slug = f"owner/repo{i}"
            history.append(_make_snapshot(slug, 1, 60.0 + i))
            history.append(_make_snapshot(slug, 2, 70.0 + i))
        _write_history(tmp_data_dir, history)
        r = generate_trend_report(tmp_data_dir, top=3)
        # All have +10 momentum => all improving
        assert len(r.improving) <= 3

    def test_category_filter(self, tmp_data_dir):
        history = [
            _make_snapshot("pallets/flask", 1, 70.0),
            _make_snapshot("pallets/flask", 2, 80.0),
            _make_snapshot("psf/requests", 1, 75.0),
            _make_snapshot("psf/requests", 2, 85.0),
        ]
        _write_history(tmp_data_dir, history)
        # flask is web-framework, requests is http-client
        r = generate_trend_report(tmp_data_dir, category="web-framework")
        slugs = [t.project_slug for t in r.improving + r.declining + r.stable]
        assert "pallets/flask" in slugs
        assert "psf/requests" not in slugs


# ---------------------------------------------------------------------------
# ensure_baseline_snapshots
# ---------------------------------------------------------------------------


class TestEnsureBaselineSnapshots:
    def test_creates_snapshots_when_empty(self, tmp_data_dir):
        created = ensure_baseline_snapshots(tmp_data_dir, sessions=[1, 2])
        assert created == 2
        history = json.loads(
            (tmp_data_dir / "score_history.json").read_text()
        )
        sessions = sorted({e["session"] for e in history})
        assert sessions == [1, 2]

    def test_skips_existing_sessions(self, tmp_data_dir):
        # Create session 1
        ensure_baseline_snapshots(tmp_data_dir, sessions=[1])
        # Now request 1 and 2 -- only 2 should be created
        created = ensure_baseline_snapshots(tmp_data_dir, sessions=[1, 2])
        assert created == 1

    def test_no_op_when_all_exist(self, tmp_data_dir):
        ensure_baseline_snapshots(tmp_data_dir, sessions=[1, 2])
        created = ensure_baseline_snapshots(tmp_data_dir, sessions=[1, 2])
        assert created == 0

    def test_custom_sessions(self, tmp_data_dir):
        created = ensure_baseline_snapshots(tmp_data_dir, sessions=[5, 10, 15])
        assert created == 3


# ---------------------------------------------------------------------------
# _slug_to_category
# ---------------------------------------------------------------------------


class TestSlugToCategory:
    def test_returns_dict(self):
        cats = _slug_to_category()
        assert isinstance(cats, dict)
        assert len(cats) > 0

    def test_known_project(self):
        cats = _slug_to_category()
        assert "pallets/flask" in cats


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLIScoreTrends:
    def test_subparser_exists(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["score-trends"])
        assert args.command == "score-trends"

    def test_format_default(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["score-trends"])
        assert args.format == "markdown"

    def test_format_json(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["score-trends", "--format", "json"])
        assert args.format == "json"

    def test_top_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["score-trends", "--top", "5"])
        assert args.top == 5

    def test_category_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["score-trends", "--category", "web-framework"])
        assert args.category == "web-framework"

    def test_write_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["score-trends", "--write"])
        assert args.write is True

    def test_data_dir_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["score-trends", "--data-dir", "/tmp/mydata"])
        assert args.data_dir == "/tmp/mydata"

    def test_cmd_score_trends_markdown(self, tmp_data_dir, capsys):
        from src.cli import cmd_score_trends
        # Pre-populate history
        history = [
            _make_snapshot("a/b", 1, 60.0),
            _make_snapshot("a/b", 2, 70.0),
        ]
        _write_history(tmp_data_dir, history)

        args = argparse.Namespace(
            data_dir=str(tmp_data_dir),
            top=10,
            category="",
            format="markdown",
            write=False,
        )
        cmd_score_trends(args)
        out = capsys.readouterr().out
        assert "Trend Analysis Report" in out

    def test_cmd_score_trends_json(self, tmp_data_dir, capsys):
        from src.cli import cmd_score_trends
        history = [
            _make_snapshot("a/b", 1, 60.0),
            _make_snapshot("a/b", 2, 70.0),
        ]
        _write_history(tmp_data_dir, history)

        args = argparse.Namespace(
            data_dir=str(tmp_data_dir),
            top=10,
            category="",
            format="json",
            write=False,
        )
        cmd_score_trends(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "total_projects" in parsed

    def test_cmd_score_trends_write(self, tmp_data_dir, capsys):
        from src.cli import cmd_score_trends
        history = [
            _make_snapshot("a/b", 1, 60.0),
            _make_snapshot("a/b", 2, 70.0),
        ]
        _write_history(tmp_data_dir, history)

        args = argparse.Namespace(
            data_dir=str(tmp_data_dir),
            top=10,
            category="",
            format="markdown",
            write=True,
        )
        cmd_score_trends(args)
        assert (tmp_data_dir / "trend_report.md").exists()
        assert (tmp_data_dir / "trend_report.json").exists()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_project_with_missing_overall(self):
        snap = {
            "project_slug": "a/b",
            "session": 1,
            "timestamp": "2026-01-01",
            "scores": {"grade": "F"},  # no overall
        }
        snap2 = {
            "project_slug": "a/b",
            "session": 2,
            "timestamp": "2026-01-01",
            "scores": {"overall": 50.0, "grade": "C-"},
        }
        t = analyze_project_trend("a/b", [snap, snap2])
        assert t.scores[0] == 0.0
        assert t.scores[1] == 50.0

    def test_project_with_missing_grade(self):
        snaps = [
            {"project_slug": "a/b", "session": 1, "timestamp": "x",
             "scores": {"overall": 60.0}},
            {"project_slug": "a/b", "session": 2, "timestamp": "x",
             "scores": {"overall": 70.0}},
        ]
        t = analyze_project_trend("a/b", snaps)
        assert t.current_grade == "F"  # default

    def test_many_sessions(self, tmp_data_dir):
        """Trend works with many sessions."""
        history = []
        for s in range(1, 21):
            history.append(_make_snapshot("a/b", s, 50.0 + s))
        _write_history(tmp_data_dir, history)
        result = analyze_all_trends(tmp_data_dir)
        assert len(result) == 1
        assert result[0].snapshots == 20

    def test_negative_momentum_with_recovery(self):
        """Drop then recovery averages out."""
        snaps = [
            _make_snapshot("a/b", 1, 80.0),
            _make_snapshot("a/b", 2, 60.0),  # -20
            _make_snapshot("a/b", 3, 80.0),  # +20
        ]
        t = analyze_project_trend("a/b", snaps)
        assert t.momentum == 0.0
        assert t.direction == "stable"


import argparse
