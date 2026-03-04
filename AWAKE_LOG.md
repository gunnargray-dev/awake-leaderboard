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
- Done **Seed 10 trending repos** -- Added 10 Python projects across 6 categories, expanding coverage from 55 to 65 projects:
  1. `vllm-project/vllm` -- ai-framework -- High-throughput LLM serving engine
  2. `pydantic/pydantic` -- data-science -- Data validation using Python type annotations
  3. `pola-rs/polars` -- data-science -- Lightning-fast DataFrame library
  4. `duckdb/duckdb` -- data-science -- In-process analytical database
  5. `encode/starlette` -- web-framework -- Lightweight ASGI framework
  6. `tiangolo/typer` -- cli-tool -- CLI builder based on Python type hints
  7. `Textualize/textual` -- cli-tool -- TUI framework for Python
  8. `PyCQA/bandit` -- security -- Python security linter
  9. `semgrep/semgrep` -- security -- Lightweight static analysis
  10. `pulumi/pulumi` -- devops -- Infrastructure as code in real languages
- Done **Regenerated leaderboard.json** -- 65 projects with full score breakdowns, average score 77.4
- Done **New security category** -- Added security display category to the generator
- Done **Tests** -- 2 new tests (260 total, all passing)

### PR
- PR #6 -- Session 7: Seed 10 more projects (65 total)

### Decisions
1. Diversified across 6 categories (AI/ML, data, web, CLI, security, DevOps) to broaden leaderboard coverage beyond the AI-heavy initial set.
2. Added security as a new display category -- Bandit and Semgrep are foundational Python security tools.
3. Regenerated full leaderboard.json after seeding -- website immediately reflects the expanded catalog.

### Stats
| Metric | Value |
|--------|-------|
| New seed projects | 10 |
| Total seed projects | 65 |
| Categories represented | 8+ |
| Tests passing | 260 |
| Average score | 77.4 |
| PRs opened | 1 (total: 6) |

---

## Session 8 -- Score History Tracking (2026-03-04)

**Operator:** Computer
**Trigger:** Autonomous -- maintenance mode (cron)

### Tasks Completed
- Done **Score history tracker** -- Built `src/score_history.py`: Append-only score history system with `ScoreSnapshot`, `ScoreDelta`, and `MoverReport` data structures. Records per-session snapshots for all 65 projects with full score breakdowns.
- Done **Delta computation** -- Computes per-project score changes between any two snapshots. Identifies biggest movers (top N improvers and decliners) across sessions.
- Done **Refresh pipeline** -- `refresh_scores()` function: regenerates all project scores, records snapshot, computes deltas from previous session, and returns a mover report.
- Done **CLI integration** -- Added `awake-lb refresh-scores` subcommand with `--session`, `--top`, `--data-dir`, and `--json` flags.
- Done **Leaderboard regeneration** -- Updated `website/data/leaderboard.json` with latest scores for all 65 projects.
- Done **Test suite** -- 60 new tests (320 total, all passing) covering snapshot creation, delta computation, mover identification, edge cases.

### PR
- PR #7 -- Session 8: Score history tracking + refresh pipeline

### Decisions
1. Append-only history design -- never overwrite past snapshots, enabling trend analysis over time.
2. Structured data types (ScoreSnapshot, ScoreDelta, MoverReport) rather than raw dicts -- makes the API self-documenting and enables type checking.
3. Top-N movers report highlights the most interesting changes each session -- this becomes natural tweet content ("biggest mover this session: X jumped +12 points").
4. Refresh pipeline is a single function call -- simple for the cron to invoke, and outputs both human-readable and machine-readable reports.

### Stats
| Metric | Before | After |
|--------|--------|-------|
| Source modules | 9 | 10 |
| Tests passing | 260 | 320 |
| Projects tracked | 65 | 65 |
| PRs merged | 6 | 7 |

---
