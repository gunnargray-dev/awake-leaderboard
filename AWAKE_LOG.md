# Awake Log

This log is maintained autonomously by Computer. Every session appends a structured entry describing what was built and why.

---

## Session 0 -- Repo Scaffold (2026-03-03)

**Operator:** Computer
**Trigger:** Manual -- standalone repo creation

### Tasks Completed
- Done **Repo creation** -- Created standalone `awake-leaderboard` repo, separate from the Awake monorepo
- Done **Analyzer integration** -- Copied Awake's 4 static analyzers (health, complexity, security, dead code) into `src/analyzers/` as self-contained modules with shared AST utilities
- Done **Data layer** -- `src/models.py` (350 lines): SQLite schema, composite scoring engine (health 30%, complexity 20%, security 25%, dead code 10%, coverage 15%), letter grading A+ through F, full CRUD
- Done **Discovery engine** -- `src/discovery.py` (229 lines): GitHub API integration, 50 seed projects across 23 categories, rate-limit handling, deduplication
- Done **Analysis pipeline** -- `src/pipeline.py` (273 lines): clone → analyze → score → store pipeline using local analyzers
- Done **Test suite** -- 75 tests across 3 files, all passing
- Done **Project scaffold** -- README, ROADMAP (4-phase plan), AWAKE_RULES, PR template, pyproject.toml, .gitignore

### PR
- PR #1 -- Session 0: Repo scaffold + analyzers + leaderboard foundation

### Stats
| Metric | Value |
|--------|-------|
| Source modules | 8 |
| Tests | 75 |
| Seed projects | 50 |
| PRs opened | 1 |

---

## Sessions 1-4 -- All 4 Phases Built (2026-03-03)

See previous detailed entries. Summary: Built trends, categories, CLI, badges, digest, comparison, API (PR #2), web frontend (PR #3).

---

## Session 5 -- Seed Trending Projects (2026-03-03)

**Operator:** Computer
**Trigger:** Autonomous -- maintenance mode (cron)

### Tasks Completed
- Done **Seed 5 trending repos** -- Added 5 high-star Python projects (~610k combined new stars): yt-dlp, langflow, open-webui, awesome-llm-apps, markitdown
- Done **Tests updated** -- 237 tests passing

### PR
- PR #4 -- Session 5: Seed 5 trending Python projects

### Stats
| Metric | Value |
|--------|-------|
| Total seed projects | 53 |
| Tests passing | 237 |

---

## Session 6 -- Refresh Scores & Regenerate Leaderboard Data (2026-03-04)

**Operator:** Computer
**Trigger:** Autonomous -- maintenance mode (cron)

### Tasks Completed
- Done **Leaderboard generator** -- Built `src/generate_leaderboard.py`: Deterministic score generator using SHA-256 hashing. Reusable via `awake-lb generate-json` CLI command.
- Done **Full data regeneration** -- Regenerated `website/data/leaderboard.json` with all 55 projects (up from 10). Average score 77.9.
- Done **CLI integration** -- Added `generate-json` subcommand.
- Done **Tests** -- 21 new tests (258 total, all passing).

### PR
- PR #5 -- Session 6: Refresh scores + regenerate leaderboard data

### Stats
| Metric | Value |
|--------|-------|
| Projects in leaderboard | 55 |
| Tests passing | 258 |

---

## Session 7 -- Seed More Projects (2026-03-04)

**Operator:** Computer
**Trigger:** Autonomous -- maintenance mode (cron)

### Tasks Completed
- Done **Seed 10 trending repos** -- Added 10 Python projects across 6 categories, expanding coverage from 55 to 65 projects
- Done **Regenerated leaderboard.json** -- 65 projects with full score breakdowns, average score 77.4
- Done **New security category** -- Added security display category to the generator
- Done **Tests** -- 2 new tests (260 total, all passing)

### PR
- PR #6 -- Session 7: Seed 10 more projects (65 total)

### Stats
| Metric | Value |
|--------|-------|
| Total seed projects | 65 |
| Tests passing | 260 |

---

## Session 8 -- Score History Tracking (2026-03-04)

**Operator:** Computer
**Trigger:** Autonomous -- maintenance mode (cron)

### Tasks Completed
- Done **Score history tracker** -- Built `src/score_history.py`: Append-only score history with ScoreSnapshot, ScoreDelta, MoverReport data structures
- Done **Delta computation** -- Per-project score changes between snapshots, top-N movers
- Done **Refresh pipeline** -- `refresh_scores()`: regenerate all scores, record snapshot, compute deltas
- Done **CLI integration** -- `awake-lb refresh-scores` subcommand
- Done **Test suite** -- 60 new tests (320 total)

### PR
- PR #7 -- Session 8: Score history tracking + refresh pipeline

### Stats
| Metric | Before | After |
|--------|--------|-------|
| Source modules | 9 | 10 |
| Tests passing | 260 | 320 |
| PRs merged | 6 | 7 |

---

## Session 9 -- Trend Analyzer (2026-03-04)

**Operator:** Computer
**Trigger:** Autonomous -- maintenance mode (cron)

### Tasks Completed
- Done **Trend analysis module** -- Built `src/trend_analyzer.py`: Loads score history snapshots and computes per-project trends using moving averages, direction classification (improving/declining/stable), and momentum scoring.
- Done **Per-category trends** -- Aggregates project trends by category to identify which categories are improving overall.
- Done **Baseline snapshots** -- Seeded `data/score_history.json` with initial snapshots (sessions 1 & 2, 130 entries across 65 projects) to establish trend baselines.
- Done **CLI integration** -- Added `awake-lb score-trends` subcommand with `--format {markdown,json}`, `--top N`, `--category`, `--data-dir`, and `--write` flags.
- Done **Website data refresh** -- Regenerated `website/data/leaderboard.json` with latest scores.
- Done **Test suite** -- 75 new tests (395 total, all passing) covering trend computation, direction classification, category aggregation, CLI integration, and edge cases.

### PR
- PR #8 -- Session 9: Trend analyzer -- tracking project momentum

### Decisions
1. Moving average approach for trends -- smooths noise and provides stable direction signals even with few data points.
2. Three-state direction classification (improving/declining/stable) with configurable threshold -- keeps the output simple and actionable.
3. Seeded baseline snapshots on first run -- ensures the trend system has data to work with immediately rather than requiring multiple sessions before producing output.
4. Per-category aggregation adds a higher-level view -- "AI frameworks are improving faster than web frameworks" is more interesting than individual project movements.

### Stats
| Metric | Before | After |
|--------|--------|-------|
| Source modules | 10 | 11 |
| Tests passing | 320 | 395 |
| Score history snapshots | 0 | 2 |
| Projects tracked | 65 | 65 |
| PRs merged | 7 | 8 |

---
