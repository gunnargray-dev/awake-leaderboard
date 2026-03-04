"""Tests for src.stats_summary -- aggregate leaderboard statistics."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from src.stats_summary import (
    GradeDistribution,
    CategoryStats,
    StatsSummary,
    compute_stats,
    generate_stats_report,
    _median,
    _std_dev,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_project(
    name: str = "flask",
    owner: str = "pallets",
    score: float = 80.0,
    grade: str = "A-",
    category: str = "Web Frameworks",
    health: float = 80.0,
    complexity: float = 75.0,
    security: float = 85.0,
    dead_code: float = 90.0,
    coverage: float = 70.0,
) -> dict:
    return {
        "name": name,
        "owner": owner,
        "score": score,
        "grade": grade,
        "category": category,
        "stars": 50000,
        "forks": 10000,
        "language": "Python",
        "dimensions": {
            "health": health,
            "complexity": complexity,
            "security": security,
            "dead_code": dead_code,
            "coverage": coverage,
        },
    }


@pytest.fixture
def sample_projects():
    """A small set of projects for testing."""
    return [
        _make_project("flask", "pallets", 85.0, "A", "Web Frameworks",
                       82.0, 78.0, 90.0, 88.0, 80.0),
        _make_project("django", "django", 80.0, "A-", "Web Frameworks",
                       79.0, 75.0, 85.0, 82.0, 78.0),
        _make_project("pandas", "pandas-dev", 75.0, "B+", "Data Science",
                       76.0, 70.0, 80.0, 85.0, 72.0),
        _make_project("numpy", "numpy", 70.0, "B", "Data Science",
                       72.0, 68.0, 75.0, 80.0, 68.0),
        _make_project("pytest", "pytest-dev", 90.0, "A+", "Testing",
                       88.0, 85.0, 92.0, 95.0, 88.0),
    ]


@pytest.fixture
def single_project():
    return [_make_project()]


# ---------------------------------------------------------------------------
# _median tests
# ---------------------------------------------------------------------------


class TestMedian:
    def test_odd_count(self):
        assert _median([1, 2, 3, 4, 5]) == 3

    def test_even_count(self):
        assert _median([1, 2, 3, 4]) == 2.5

    def test_single(self):
        assert _median([42]) == 42

    def test_empty(self):
        assert _median([]) == 0.0

    def test_unsorted_input(self):
        assert _median([5, 1, 3]) == 3

    def test_duplicates(self):
        assert _median([7, 7, 7]) == 7

    def test_two_elements(self):
        assert _median([10, 20]) == 15.0


# ---------------------------------------------------------------------------
# _std_dev tests
# ---------------------------------------------------------------------------


class TestStdDev:
    def test_zero_variance(self):
        assert _std_dev([5, 5, 5], 5.0) == 0.0

    def test_known_std(self):
        # population std of [2, 4, 4, 4, 5, 5, 7, 9] = 2.0
        values = [2, 4, 4, 4, 5, 5, 7, 9]
        mean = sum(values) / len(values)
        result = _std_dev(values, mean)
        assert abs(result - 2.0) < 0.01

    def test_single_value(self):
        assert _std_dev([10], 10.0) == 0.0

    def test_empty(self):
        assert _std_dev([], 0.0) == 0.0

    def test_two_values(self):
        result = _std_dev([0, 10], 5.0)
        assert abs(result - 5.0) < 0.01


# ---------------------------------------------------------------------------
# GradeDistribution tests
# ---------------------------------------------------------------------------


class TestGradeDistribution:
    def test_to_dict(self):
        gd = GradeDistribution(grade="A+", count=5, percentage=25.0)
        d = gd.to_dict()
        assert d["grade"] == "A+"
        assert d["count"] == 5
        assert d["percentage"] == 25.0

    def test_fields(self):
        gd = GradeDistribution(grade="B", count=3, percentage=15.0)
        assert gd.grade == "B"
        assert gd.count == 3
        assert gd.percentage == 15.0


# ---------------------------------------------------------------------------
# CategoryStats tests
# ---------------------------------------------------------------------------


class TestCategoryStats:
    def test_to_dict(self):
        cs = CategoryStats(
            category="Web Frameworks",
            project_count=10,
            avg_score=82.5,
            min_score=70.0,
            max_score=95.0,
            avg_health=80.0,
            avg_complexity=75.0,
            avg_security=85.0,
        )
        d = cs.to_dict()
        assert d["category"] == "Web Frameworks"
        assert d["project_count"] == 10
        assert d["avg_score"] == 82.5

    def test_all_fields_present(self):
        cs = CategoryStats("ML/AI", 5, 78.0, 65.0, 90.0, 76.0, 74.0, 80.0)
        d = cs.to_dict()
        assert set(d.keys()) == {
            "category", "project_count", "avg_score",
            "min_score", "max_score", "avg_health",
            "avg_complexity", "avg_security",
        }


# ---------------------------------------------------------------------------
# StatsSummary tests
# ---------------------------------------------------------------------------


class TestStatsSummary:
    def test_to_dict_keys(self, sample_projects):
        report = compute_stats(sample_projects)
        d = report.to_dict()
        expected_keys = {
            "total_projects", "mean_score", "median_score",
            "std_score", "min_score", "max_score",
            "grade_distribution", "category_stats",
            "top_project", "bottom_project", "dimension_averages",
        }
        assert set(d.keys()) == expected_keys

    def test_to_json_valid(self, sample_projects):
        report = compute_stats(sample_projects)
        j = report.to_json()
        parsed = json.loads(j)
        assert parsed["total_projects"] == 5

    def test_to_markdown_structure(self, sample_projects):
        report = compute_stats(sample_projects)
        md = report.to_markdown()
        assert "# Awake Leaderboard Stats" in md
        assert "## Score Overview" in md
        assert "## Dimension Averages" in md
        assert "## Grade Distribution" in md
        assert "## Category Averages" in md
        assert "**5 projects**" in md

    def test_to_dict_rounds_values(self, sample_projects):
        report = compute_stats(sample_projects)
        d = report.to_dict()
        # All numeric values should have at most 1 decimal place
        assert d["mean_score"] == round(d["mean_score"], 1)
        assert d["median_score"] == round(d["median_score"], 1)
        assert d["std_score"] == round(d["std_score"], 1)

    def test_dimension_averages_in_dict(self, sample_projects):
        report = compute_stats(sample_projects)
        d = report.to_dict()
        dims = d["dimension_averages"]
        assert set(dims.keys()) == {"health", "complexity", "security", "dead_code", "coverage"}
        for v in dims.values():
            assert v == round(v, 1)


# ---------------------------------------------------------------------------
# compute_stats tests
# ---------------------------------------------------------------------------


class TestComputeStats:
    def test_total_projects(self, sample_projects):
        report = compute_stats(sample_projects)
        assert report.total_projects == 5

    def test_mean_score(self, sample_projects):
        expected = (85.0 + 80.0 + 75.0 + 70.0 + 90.0) / 5
        report = compute_stats(sample_projects)
        assert report.mean_score == round(expected, 1)

    def test_median_score(self, sample_projects):
        report = compute_stats(sample_projects)
        assert report.median_score == 80.0

    def test_min_max(self, sample_projects):
        report = compute_stats(sample_projects)
        assert report.min_score == 70.0
        assert report.max_score == 90.0

    def test_std_score(self, sample_projects):
        scores = [85.0, 80.0, 75.0, 70.0, 90.0]
        mean = sum(scores) / len(scores)
        expected = math.sqrt(sum((x - mean) ** 2 for x in scores) / len(scores))
        report = compute_stats(sample_projects)
        assert report.std_score == round(expected, 1)

    def test_top_project(self, sample_projects):
        report = compute_stats(sample_projects)
        assert "pytest-dev/pytest" in report.top_project
        assert "90.0" in report.top_project

    def test_bottom_project(self, sample_projects):
        report = compute_stats(sample_projects)
        assert "numpy/numpy" in report.bottom_project
        assert "70.0" in report.bottom_project

    def test_grade_distribution(self, sample_projects):
        report = compute_stats(sample_projects)
        grades = {g.grade: g.count for g in report.grade_distribution}
        assert grades["A+"] == 1
        assert grades["A"] == 1
        assert grades["A-"] == 1
        assert grades["B+"] == 1
        assert grades["B"] == 1

    def test_grade_distribution_percentages(self, sample_projects):
        report = compute_stats(sample_projects)
        for g in report.grade_distribution:
            expected_pct = round(g.count / 5 * 100, 1)
            assert g.percentage == expected_pct

    def test_grade_distribution_only_nonzero(self, sample_projects):
        report = compute_stats(sample_projects)
        for g in report.grade_distribution:
            assert g.count > 0

    def test_category_stats_count(self, sample_projects):
        report = compute_stats(sample_projects)
        cats = {c.category: c for c in report.category_stats}
        assert len(cats) == 3  # Web Frameworks, Data Science, Testing
        assert cats["Web Frameworks"].project_count == 2
        assert cats["Data Science"].project_count == 2
        assert cats["Testing"].project_count == 1

    def test_category_stats_avg_score(self, sample_projects):
        report = compute_stats(sample_projects)
        cats = {c.category: c for c in report.category_stats}
        # Web Frameworks: (85 + 80) / 2 = 82.5
        assert cats["Web Frameworks"].avg_score == 82.5
        # Data Science: (75 + 70) / 2 = 72.5
        assert cats["Data Science"].avg_score == 72.5

    def test_category_stats_sorted_by_avg_desc(self, sample_projects):
        report = compute_stats(sample_projects)
        avg_scores = [c.avg_score for c in report.category_stats]
        assert avg_scores == sorted(avg_scores, reverse=True)

    def test_category_min_max(self, sample_projects):
        report = compute_stats(sample_projects)
        cats = {c.category: c for c in report.category_stats}
        assert cats["Web Frameworks"].min_score == 80.0
        assert cats["Web Frameworks"].max_score == 85.0

    def test_dimension_averages(self, sample_projects):
        report = compute_stats(sample_projects)
        dims = report.dimension_averages
        # health: (82 + 79 + 76 + 72 + 88) / 5 = 79.4
        expected_health = (82 + 79 + 76 + 72 + 88) / 5
        assert abs(dims["health"] - expected_health) < 0.05

    def test_empty_projects(self):
        report = compute_stats([])
        assert report.total_projects == 0
        assert report.mean_score == 0.0
        assert report.median_score == 0.0
        assert report.grade_distribution == []
        assert report.category_stats == []

    def test_single_project(self, single_project):
        report = compute_stats(single_project)
        assert report.total_projects == 1
        assert report.mean_score == 80.0
        assert report.median_score == 80.0
        assert report.min_score == 80.0
        assert report.max_score == 80.0


# ---------------------------------------------------------------------------
# generate_stats_report tests
# ---------------------------------------------------------------------------


class TestGenerateStatsReport:
    def test_generates_from_seed_data(self):
        """Generate report without data_dir (fresh from seed list)."""
        report = generate_stats_report()
        assert report.total_projects == 75

    def test_reads_from_data_dir(self, tmp_path):
        """Generate report from existing leaderboard.json."""
        from src.generate_leaderboard import generate_leaderboard

        data = generate_leaderboard()
        lb_path = tmp_path / "leaderboard.json"
        lb_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        report = generate_stats_report(data_dir=tmp_path)
        assert report.total_projects == 75

    def test_falls_back_to_fresh_if_no_file(self, tmp_path):
        """When data_dir exists but leaderboard.json doesn't, generate fresh."""
        report = generate_stats_report(data_dir=tmp_path)
        assert report.total_projects == 75

    def test_report_has_all_categories(self):
        """All display categories should be represented."""
        report = generate_stats_report()
        cat_names = {c.category for c in report.category_stats}
        # Should have multiple categories from the 75 seed projects
        assert len(cat_names) >= 8

    def test_grade_distribution_sums_to_total(self):
        report = generate_stats_report()
        total_graded = sum(g.count for g in report.grade_distribution)
        assert total_graded == report.total_projects

    def test_report_deterministic(self):
        """Same seed data should produce identical reports."""
        r1 = generate_stats_report()
        r2 = generate_stats_report()
        assert r1.mean_score == r2.mean_score
        assert r1.median_score == r2.median_score
        assert r1.std_score == r2.std_score


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestStsSummaryCLI:
    def test_stats_summary_command_markdown(self, capsys):
        """CLI stats-summary outputs markdown by default."""
        from src.cli import main

        main(["stats-summary"])
        captured = capsys.readouterr()
        assert "# Awake Leaderboard Stats" in captured.out
        assert "75 projects" in captured.out

    def test_stats_summary_command_json(self, capsys):
        """CLI stats-summary --format json outputs valid JSON."""
        from src.cli import main

        main(["stats-summary", "--format", "json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total_projects"] == 75
        assert "mean_score" in data

    def test_stats_summary_command_write(self, tmp_path, capsys):
        """CLI stats-summary --write creates files."""
        from src.cli import main

        main(["stats-summary", "--write", "--data-dir", str(tmp_path)])
        md_path = tmp_path / "stats_summary.md"
        json_path = tmp_path / "stats_summary.json"
        assert md_path.exists()
        assert json_path.exists()
        # Verify JSON is valid
        data = json.loads(json_path.read_text())
        assert data["total_projects"] == 75

    def test_stats_summary_with_data_dir(self, tmp_path, capsys):
        """CLI stats-summary --data-dir reads from leaderboard.json."""
        from src.generate_leaderboard import generate_leaderboard
        from src.cli import main

        data = generate_leaderboard()
        lb_path = tmp_path / "leaderboard.json"
        lb_path.write_text(json.dumps(data, indent=2))

        main(["stats-summary", "--data-dir", str(tmp_path), "--format", "json"])
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["total_projects"] == 75


# ---------------------------------------------------------------------------
# Integration with real leaderboard data
# ---------------------------------------------------------------------------


class TestIntegrationWithLeaderboard:
    def test_scores_in_valid_range(self):
        """All computed scores should be in realistic ranges."""
        report = generate_stats_report()
        assert 50 < report.mean_score < 100
        assert 50 < report.median_score < 100
        assert report.std_score > 0
        assert report.min_score > 0
        assert report.max_score <= 100

    def test_all_dimensions_have_averages(self):
        report = generate_stats_report()
        expected_dims = {"health", "complexity", "security", "dead_code", "coverage"}
        assert set(report.dimension_averages.keys()) == expected_dims
        for dim, val in report.dimension_averages.items():
            assert 0 < val < 100, f"{dim} average out of range: {val}"

    def test_category_stats_cover_all_projects(self):
        """Sum of projects across categories should equal total."""
        report = generate_stats_report()
        total_in_cats = sum(c.project_count for c in report.category_stats)
        assert total_in_cats == report.total_projects

    def test_data_viz_category_present(self):
        """New data-viz category from session 10 should appear."""
        report = generate_stats_report()
        cat_names = {c.category for c in report.category_stats}
        assert "Data Visualization" in cat_names

    def test_workflow_orchestration_category_present(self):
        """New workflow-orchestration category from session 10 should appear."""
        report = generate_stats_report()
        cat_names = {c.category for c in report.category_stats}
        assert "Workflow Orchestration" in cat_names

    def test_markdown_output_not_empty(self):
        report = generate_stats_report()
        md = report.to_markdown()
        assert len(md) > 200

    def test_json_output_round_trips(self):
        report = generate_stats_report()
        j = report.to_json()
        parsed = json.loads(j)
        assert parsed["total_projects"] == 75
        # Verify it's serializable back
        json.dumps(parsed)
