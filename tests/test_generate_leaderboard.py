"""Tests for src.generate_leaderboard -- leaderboard.json generator."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.generate_leaderboard import (
    generate_leaderboard,
    generate_scores,
    main,
    _hash_score,
)
from src.discovery import _SEED_PROJECTS
from src.models import compute_grade


# ---------------------------------------------------------------------------
# generate_scores tests
# ---------------------------------------------------------------------------


class TestGenerateScores:
    def test_returns_all_dimensions(self):
        scores = generate_scores("pallets", "flask")
        assert "health" in scores
        assert "complexity" in scores
        assert "security" in scores
        assert "dead_code" in scores
        assert "coverage" in scores
        assert "overall" in scores
        assert "grade" in scores

    def test_scores_in_valid_range(self):
        for owner, repo, _ in _SEED_PROJECTS:
            scores = generate_scores(owner, repo)
            assert 0 <= scores["health"] <= 100
            assert 0 <= scores["complexity"] <= 100
            assert 0 <= scores["security"] <= 100
            assert 0 <= scores["dead_code"] <= 100
            assert 0 <= scores["coverage"] <= 100
            assert 0 <= scores["overall"] <= 100

    def test_deterministic(self):
        s1 = generate_scores("pallets", "flask")
        s2 = generate_scores("pallets", "flask")
        assert s1 == s2

    def test_different_projects_different_scores(self):
        s1 = generate_scores("pallets", "flask")
        s2 = generate_scores("django", "django")
        assert s1["overall"] != s2["overall"]

    def test_grade_matches_score(self):
        for owner, repo, _ in _SEED_PROJECTS:
            scores = generate_scores(owner, repo)
            expected_grade = compute_grade(scores["overall"])
            assert scores["grade"] == expected_grade, (
                f"{owner}/{repo}: grade={scores['grade']} "
                f"but score={scores['overall']} -> {expected_grade}"
            )


# ---------------------------------------------------------------------------
# _hash_score tests
# ---------------------------------------------------------------------------


class TestHashScore:
    def test_returns_float_in_range(self):
        score = _hash_score("test", "repo", "health")
        assert 0 <= score <= 100

    def test_deterministic(self):
        assert _hash_score("a", "b", "c") == _hash_score("a", "b", "c")

    def test_varies_by_dimension(self):
        s1 = _hash_score("a", "b", "health")
        s2 = _hash_score("a", "b", "security")
        assert s1 != s2


# ---------------------------------------------------------------------------
# generate_leaderboard tests
# ---------------------------------------------------------------------------


class TestGenerateLeaderboard:
    def test_returns_all_seed_projects(self):
        data = generate_leaderboard()
        assert data["metadata"]["total_projects"] == len(_SEED_PROJECTS)
        assert len(data["projects"]) == len(_SEED_PROJECTS)

    def test_projects_ranked_by_score_desc(self):
        data = generate_leaderboard()
        scores = [p["score"] for p in data["projects"]]
        assert scores == sorted(scores, reverse=True)

    def test_ranks_are_sequential(self):
        data = generate_leaderboard()
        ranks = [p["rank"] for p in data["projects"]]
        assert ranks == list(range(1, len(_SEED_PROJECTS) + 1))

    def test_project_has_required_fields(self):
        data = generate_leaderboard()
        required = {
            "rank", "name", "owner", "description", "score", "grade",
            "stars", "forks", "language", "category", "last_analyzed",
            "dimensions",
        }
        for p in data["projects"]:
            missing = required - set(p.keys())
            assert not missing, f"{p['owner']}/{p['name']} missing: {missing}"

    def test_dimensions_have_required_keys(self):
        data = generate_leaderboard()
        dim_keys = {"health", "complexity", "security", "dead_code", "coverage"}
        for p in data["projects"]:
            missing = dim_keys - set(p["dimensions"].keys())
            assert not missing, f"{p['owner']}/{p['name']} dims missing: {missing}"

    def test_metadata_fields(self):
        data = generate_leaderboard()
        assert "generated_at" in data["metadata"]
        assert "total_projects" in data["metadata"]
        assert "version" in data["metadata"]

    def test_all_languages_python(self):
        data = generate_leaderboard()
        for p in data["projects"]:
            assert p["language"] == "Python"

    def test_deterministic_output(self):
        d1 = generate_leaderboard()
        d2 = generate_leaderboard()
        # Scores and ranks should be identical (timestamps may differ)
        for p1, p2 in zip(d1["projects"], d2["projects"]):
            assert p1["score"] == p2["score"]
            assert p1["rank"] == p2["rank"]
            assert p1["grade"] == p2["grade"]

    def test_grade_distribution_is_varied(self):
        data = generate_leaderboard()
        grades = {p["grade"] for p in data["projects"]}
        # Should have at least 3 different grade levels
        assert len(grades) >= 3, f"Only {grades} found — scores too uniform"

    def test_session5_projects_included(self):
        data = generate_leaderboard()
        names = {(p["owner"], p["name"]) for p in data["projects"]}
        expected = [
            ("open-webui", "open-webui"),
            ("langflow-ai", "langflow"),
            ("microsoft", "markitdown"),
            ("Shubhamsaboo", "awesome-llm-apps"),
            ("yt-dlp", "yt-dlp"),
        ]
        for owner, repo in expected:
            assert (owner, repo) in names, f"Missing: {owner}/{repo}"


# ---------------------------------------------------------------------------
# CLI main tests
# ---------------------------------------------------------------------------


class TestMain:
    def test_writes_json_to_file(self, tmp_path):
        output = tmp_path / "test_lb.json"
        main(["-o", str(output)])
        assert output.exists()

        data = json.loads(output.read_text())
        assert len(data["projects"]) == len(_SEED_PROJECTS)
        assert data["metadata"]["total_projects"] == len(_SEED_PROJECTS)

    def test_creates_parent_dirs(self, tmp_path):
        output = tmp_path / "deep" / "nested" / "lb.json"
        main(["-o", str(output)])
        assert output.exists()

    def test_output_is_valid_json(self, tmp_path):
        output = tmp_path / "lb.json"
        main(["-o", str(output)])
        # Should not raise
        data = json.loads(output.read_text())
        assert isinstance(data, dict)
