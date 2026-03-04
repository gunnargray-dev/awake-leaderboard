"""Awake Leaderboard -- badge generation.

Generates shields.io-compatible badge URLs for embedding project scores
in READMEs, websites, and social cards.

Badge colors map to letter grades:
    A+, A, A-  -> brightgreen
    B+, B, B-  -> green
    C+, C, C-  -> yellow
    D          -> orange
    F          -> red

Public API
----------
- ``grade_to_color(grade)``                   -> str
- ``generate_badge_url(score, grade)``         -> str
- ``generate_badge_markdown(owner, repo, score, grade)`` -> str
- ``generate_score_badge_url(score)``          -> str
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Color mapping
# ---------------------------------------------------------------------------

_GRADE_COLORS: dict[str, str] = {
    "A+": "brightgreen",
    "A":  "brightgreen",
    "A-": "brightgreen",
    "B+": "green",
    "B":  "green",
    "B-": "green",
    "C+": "yellow",
    "C":  "yellow",
    "C-": "yellow",
    "D":  "orange",
    "F":  "red",
}

_SHIELDS_BASE = "https://img.shields.io/badge"


# ---------------------------------------------------------------------------
# Badge functions
# ---------------------------------------------------------------------------


def grade_to_color(grade: str) -> str:
    """Map a letter grade to a shields.io color name.

    Args:
        grade: Letter grade string, e.g. ``"A+"``, ``"B-"``, ``"F"``.

    Returns:
        shields.io color name, e.g. ``"brightgreen"``, ``"red"``.
        Falls back to ``"lightgrey"`` for unknown grades.
    """
    return _GRADE_COLORS.get(grade, "lightgrey")


def generate_badge_url(score: float, grade: str) -> str:
    """Generate a shields.io badge URL for an Awake score.

    Args:
        score: Numeric score 0-100.
        grade: Letter grade string.

    Returns:
        Full shields.io URL, e.g.:
        ``https://img.shields.io/badge/Awake_Score-85%20A-brightgreen``
    """
    color = grade_to_color(grade)
    score_int = round(score)
    label = f"Awake Score"
    value = f"{score_int} {grade}"
    # shields.io uses - as separator and encodes spaces as _
    value_encoded = value.replace(" ", "_").replace("-", "--")
    return f"{_SHIELDS_BASE}/{label.replace(' ', '_')}-{value_encoded}-{color}"


def generate_score_badge_url(score: float) -> str:
    """Generate a numeric-only badge URL (no grade label).

    Args:
        score: Numeric score 0-100.

    Returns:
        shields.io URL showing just the score with color coding.
    """
    score_int = round(score)
    if score >= 80:
        color = "brightgreen"
    elif score >= 60:
        color = "green"
    elif score >= 40:
        color = "yellow"
    elif score >= 20:
        color = "orange"
    else:
        color = "red"
    return f"{_SHIELDS_BASE}/Awake_Score-{score_int}-{color}"


def generate_badge_markdown(
    owner: str,
    repo: str,
    score: float,
    grade: str,
) -> str:
    """Generate a Markdown badge snippet for embedding in a README.

    Args:
        owner: Repository owner (e.g. ``"pallets"``).
        repo:  Repository name (e.g. ``"flask"``).
        score: Numeric score 0-100.
        grade: Letter grade string.

    Returns:
        Markdown image with link to the repo, e.g.:
        ``[![Awake Score](badge_url)](https://github.com/owner/repo)``
    """
    badge_url = generate_badge_url(score, grade)
    repo_url = f"https://github.com/{owner}/{repo}"
    return f"[![Awake Score]({badge_url})]({repo_url})"


def generate_all_badges(
    owner: str,
    repo: str,
    score: float,
    grade: str,
    health_score: float = 0.0,
    security_score: float = 0.0,
    complexity_score: float = 0.0,
) -> dict[str, str]:
    """Generate a full set of badge URLs for a project.

    Returns a dict with keys: overall, health, security, complexity,
    all as shields.io URLs.
    """
    def _score_badge(label: str, s: float) -> str:
        s_int = round(s)
        color = "brightgreen" if s >= 80 else "green" if s >= 60 else "yellow" if s >= 40 else "orange" if s >= 20 else "red"
        return f"{_SHIELDS_BASE}/{label.replace(' ', '_')}-{s_int}-{color}"

    return {
        "overall": generate_badge_url(score, grade),
        "health": _score_badge("Health", health_score),
        "security": _score_badge("Security", security_score),
        "complexity": _score_badge("Complexity", complexity_score),
    }
