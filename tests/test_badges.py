"""Tests for src/badges.py -- badge URL generation."""

from __future__ import annotations

import pytest

from src.badges import (
    grade_to_color,
    generate_badge_url,
    generate_badge_markdown,
    generate_score_badge_url,
    generate_all_badges,
)


SHIELDS_BASE = "https://img.shields.io/badge"


# ---------------------------------------------------------------------------
# grade_to_color
# ---------------------------------------------------------------------------


class TestGradeToColor:
    def test_a_plus_brightgreen(self):
        assert grade_to_color("A+") == "brightgreen"

    def test_a_brightgreen(self):
        assert grade_to_color("A") == "brightgreen"

    def test_a_minus_brightgreen(self):
        assert grade_to_color("A-") == "brightgreen"

    def test_b_green(self):
        assert grade_to_color("B") == "green"

    def test_c_yellow(self):
        assert grade_to_color("C") == "yellow"

    def test_d_orange(self):
        assert grade_to_color("D") == "orange"

    def test_f_red(self):
        assert grade_to_color("F") == "red"

    def test_unknown_grade_lightgrey(self):
        assert grade_to_color("X") == "lightgrey"
        assert grade_to_color("") == "lightgrey"


# ---------------------------------------------------------------------------
# generate_badge_url
# ---------------------------------------------------------------------------


class TestGenerateBadgeUrl:
    def test_returns_string(self):
        url = generate_badge_url(85.0, "A")
        assert isinstance(url, str)

    def test_starts_with_shields_base(self):
        url = generate_badge_url(75.0, "B")
        assert url.startswith(SHIELDS_BASE)

    def test_includes_score(self):
        url = generate_badge_url(85.0, "A+")
        assert "85" in url

    def test_includes_grade(self):
        url = generate_badge_url(85.0, "A+")
        assert "A%2B" in url or "A+" in url or "A" in url

    def test_high_score_brightgreen(self):
        url = generate_badge_url(90.0, "A+")
        assert "brightgreen" in url

    def test_f_grade_red(self):
        url = generate_badge_url(30.0, "F")
        assert "red" in url

    def test_rounding(self):
        url = generate_badge_url(84.6, "A-")
        assert "85" in url


# ---------------------------------------------------------------------------
# generate_score_badge_url
# ---------------------------------------------------------------------------


class TestGenerateScoreBadgeUrl:
    def test_returns_url(self):
        url = generate_score_badge_url(75.0)
        assert url.startswith(SHIELDS_BASE)

    def test_high_score_green(self):
        url = generate_score_badge_url(90.0)
        assert "brightgreen" in url

    def test_low_score_red(self):
        url = generate_score_badge_url(10.0)
        assert "red" in url

    def test_mid_score_color(self):
        url = generate_score_badge_url(65.0)
        assert "green" in url or "yellow" in url

    def test_score_integer_in_url(self):
        url = generate_score_badge_url(72.9)
        assert "73" in url


# ---------------------------------------------------------------------------
# generate_badge_markdown
# ---------------------------------------------------------------------------


class TestGenerateBadgeMarkdown:
    def test_returns_markdown(self):
        md = generate_badge_markdown("pallets", "flask", 85.0, "A")
        assert md.startswith("[![")

    def test_includes_repo_url(self):
        md = generate_badge_markdown("pallets", "flask", 85.0, "A")
        assert "https://github.com/pallets/flask" in md

    def test_includes_badge_url(self):
        md = generate_badge_markdown("pallets", "flask", 85.0, "A")
        assert SHIELDS_BASE in md

    def test_markdown_structure(self):
        md = generate_badge_markdown("org", "repo", 70.0, "B")
        # Should be [![...](...)(...)]
        assert md.startswith("[![")
        assert ")](https://" in md


# ---------------------------------------------------------------------------
# generate_all_badges
# ---------------------------------------------------------------------------


class TestGenerateAllBadges:
    def test_returns_dict(self):
        badges = generate_all_badges("org", "repo", 75.0, "B")
        assert isinstance(badges, dict)

    def test_has_expected_keys(self):
        badges = generate_all_badges("org", "repo", 75.0, "B",
                                     health_score=80.0,
                                     security_score=70.0,
                                     complexity_score=60.0)
        assert "overall" in badges
        assert "health" in badges
        assert "security" in badges
        assert "complexity" in badges

    def test_all_values_are_urls(self):
        badges = generate_all_badges("org", "repo", 75.0, "B",
                                     health_score=80.0,
                                     security_score=70.0,
                                     complexity_score=60.0)
        for val in badges.values():
            assert val.startswith(SHIELDS_BASE)
