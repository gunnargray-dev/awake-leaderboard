"""Tests for src.discovery -- GitHub project discovery."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from src.discovery import (
    _parse_repo,
    discover_top_repos,
    discover_trending,
    fetch_repo_metadata,
    get_seed_projects,
    _SEED_PROJECTS,
)


# ---------------------------------------------------------------------------
# Mock GitHub API response
# ---------------------------------------------------------------------------

_MOCK_REPO = {
    "owner": {"login": "pallets"},
    "name": "flask",
    "html_url": "https://github.com/pallets/flask",
    "description": "The Python Micro Framework",
    "language": "Python",
    "stargazers_count": 65000,
    "forks_count": 16000,
    "open_issues_count": 12,
    "topics": ["python", "flask", "web"],
    "created_at": "2010-04-06T11:00:00Z",
    "pushed_at": "2024-03-01T10:00:00Z",
}

_MOCK_SEARCH_RESPONSE = json.dumps({
    "total_count": 1,
    "items": [_MOCK_REPO],
}).encode()


# ---------------------------------------------------------------------------
# _parse_repo tests
# ---------------------------------------------------------------------------


class TestParseRepo:
    def test_parses_all_fields(self):
        result = _parse_repo(_MOCK_REPO)
        assert result["owner"] == "pallets"
        assert result["repo"] == "flask"
        assert result["url"] == "https://github.com/pallets/flask"
        assert result["language"] == "Python"
        assert result["stars"] == 65000
        assert result["forks"] == 16000
        assert "python" in result["topics"]

    def test_handles_missing_fields(self):
        result = _parse_repo({})
        assert result["owner"] == ""
        assert result["repo"] == ""
        assert result["stars"] == 0

    def test_truncates_long_description(self):
        long_desc = "x" * 1000
        result = _parse_repo({"description": long_desc})
        assert len(result["description"]) <= 500

    def test_handles_null_description(self):
        result = _parse_repo({"description": None})
        assert result["description"] == ""

    def test_handles_null_language(self):
        result = _parse_repo({"language": None})
        assert result["language"] == ""


# ---------------------------------------------------------------------------
# discover_top_repos tests
# ---------------------------------------------------------------------------


class TestDiscoverTopRepos:
    @patch("src.discovery.urllib.request.urlopen")
    def test_returns_parsed_repos(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = _MOCK_SEARCH_RESPONSE
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        results = discover_top_repos("Python", limit=10)
        assert len(results) == 1
        assert results[0]["owner"] == "pallets"

    @patch("src.discovery.urllib.request.urlopen")
    def test_handles_api_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=403, msg="rate limit", hdrs={}, fp=None
        )
        results = discover_top_repos("Python")
        assert results == []

    @patch("src.discovery.urllib.request.urlopen")
    def test_respects_limit(self, mock_urlopen):
        items = [_MOCK_REPO] * 50
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "total_count": 50, "items": items,
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        results = discover_top_repos("Python", limit=5)
        assert len(results) == 5


# ---------------------------------------------------------------------------
# discover_trending tests
# ---------------------------------------------------------------------------


class TestDiscoverTrending:
    @patch("src.discovery.urllib.request.urlopen")
    def test_returns_repos(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = _MOCK_SEARCH_RESPONSE
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        results = discover_trending("Python", limit=10, days=7)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# fetch_repo_metadata tests
# ---------------------------------------------------------------------------


class TestFetchRepoMetadata:
    @patch("src.discovery.urllib.request.urlopen")
    def test_returns_metadata(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(_MOCK_REPO).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = fetch_repo_metadata("pallets", "flask")
        assert result["owner"] == "pallets"
        assert result["stars"] == 65000

    @patch("src.discovery.urllib.request.urlopen")
    def test_returns_none_on_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=404, msg="not found", hdrs={}, fp=None
        )
        result = fetch_repo_metadata("ghost", "missing")
        assert result is None


# ---------------------------------------------------------------------------
# Seed list tests
# ---------------------------------------------------------------------------


class TestSeedProjects:
    def test_returns_list(self):
        seeds = get_seed_projects()
        assert isinstance(seeds, list)
        assert len(seeds) == len(_SEED_PROJECTS)

    def test_seed_has_required_fields(self):
        for seed in get_seed_projects():
            assert "owner" in seed
            assert "repo" in seed
            assert "category" in seed
            assert "url" in seed
            assert seed["url"].startswith("https://github.com/")

    def test_seed_categories_are_valid(self):
        valid_categories = {
            "web-framework", "http-client", "data-science",
            "package-manager", "testing", "cli-framework",
            "code-quality", "type-checker", "data-validation",
            "database", "web-scraping", "image-processing",
            "serialization", "cloud-sdk", "devops", "networking",
            "cli-tool", "template-engine", "machine-learning",
            "ai-framework", "tui-framework", "utilities",
            "task-queue",
        }
        for seed in get_seed_projects():
            assert seed["category"] in valid_categories, (
                f"Unknown category: {seed['category']}"
            )

    def test_no_duplicate_seeds(self):
        seeds = get_seed_projects()
        keys = [(s["owner"], s["repo"]) for s in seeds]
        assert len(keys) == len(set(keys)), "Duplicate seed projects found"

    def test_session5_trending_projects_present(self):
        seeds = get_seed_projects()
        keys = {(s["owner"], s["repo"]): s["category"] for s in seeds}
        expected = [
            ("open-webui", "open-webui", "ai-framework"),
            ("langflow-ai", "langflow", "ai-framework"),
            ("microsoft", "markitdown", "cli-tool"),
            ("Shubhamsaboo", "awesome-llm-apps", "ai-framework"),
            ("yt-dlp", "yt-dlp", "cli-tool"),
        ]
        for owner, repo, category in expected:
            assert (owner, repo) in keys, f"Missing seed: {owner}/{repo}"
            assert keys[(owner, repo)] == category, (
                f"Wrong category for {owner}/{repo}: expected {category}"
            )
