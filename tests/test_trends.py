"""Tests for src/trends.py -- trend tracking and score history analysis."""

from __future__ import annotations

import pytest

from src.models import init_db
from src.trends import (
    get_score_delta,
    get_rank_history,
    get_movers,
    get_trend_summary,
    get_weekly_aggregation,
    get_session_leaderboard_delta,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    return conn


def _insert_project(conn, owner, repo, stars=100, category="web"):
    conn.execute(
        "INSERT OR IGNORE INTO projects (owner, repo, url, stars, category) VALUES (?,?,?,?,?)",
        (owner, repo, f"https://github.com/{owner}/{repo}", stars, category),
    )
    conn.commit()


def _insert_run(conn, owner, repo, session, score, grade="B", analyzed_at="2024-01-01T00:00:00"):
    conn.execute(
        """INSERT INTO analysis_runs
           (owner, repo, session, overall_score, health_score, complexity_score,
            security_score, dead_code_pct, grade, analyzed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (owner, repo, session, score, score, score, score, 5.0, grade, analyzed_at),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# get_score_delta
# ---------------------------------------------------------------------------


class TestGetScoreDelta:
    def test_no_runs_returns_zeros(self, db):
        result = get_score_delta(db, "acme", "pkg")
        assert result["current_score"] == 0.0
        assert result["previous_score"] == 0.0
        assert result["score_change"] == 0.0
        assert result["current_grade"] == "F"

    def test_single_run_current_equals_previous(self, db):
        _insert_run(db, "acme", "pkg", session=1, score=70.0, grade="B")
        result = get_score_delta(db, "acme", "pkg")
        assert result["current_score"] == 70.0
        assert result["previous_score"] == 70.0
        assert result["score_change"] == 0.0

    def test_two_runs_correct_delta(self, db):
        _insert_run(db, "acme", "pkg", session=1, score=60.0, grade="C+")
        _insert_run(db, "acme", "pkg", session=2, score=75.0, grade="B+")
        result = get_score_delta(db, "acme", "pkg")
        assert result["current_score"] == 75.0
        assert result["previous_score"] == 60.0
        assert result["score_change"] == 15.0

    def test_sessions_window(self, db):
        for i in range(1, 8):
            _insert_run(db, "acme", "pkg", session=i, score=float(i * 10))
        result = get_score_delta(db, "acme", "pkg", sessions=3)
        # Latest=7 (score=70), 3 sessions back = session 4 (score=40)
        assert result["current_score"] == 70.0
        assert result["previous_score"] == 40.0
        assert result["score_change"] == 30.0

    def test_owner_repo_in_result(self, db):
        _insert_run(db, "org", "repo", session=1, score=50.0)
        result = get_score_delta(db, "org", "repo")
        assert result["owner"] == "org"
        assert result["repo"] == "repo"

    def test_null_score_treated_as_zero(self, db):
        conn = db
        conn.execute(
            """INSERT INTO analysis_runs (owner, repo, session, overall_score, grade, analyzed_at)
               VALUES (?,?,?,?,?,?)""",
            ("acme", "pkg", 1, None, "F", "2024-01-01"),
        )
        conn.commit()
        result = get_score_delta(conn, "acme", "pkg")
        assert result["current_score"] == 0.0


# ---------------------------------------------------------------------------
# get_rank_history
# ---------------------------------------------------------------------------


class TestGetRankHistory:
    def test_empty_session(self, db):
        assert get_rank_history(db, 99) == []

    def test_ranks_assigned_correctly(self, db):
        _insert_project(db, "acme", "alpha")
        _insert_project(db, "acme", "beta")
        _insert_run(db, "acme", "alpha", session=1, score=80.0)
        _insert_run(db, "acme", "beta", session=1, score=90.0)
        ranks = get_rank_history(db, 1)
        assert len(ranks) == 2
        assert ranks[0]["repo"] == "beta"
        assert ranks[0]["rank"] == 1
        assert ranks[1]["repo"] == "alpha"
        assert ranks[1]["rank"] == 2

    def test_result_includes_stars_category(self, db):
        _insert_project(db, "org", "repo", stars=500, category="ml")
        _insert_run(db, "org", "repo", session=2, score=75.0)
        ranks = get_rank_history(db, 2)
        assert ranks[0]["stars"] == 500
        assert ranks[0]["category"] == "ml"


# ---------------------------------------------------------------------------
# get_movers
# ---------------------------------------------------------------------------


class TestGetMovers:
    def test_no_projects(self, db):
        result = get_movers(db)
        assert result["risers"] == []
        assert result["fallers"] == []

    def test_single_run_project_excluded(self, db):
        _insert_project(db, "org", "single")
        _insert_run(db, "org", "single", session=1, score=70.0)
        result = get_movers(db)
        assert result["risers"] == []
        assert result["fallers"] == []

    def test_two_run_project_included(self, db):
        _insert_project(db, "org", "mover")
        _insert_run(db, "org", "mover", session=1, score=60.0)
        _insert_run(db, "org", "mover", session=2, score=80.0)
        result = get_movers(db)
        assert len(result["risers"]) == 1
        assert result["risers"][0]["score_change"] == 20.0

    def test_sessions_window_key(self, db):
        result = get_movers(db, sessions=7)
        assert result["sessions_window"] == 7

    def test_risers_sorted_desc_fallers_sorted_desc_change(self, db):
        for i, (score_a, score_b) in enumerate([(50, 80), (60, 75), (70, 65)], 1):
            _insert_project(db, "org", f"proj{i}")
            _insert_run(db, "org", f"proj{i}", session=1, score=float(score_a))
            _insert_run(db, "org", f"proj{i}", session=2, score=float(score_b))
        result = get_movers(db)
        # proj1 +30, proj2 +15 → risers
        assert result["risers"][0]["score_change"] == 30.0
        assert result["risers"][1]["score_change"] == 15.0
        # proj3 -5 → faller
        assert result["fallers"][0]["score_change"] == -5.0

    def test_limit_respected(self, db):
        for i in range(1, 6):
            _insert_project(db, "org", f"p{i}")
            _insert_run(db, "org", f"p{i}", session=1, score=50.0)
            _insert_run(db, "org", f"p{i}", session=2, score=50.0 + i * 5)
        result = get_movers(db, limit=3)
        assert len(result["risers"]) <= 3


# ---------------------------------------------------------------------------
# get_trend_summary
# ---------------------------------------------------------------------------


class TestGetTrendSummary:
    def test_no_history(self, db):
        result = get_trend_summary(db, "x", "y")
        assert result["history"] == []
        assert result["stats"] == {}
        assert result["delta"] == {}

    def test_full_summary(self, db):
        for s, score in [(1, 60.0), (2, 70.0), (3, 80.0)]:
            _insert_run(db, "org", "repo", session=s, score=score)
        result = get_trend_summary(db, "org", "repo")
        assert result["owner"] == "org"
        assert result["repo"] == "repo"
        assert len(result["history"]) == 3
        stats = result["stats"]
        assert stats["sessions_analyzed"] == 3
        assert stats["min_score"] == 60.0
        assert stats["max_score"] == 80.0
        assert stats["avg_score"] == 70.0
        assert stats["first_session"] == 1
        assert stats["latest_session"] == 3

    def test_history_ordered_asc(self, db):
        for s in [3, 1, 2]:
            _insert_run(db, "org", "repo", session=s, score=float(s * 10))
        result = get_trend_summary(db, "org", "repo")
        sessions = [h["session"] for h in result["history"]]
        assert sessions == sorted(sessions)


# ---------------------------------------------------------------------------
# get_weekly_aggregation
# ---------------------------------------------------------------------------


class TestGetWeeklyAggregation:
    def test_empty(self, db):
        assert get_weekly_aggregation(db, "x", "y") == []

    def test_aggregates_by_week(self, db):
        # Two runs same week
        _insert_run(db, "org", "repo", session=1, score=60.0, analyzed_at="2024-01-08T10:00:00")
        _insert_run(db, "org", "repo", session=2, score=80.0, analyzed_at="2024-01-10T10:00:00")
        result = get_weekly_aggregation(db, "org", "repo", weeks=4)
        assert len(result) >= 1
        week_entry = result[0]
        assert week_entry["avg_score"] == 70.0
        assert week_entry["run_count"] == 2

    def test_weeks_limit_respected(self, db):
        for i in range(1, 10):
            # spread across different weeks
            _insert_run(
                db, "org", "repo", session=i, score=float(i * 10),
                analyzed_at=f"2024-0{i}-15T00:00:00" if i <= 9 else f"2024-10-15T00:00:00",
            )
        result = get_weekly_aggregation(db, "org", "repo", weeks=3)
        assert len(result) <= 3

    def test_no_empty_timestamp_rows(self, db):
        # Rows with empty analyzed_at should be excluded
        db.execute(
            "INSERT INTO analysis_runs (owner, repo, session, overall_score, grade, analyzed_at) VALUES (?,?,?,?,?,?)",
            ("org", "repo", 1, 70.0, "B", ""),
        )
        db.commit()
        result = get_weekly_aggregation(db, "org", "repo")
        assert result == []


# ---------------------------------------------------------------------------
# get_session_leaderboard_delta
# ---------------------------------------------------------------------------


class TestGetSessionLeaderboardDelta:
    def test_empty_sessions(self, db):
        result = get_session_leaderboard_delta(db, 1, 2)
        assert result == []

    def test_rank_change_computed(self, db):
        _insert_run(db, "acme", "alpha", session=1, score=90.0)
        _insert_run(db, "acme", "beta", session=1, score=70.0)
        _insert_run(db, "acme", "alpha", session=2, score=65.0)
        _insert_run(db, "acme", "beta", session=2, score=85.0)
        result = get_session_leaderboard_delta(db, 1, 2)
        by_repo = {r["repo"]: r for r in result}
        # alpha: was rank 1 now rank 2 → rank_change = -1
        assert by_repo["alpha"]["rank_change"] == -1
        # beta: was rank 2 now rank 1 → rank_change = +1
        assert by_repo["beta"]["rank_change"] == 1

    def test_new_project_in_session_b(self, db):
        _insert_run(db, "org", "old", session=1, score=70.0)
        _insert_run(db, "org", "old", session=2, score=70.0)
        _insert_run(db, "org", "new", session=2, score=80.0)
        result = get_session_leaderboard_delta(db, 1, 2)
        by_repo = {r["repo"]: r for r in result}
        assert "new" in by_repo
        assert by_repo["new"]["score_a"] == 0.0
        assert by_repo["new"]["rank_a"] == 9999

    def test_sorted_by_rank_b(self, db):
        for i, score in enumerate([80.0, 70.0, 60.0], 1):
            _insert_run(db, "org", f"p{i}", session=1, score=score)
            _insert_run(db, "org", f"p{i}", session=2, score=score)
        result = get_session_leaderboard_delta(db, 1, 2)
        ranks = [r["rank_b"] for r in result]
        assert ranks == sorted(ranks)
