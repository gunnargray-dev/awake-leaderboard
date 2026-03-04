"""Tests for src.score_history -- score history tracking and refresh pipeline.

Covers:
- ScoreSnapshot, ScoreDelta, MoverReport data structures
- History file I/O (load/save)
- Snapshot recording (record_snapshot)
- Delta computation (compute_deltas)
- Mover identification (find_movers)
- Session utilities (get_latest_sessions, get_session_summary)
- Full refresh pipeline (refresh_scores)
- CLI integration (refresh-scores subcommand)
- Edge cases: empty history, single session, no movers
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.score_history import (
    ScoreSnapshot,
    ScoreDelta,
    MoverReport,
    load_history,
    _save_history,
    record_snapshot,
    compute_deltas,
    find_movers,
    get_latest_sessions,
    get_session_summary,
    refresh_scores,
    HISTORY_FILENAME,
)
from src.discovery import _SEED_PROJECTS
from src.generate_leaderboard import generate_scores


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_snapshot(slug: str, session: int, overall: float, grade: str = "B") -> dict:
    """Create a minimal snapshot dict for testing."""
    return {
        "project_slug": slug,
        "session": session,
        "timestamp": "2026-03-04T00:00:00+00:00",
        "scores": {
            "health": 80.0,
            "complexity": 75.0,
            "security": 85.0,
            "dead_code": 90.0,
            "coverage": 70.0,
            "overall": overall,
            "grade": grade,
        },
    }


def _make_history_pair(slug: str, old_overall: float, new_overall: float) -> list[dict]:
    """Create a two-session history for one project."""
    return [
        _make_snapshot(slug, 1, old_overall, "B"),
        _make_snapshot(slug, 2, new_overall, "B+"),
    ]


# ---------------------------------------------------------------------------
# ScoreSnapshot tests
# ---------------------------------------------------------------------------


class TestScoreSnapshot:
    def test_to_dict(self):
        snap = ScoreSnapshot(
            project_slug="pallets/flask",
            session=1,
            timestamp="2026-03-04T00:00:00Z",
            scores={"overall": 82.5, "grade": "A-"},
        )
        d = snap.to_dict()
        assert d["project_slug"] == "pallets/flask"
        assert d["session"] == 1
        assert d["scores"]["overall"] == 82.5

    def test_fields(self):
        snap = ScoreSnapshot("a/b", 2, "ts", {"overall": 50.0})
        assert snap.project_slug == "a/b"
        assert snap.session == 2


# ---------------------------------------------------------------------------
# ScoreDelta tests
# ---------------------------------------------------------------------------


class TestScoreDelta:
    def test_to_dict(self):
        delta = ScoreDelta(
            project_slug="pallets/flask",
            session_from=1,
            session_to=2,
            previous_overall=80.0,
            current_overall=85.0,
            overall_change=5.0,
            dimension_changes={"health": 2.0, "security": 3.0},
            previous_grade="A-",
            current_grade="A",
        )
        d = delta.to_dict()
        assert d["overall_change"] == 5.0
        assert d["dimension_changes"]["health"] == 2.0


# ---------------------------------------------------------------------------
# MoverReport tests
# ---------------------------------------------------------------------------


class TestMoverReport:
    def _sample_report(self) -> MoverReport:
        improver = ScoreDelta("a/b", 1, 2, 70.0, 80.0, 10.0, {}, "B", "A-")
        decliner = ScoreDelta("c/d", 1, 2, 85.0, 75.0, -10.0, {}, "A", "B+")
        return MoverReport(
            session_from=1,
            session_to=2,
            improvers=[improver],
            decliners=[decliner],
            total_projects=10,
            avg_change=0.5,
        )

    def test_to_dict(self):
        report = self._sample_report()
        d = report.to_dict()
        assert d["session_from"] == 1
        assert d["session_to"] == 2
        assert d["total_projects"] == 10
        assert len(d["improvers"]) == 1
        assert len(d["decliners"]) == 1

    def test_to_json_valid(self):
        report = self._sample_report()
        parsed = json.loads(report.to_json())
        assert parsed["total_projects"] == 10

    def test_to_text_has_headers(self):
        report = self._sample_report()
        text = report.to_text()
        assert "SCORE REFRESH" in text
        assert "TOP IMPROVERS" in text
        assert "TOP DECLINERS" in text

    def test_to_text_shows_projects(self):
        report = self._sample_report()
        text = report.to_text()
        assert "a/b" in text
        assert "c/d" in text

    def test_empty_report_text(self):
        report = MoverReport(1, 2, [], [], 0, 0.0)
        text = report.to_text()
        assert "SCORE REFRESH" in text
        assert "TOP IMPROVERS" not in text


# ---------------------------------------------------------------------------
# History file I/O
# ---------------------------------------------------------------------------


class TestHistoryIO:
    def test_load_empty_dir(self, tmp_path):
        result = load_history(tmp_path)
        assert result == []

    def test_load_empty_file(self, tmp_path):
        (tmp_path / HISTORY_FILENAME).write_text("")
        result = load_history(tmp_path)
        assert result == []

    def test_save_and_load_roundtrip(self, tmp_path):
        data = [_make_snapshot("a/b", 1, 80.0)]
        _save_history(tmp_path, data)
        loaded = load_history(tmp_path)
        assert len(loaded) == 1
        assert loaded[0]["project_slug"] == "a/b"

    def test_save_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        _save_history(nested, [_make_snapshot("x/y", 1, 50.0)])
        assert (nested / HISTORY_FILENAME).exists()

    def test_load_preserves_all_fields(self, tmp_path):
        snap = _make_snapshot("test/repo", 5, 77.3, "B+")
        _save_history(tmp_path, [snap])
        loaded = load_history(tmp_path)
        assert loaded[0]["scores"]["grade"] == "B+"
        assert loaded[0]["session"] == 5


# ---------------------------------------------------------------------------
# record_snapshot
# ---------------------------------------------------------------------------


class TestRecordSnapshot:
    def test_records_all_seed_projects(self, tmp_path):
        snaps = record_snapshot(tmp_path, session=1)
        assert len(snaps) == len(_SEED_PROJECTS)

    def test_creates_history_file(self, tmp_path):
        record_snapshot(tmp_path, session=1)
        assert (tmp_path / HISTORY_FILENAME).exists()

    def test_scores_match_generate_scores(self, tmp_path):
        snaps = record_snapshot(tmp_path, session=1)
        for snap in snaps:
            owner, repo = snap.project_slug.split("/")
            expected = generate_scores(owner, repo)
            assert snap.scores["overall"] == expected["overall"]
            assert snap.scores["grade"] == expected["grade"]

    def test_appends_to_existing_history(self, tmp_path):
        record_snapshot(tmp_path, session=1)
        record_snapshot(tmp_path, session=2)
        history = load_history(tmp_path)
        assert len(history) == 2 * len(_SEED_PROJECTS)

    def test_session_number_stored(self, tmp_path):
        snaps = record_snapshot(tmp_path, session=42)
        for snap in snaps:
            assert snap.session == 42

    def test_timestamp_is_set(self, tmp_path):
        snaps = record_snapshot(tmp_path, session=1)
        for snap in snaps:
            assert len(snap.timestamp) > 0


# ---------------------------------------------------------------------------
# compute_deltas
# ---------------------------------------------------------------------------


class TestComputeDeltas:
    def test_basic_delta(self):
        history = _make_history_pair("a/b", 70.0, 80.0)
        deltas = compute_deltas(history, 1, 2)
        assert len(deltas) == 1
        assert deltas[0].overall_change == 10.0

    def test_negative_delta(self):
        history = _make_history_pair("a/b", 90.0, 80.0)
        deltas = compute_deltas(history, 1, 2)
        assert deltas[0].overall_change == -10.0

    def test_zero_delta(self):
        history = _make_history_pair("a/b", 75.0, 75.0)
        deltas = compute_deltas(history, 1, 2)
        assert deltas[0].overall_change == 0.0

    def test_only_common_projects(self):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("c/d", 1, 80.0),
            _make_snapshot("a/b", 2, 75.0),
            # c/d not in session 2
        ]
        deltas = compute_deltas(history, 1, 2)
        assert len(deltas) == 1
        assert deltas[0].project_slug == "a/b"

    def test_multiple_projects(self):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("c/d", 1, 80.0),
            _make_snapshot("a/b", 2, 75.0),
            _make_snapshot("c/d", 2, 85.0),
        ]
        deltas = compute_deltas(history, 1, 2)
        assert len(deltas) == 2

    def test_dimension_changes_computed(self):
        s1 = _make_snapshot("a/b", 1, 70.0)
        s1["scores"]["health"] = 80.0
        s2 = _make_snapshot("a/b", 2, 75.0)
        s2["scores"]["health"] = 85.0
        deltas = compute_deltas([s1, s2], 1, 2)
        assert deltas[0].dimension_changes["health"] == 5.0

    def test_empty_history(self):
        deltas = compute_deltas([], 1, 2)
        assert deltas == []

    def test_no_common_sessions(self):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("c/d", 2, 80.0),
        ]
        deltas = compute_deltas(history, 1, 2)
        assert deltas == []

    def test_grades_captured(self):
        history = [
            _make_snapshot("a/b", 1, 70.0, "B"),
            _make_snapshot("a/b", 2, 85.0, "A"),
        ]
        deltas = compute_deltas(history, 1, 2)
        assert deltas[0].previous_grade == "B"
        assert deltas[0].current_grade == "A"


# ---------------------------------------------------------------------------
# find_movers
# ---------------------------------------------------------------------------


class TestFindMovers:
    def test_identifies_improvers(self):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("a/b", 2, 80.0),
        ]
        report = find_movers(history, 1, 2)
        assert len(report.improvers) == 1
        assert report.improvers[0].project_slug == "a/b"
        assert report.decliners == []

    def test_identifies_decliners(self):
        history = [
            _make_snapshot("a/b", 1, 90.0),
            _make_snapshot("a/b", 2, 80.0),
        ]
        report = find_movers(history, 1, 2)
        assert report.improvers == []
        assert len(report.decliners) == 1

    def test_top_n_limit(self):
        history = []
        for i in range(10):
            history.append(_make_snapshot(f"o/r{i}", 1, 50.0 + i))
            history.append(_make_snapshot(f"o/r{i}", 2, 60.0 + i))
        report = find_movers(history, 1, 2, top=3)
        assert len(report.improvers) <= 3

    def test_empty_history(self):
        report = find_movers([], 1, 2)
        assert report.total_projects == 0
        assert report.improvers == []
        assert report.decliners == []

    def test_no_change(self):
        history = _make_history_pair("a/b", 75.0, 75.0)
        report = find_movers(history, 1, 2)
        assert report.improvers == []
        assert report.decliners == []
        assert report.total_projects == 1

    def test_avg_change_computed(self):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("c/d", 1, 80.0),
            _make_snapshot("a/b", 2, 80.0),  # +10
            _make_snapshot("c/d", 2, 78.0),  # -2
        ]
        report = find_movers(history, 1, 2)
        assert report.avg_change == pytest.approx(4.0, abs=0.01)

    def test_mixed_movers(self):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("c/d", 1, 90.0),
            _make_snapshot("a/b", 2, 85.0),  # +15 improver
            _make_snapshot("c/d", 2, 75.0),  # -15 decliner
        ]
        report = find_movers(history, 1, 2)
        assert len(report.improvers) == 1
        assert len(report.decliners) == 1
        assert report.improvers[0].project_slug == "a/b"
        assert report.decliners[0].project_slug == "c/d"


# ---------------------------------------------------------------------------
# get_latest_sessions
# ---------------------------------------------------------------------------


class TestGetLatestSessions:
    def test_returns_last_n(self):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("a/b", 2, 75.0),
            _make_snapshot("a/b", 3, 80.0),
        ]
        result = get_latest_sessions(history, n=2)
        assert result == [2, 3]

    def test_returns_all_if_fewer(self):
        history = [_make_snapshot("a/b", 5, 70.0)]
        result = get_latest_sessions(history, n=3)
        assert result == [5]

    def test_deduplicates_sessions(self):
        history = [
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("c/d", 1, 80.0),
            _make_snapshot("a/b", 2, 75.0),
            _make_snapshot("c/d", 2, 85.0),
        ]
        result = get_latest_sessions(history, n=2)
        assert result == [1, 2]

    def test_empty_history(self):
        assert get_latest_sessions([], n=2) == []

    def test_sorted_ascending(self):
        history = [
            _make_snapshot("a/b", 3, 70.0),
            _make_snapshot("a/b", 1, 70.0),
            _make_snapshot("a/b", 5, 70.0),
        ]
        result = get_latest_sessions(history, n=3)
        assert result == [1, 3, 5]


# ---------------------------------------------------------------------------
# get_session_summary
# ---------------------------------------------------------------------------


class TestGetSessionSummary:
    def test_basic_summary(self):
        history = [
            _make_snapshot("a/b", 1, 70.0, "B"),
            _make_snapshot("c/d", 1, 90.0, "A+"),
        ]
        summary = get_session_summary(history, 1)
        assert summary["session"] == 1
        assert summary["projects"] == 2
        assert summary["avg_score"] == 80.0
        assert summary["min_score"] == 70.0
        assert summary["max_score"] == 90.0

    def test_empty_session(self):
        summary = get_session_summary([], 1)
        assert summary["projects"] == 0

    def test_grade_distribution(self):
        history = [
            _make_snapshot("a/b", 1, 70.0, "B"),
            _make_snapshot("c/d", 1, 90.0, "A+"),
            _make_snapshot("e/f", 1, 72.0, "B"),
        ]
        summary = get_session_summary(history, 1)
        assert "B" in summary["grade_distribution"]
        assert summary["grade_distribution"]["B"] == 2


# ---------------------------------------------------------------------------
# refresh_scores (full pipeline)
# ---------------------------------------------------------------------------


class TestRefreshScores:
    def test_first_snapshot(self, tmp_path):
        report = refresh_scores(tmp_path, session=1)
        assert report.total_projects == len(_SEED_PROJECTS)
        assert report.improvers == []
        assert report.decliners == []

    def test_second_snapshot_has_deltas(self, tmp_path):
        refresh_scores(tmp_path, session=1)
        report = refresh_scores(tmp_path, session=2)
        assert report.total_projects == len(_SEED_PROJECTS)
        assert report.session_from == 1
        assert report.session_to == 2

    def test_history_file_created(self, tmp_path):
        refresh_scores(tmp_path, session=1)
        assert (tmp_path / HISTORY_FILENAME).exists()

    def test_history_grows(self, tmp_path):
        refresh_scores(tmp_path, session=1)
        h1 = load_history(tmp_path)
        refresh_scores(tmp_path, session=2)
        h2 = load_history(tmp_path)
        assert len(h2) == 2 * len(h1)

    def test_top_parameter(self, tmp_path):
        refresh_scores(tmp_path, session=1)
        report = refresh_scores(tmp_path, session=2, top=3)
        assert len(report.improvers) <= 3
        assert len(report.decliners) <= 3


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLI:
    def test_refresh_scores_subcommand_exists(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["refresh-scores", "--session", "5"])
        assert args.session == 5
        assert args.command == "refresh-scores"

    def test_refresh_scores_defaults(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["refresh-scores"])
        assert args.session == 1
        assert args.top == 5
        assert args.data_dir == "data"

    def test_refresh_scores_top_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["refresh-scores", "--top", "10"])
        assert args.top == 10

    def test_refresh_scores_data_dir_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["refresh-scores", "--data-dir", "/tmp/test"])
        assert args.data_dir == "/tmp/test"

    def test_refresh_scores_json_flag(self):
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["refresh-scores", "--json"])
        assert args.json is True

    def test_refresh_scores_in_commands(self):
        from src.cli import main
        # Should not raise when parsing
        from src.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["refresh-scores", "--session", "1"])
        assert hasattr(args, "session")


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_snapshots_deterministic(self, tmp_path):
        dir1 = tmp_path / "a"
        dir2 = tmp_path / "b"
        snaps1 = record_snapshot(dir1, session=1)
        snaps2 = record_snapshot(dir2, session=1)
        for s1, s2 in zip(snaps1, snaps2):
            assert s1.project_slug == s2.project_slug
            assert s1.scores["overall"] == s2.scores["overall"]

    def test_deltas_deterministic_across_runs(self, tmp_path):
        dir1 = tmp_path / "a"
        dir2 = tmp_path / "b"
        for d in (dir1, dir2):
            record_snapshot(d, session=1)
            record_snapshot(d, session=2)
        h1 = load_history(dir1)
        h2 = load_history(dir2)
        d1 = compute_deltas(h1, 1, 2)
        d2 = compute_deltas(h2, 1, 2)
        for a, b in zip(d1, d2):
            assert a.overall_change == b.overall_change


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_nonexistent_session_deltas(self):
        history = [_make_snapshot("a/b", 1, 70.0)]
        deltas = compute_deltas(history, 1, 99)
        assert deltas == []

    def test_same_session_deltas(self):
        history = [_make_snapshot("a/b", 1, 70.0)]
        deltas = compute_deltas(history, 1, 1)
        assert len(deltas) == 1
        assert deltas[0].overall_change == 0.0

    def test_movers_with_all_same_scores(self):
        history = [
            _make_snapshot("a/b", 1, 80.0),
            _make_snapshot("c/d", 1, 80.0),
            _make_snapshot("a/b", 2, 80.0),
            _make_snapshot("c/d", 2, 80.0),
        ]
        report = find_movers(history, 1, 2)
        assert report.improvers == []
        assert report.decliners == []
        assert report.avg_change == 0.0

    def test_single_project_history(self, tmp_path):
        """Refresh with only history for one project still works."""
        history = _make_history_pair("solo/project", 70.0, 85.0)
        _save_history(tmp_path, history)
        report = find_movers(load_history(tmp_path), 1, 2)
        assert report.total_projects == 1
        assert report.improvers[0].overall_change == 15.0
