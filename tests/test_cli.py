"""Tests for src.cli -- command-line interface."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.models import AnalysisRun, Project, init_db, insert_run, upsert_project
from src.cli import build_parser, main, _truncate, _fmt_table


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


def _seed(db_path, owner="a", repo="flask", session=1, score=75.0):
    conn = init_db(db_path)
    upsert_project(conn, Project(
        owner=owner, repo=repo,
        url=f"https://github.com/{owner}/{repo}",
        category="web-framework", language="Python", stars=1000,
    ))
    insert_run(conn, AnalysisRun(
        owner=owner, repo=repo, session=session,
        overall_score=score, grade="B",
        health_score=score, complexity_score=score,
        security_score=score, dead_code_pct=0.0,
    ))
    conn.close()


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_string(self):
        assert _truncate("hello", 10) == "hello"

    def test_exact_length(self):
        assert _truncate("hello", 5) == "hello"

    def test_truncates_long(self):
        result = _truncate("hello world", 8)
        assert len(result) == 8
        assert result.endswith("…")


class TestFmtTable:
    def test_basic_table(self):
        out = _fmt_table(["A", "B"], [["x", "y"], ["foo", "bar"]])
        assert "A" in out
        assert "B" in out
        assert "foo" in out


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_top_command(self):
        parser = build_parser()
        args = parser.parse_args(["top"])
        assert args.command == "top"
        assert args.limit == 20

    def test_top_limit_option(self):
        args = build_parser().parse_args(["top", "--limit", "5"])
        assert args.limit == 5

    def test_top_category_option(self):
        args = build_parser().parse_args(["top", "--category", "testing"])
        assert args.category == "testing"

    def test_top_sort_by(self):
        args = build_parser().parse_args(["top", "--sort-by", "stars"])
        assert args.sort_by == "stars"

    def test_detail_command(self):
        args = build_parser().parse_args(["detail", "pallets/flask"])
        assert args.command == "detail"
        assert args.project == "pallets/flask"

    def test_refresh_command(self):
        args = build_parser().parse_args(["refresh", "pallets/flask", "--session", "2"])
        assert args.command == "refresh"
        assert args.session == 2

    def test_refresh_all_command(self):
        args = build_parser().parse_args(["refresh-all", "--session", "3"])
        assert args.command == "refresh-all"
        assert args.session == 3

    def test_trends_command(self):
        args = build_parser().parse_args(["trends", "--limit", "5", "--sessions", "3"])
        assert args.limit == 5
        assert args.sessions == 3

    def test_compare_command(self):
        args = build_parser().parse_args(["compare", "a/x", "b/y"])
        assert args.project_a == "a/x"
        assert args.project_b == "b/y"

    def test_digest_command(self):
        args = build_parser().parse_args(["digest", "--session", "4"])
        assert args.session == 4

    def test_badge_command(self):
        args = build_parser().parse_args(["badge", "a/b"])
        assert args.project == "a/b"

    def test_seed_default_session(self):
        args = build_parser().parse_args(["seed"])
        assert args.session == 0

    def test_no_command_raises(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])


# ---------------------------------------------------------------------------
# Command execution tests
# ---------------------------------------------------------------------------


class TestCmdTop:
    def test_empty_db(self, db_path, capsys):
        main(["--db", str(db_path), "top"])
        out = capsys.readouterr().out
        assert "seed" in out.lower() or "no projects" in out.lower()

    def test_with_data(self, db_path, capsys):
        _seed(db_path, "pallets", "flask", score=85.0)
        main(["--db", str(db_path), "top"])
        out = capsys.readouterr().out
        assert "pallets/flask" in out
        assert "85.0" in out

    def test_limit_option(self, db_path, capsys):
        for i in range(5):
            _seed(db_path, "a", f"repo{i}", score=float(70 + i))
        main(["--db", str(db_path), "top", "--limit", "3"])
        out = capsys.readouterr().out
        assert "Top 3" in out


class TestCmdDetail:
    def test_missing_project(self, db_path, capsys):
        init_db(db_path)
        with pytest.raises(SystemExit):
            main(["--db", str(db_path), "detail", "ghost/missing"])

    def test_existing_project(self, db_path, capsys):
        _seed(db_path, "pallets", "flask", score=85.0)
        main(["--db", str(db_path), "detail", "pallets/flask"])
        out = capsys.readouterr().out
        assert "pallets/flask" in out
        assert "85.0" in out

    def test_bad_format_exits(self, db_path, capsys):
        with pytest.raises(SystemExit):
            main(["--db", str(db_path), "detail", "no-slash-here"])


class TestCmdStats:
    def test_empty_db(self, db_path, capsys):
        main(["--db", str(db_path), "stats"])
        out = capsys.readouterr().out
        assert "Projects" in out

    def test_with_data(self, db_path, capsys):
        _seed(db_path, score=80.0)
        main(["--db", str(db_path), "stats"])
        out = capsys.readouterr().out
        assert "1" in out


class TestCmdCategories:
    def test_empty_db(self, db_path, capsys):
        main(["--db", str(db_path), "categories"])
        out = capsys.readouterr().out
        assert "No projects" in out

    def test_with_data(self, db_path, capsys):
        _seed(db_path, score=75.0)
        main(["--db", str(db_path), "categories"])
        out = capsys.readouterr().out
        assert "web-framework" in out


class TestCmdTrends:
    def test_no_history(self, db_path, capsys):
        _seed(db_path)
        main(["--db", str(db_path), "trends"])
        out = capsys.readouterr().out
        assert "Not enough history" in out or "Biggest Movers" in out


class TestCmdCompare:
    def test_missing_data(self, db_path, capsys):
        init_db(db_path)
        with pytest.raises(SystemExit):
            main(["--db", str(db_path), "compare", "a/x", "b/y"])

    def test_successful_comparison(self, db_path, capsys):
        _seed(db_path, "a", "alpha", score=85.0)
        _seed(db_path, "b", "beta", score=70.0)
        main(["--db", str(db_path), "compare", "a/alpha", "b/beta"])
        out = capsys.readouterr().out
        assert "a/alpha" in out
        assert "b/beta" in out


class TestCmdDigest:
    def test_empty_db(self, db_path, capsys):
        main(["--db", str(db_path), "digest"])
        out = capsys.readouterr().out
        assert "Digest" in out

    def test_with_session(self, db_path, capsys):
        _seed(db_path, session=2, score=80.0)
        main(["--db", str(db_path), "digest", "--session", "2"])
        out = capsys.readouterr().out
        assert "Session 2" in out


class TestCmdBadge:
    def test_no_data(self, db_path, capsys):
        init_db(db_path)
        with pytest.raises(SystemExit):
            main(["--db", str(db_path), "badge", "x/y"])

    def test_with_data(self, db_path, capsys):
        _seed(db_path, "a", "b", score=85.0)
        main(["--db", str(db_path), "badge", "a/b"])
        out = capsys.readouterr().out
        assert "shields.io" in out
        assert "Markdown" in out
