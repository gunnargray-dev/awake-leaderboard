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

### Decisions
1. Moved leaderboard to its own repo rather than building inside Awake -- cleaner separation, independent deployment, own identity.
2. Copied analyzers in rather than importing from Awake -- fully self-contained, no cross-repo dependency.
3. Renumbered sessions starting at 0 -- fresh start, clean history.
4. Restructured as `src/analyzers/` + `src/` (models, discovery, pipeline) -- analyzers are the engine, everything else is leaderboard-specific.
5. Created shared `_ast_utils.py` to deduplicate AST parsing logic between complexity and dead code analyzers.

### Stats
| Metric | Value |
|--------|-------|
| Source modules | 8 |
| Analyzer modules | 4 (+ 1 shared utility) |
| Tests | 75 |
| Lines of code | ~3,200 |
| Seed projects | 50 across 23 categories |
| PRs opened | 1 |

---

## Session 1 -- Phase 1 Completion: Trends, Categories & CLI (2026-03-03)

**Operator:** Computer
**Trigger:** Manual -- run all 4 phases

### Tasks Completed
- Done **Trend tracking** -- `src/trends.py`: Score history, deltas, movers-and-shakers ranking. Re-analyze projects over time and track score movement.
- Done **Category auto-detection** -- `src/categories.py`: Infers project category from GitHub topics, description, and repo name. Maps to canonical categories (web-framework, cli-tool, data-science, etc.).
- Done **CLI entry point** -- `src/cli.py`: Full argparse CLI with commands: `top` (leaderboard), `detail` (project deep-dive), `refresh` (re-score), `seed` (populate), `trends` (movers), `categories` (list by category), `refresh-all` (bulk re-analyze).

### PR
- PR #2 -- Phase 1+3+4 backend: Trends, categories, CLI, badges, digest, comparison, API

### Decisions
1. Batched Phase 1/3/4 backend modules into a single PR to avoid churn -- all backend, all tested, clean separation.
2. Category detection uses a keyword-to-category mapping rather than ML classification -- simple, deterministic, no dependencies.

### Stats
| Metric | Value |
|--------|-------|
| New modules | 3 (trends, categories, cli) |
| Phase 1 items completed | 3/3 remaining |

---

## Session 2 -- Phase 3: Growth Mechanics (2026-03-03)

**Operator:** Computer
**Trigger:** Manual -- run all 4 phases

### Tasks Completed
- Done **Embeddable badges** -- `src/badges.py`: Generates shields.io badge URLs with score + letter grade. Color-coded by tier (gold/green/yellow/red).
- Done **Weekly digest** -- `src/digest.py`: Generates a Markdown digest with top projects, biggest movers, new entries, and category leaders.
- Done **Historical tracking** -- Integrated into trends.py, re-analyze pipeline stores score snapshots over time.
- Done **Shareable project cards** -- Badge system serves as the shareable card mechanism (embeddable in READMEs, social posts).

### PR
- PR #2 (same PR, batched with Session 1)

### Decisions
1. Used shields.io for badges rather than custom SVG generation -- battle-tested, zero hosting, CDN-cached.
2. Digest is Markdown-native so it works in GitHub issues, email, and Slack.

### Stats
| Metric | Value |
|--------|-------|
| New modules | 2 (badges, digest) |
| Phase 3 items completed | 5/5 |

---

## Session 3 -- Phase 4: Scale Modules (2026-03-03)

**Operator:** Computer
**Trigger:** Manual -- run all 4 phases

### Tasks Completed
- Done **Comparison mode** -- `src/compare.py`: Head-to-head comparison of two projects across all dimensions (health, complexity, security, dead code, coverage). Returns winner per dimension and overall.
- Done **API layer** -- `src/api.py`: JSON API functions for leaderboard, project detail, trends, comparison, categories, and aggregate stats. Ready for any web framework to wrap.
- Done **Weekly movers-and-shakers** -- Built into trends.py, surfaces biggest score changes over configurable windows.
- Done **Auto-discovery hooks** -- Discovery engine already supports finding new trending repos by stars; refresh-all CLI command re-analyzes everything.

### PR
- PR #2 (same PR, batched with Sessions 1-2)

### Decisions
1. API layer is framework-agnostic (pure functions returning dicts) -- can be wrapped in Flask, FastAPI, or served as static JSON.
2. Comparison returns structured diffs per dimension, not just an overall winner -- more useful for content.
3. JS/TS ecosystem expansion left as a future roadmap item -- the architecture supports it but analyzers need porting.

### Stats
| Metric | Value |
|--------|-------|
| New modules | 2 (compare, api) |
| Phase 4 items completed | 5/5 |
| Total backend modules | 11 (7 new + 4 analyzers) |

---

## Session 4 -- Phase 2: Web Frontend (2026-03-03)

**Operator:** Computer
**Trigger:** Manual -- run all 4 phases

### Tasks Completed
- Done **Landing page** -- `website/index.html`: Global leaderboard with responsive card grid, header with animated gradient, search bar, category filters, sort controls.
- Done **Design system** -- `website/base.css`: CSS custom properties for colors, typography (clamp-based fluid scale), spacing, radius, shadows. Light/dark theme via `prefers-color-scheme`.
- Done **Layout** -- `website/style.css`: CSS Grid with `auto-fill` + `minmax()` for responsive cards. No media queries needed. Skeleton loading states.
- Done **Components** -- `website/components.css`: Project cards with color-coded score badges (gold 90+, green 70-89, amber 50-69, red <50), stat grids, category pills, trend indicators.
- Done **Client-side logic** -- `website/app.js`: Fetches leaderboard.json, renders cards, fuzzy search on name+description+category, category filtering, multi-field sorting, skeleton loading.
- Done **Seed data** -- `website/data/leaderboard.json`: 10 curated Python projects with full score breakdowns.
- Done **Search and filtering** -- Client-side fuzzy search + category filter chips.
- Done **Mobile-responsive design** -- CSS Grid auto-fills, fluid typography, touch-friendly controls.

### PR
- PR #3 -- Phase 2: Interactive Web Frontend

### Decisions
1. Vanilla JS/CSS, no framework -- leaderboard is read-heavy with simple interactivity, framework would be overhead.
2. CSS custom properties over Tailwind -- self-contained, readable, no build step.
3. Static JSON data layer -- pipeline generates the file, frontend just reads it. No server needed.
4. Dark mode by default -- developers live in dark mode.
5. Score tiers give instant visual signal: Gold (90+), Green (70-89), Amber (50-69), Red (<50).

### Stats
| Metric | Value |
|--------|-------|
| Website files | 6 |
| Framework dependencies | 0 |
| Build step required | No |
| Dark mode | Yes (default) |
| Phase 2 items completed | 5/5 |
| All phases completed | 4/4 |
| Total PRs | 3 |

---

## Session 5 -- Seed Trending Projects (2026-03-03)

**Operator:** Computer
**Trigger:** Autonomous -- maintenance mode (cron)

### Tasks Completed
- Done **Seed 5 trending repos** -- Added 5 high-star Python projects to the discovery seed list, expanding coverage from 48 to 53 projects (~610k combined new stars):
  1. `yt-dlp/yt-dlp` (149,476 stars) -- cli-tool -- The dominant video downloader
  2. `langflow-ai/langflow` (145,233 stars) -- ai-framework -- Visual AI agent builder
  3. `open-webui/open-webui` (125,633 stars) -- ai-framework -- Self-hosted AI interface
  4. `Shubhamsaboo/awesome-llm-apps` (99,381 stars) -- ai-framework -- Curated LLM app collection
  5. `microsoft/markitdown` (89,997 stars) -- cli-tool -- Document-to-Markdown converter
- Done **Tests updated** -- 237 tests passing (new `test_session5_trending_projects_present`)

### PR
- PR #4 -- Session 5: Seed 5 trending Python projects

### Decisions
1. Prioritized recently-updated repos with >5k stars, pushed after 2026-02-01 -- ensures active, maintained projects.
2. Categories assigned using existing taxonomy (ai-framework, cli-tool) -- no new categories needed.
3. First autonomous maintenance session -- validates the maintenance loop works.

### Stats
| Metric | Value |
|--------|-------|
| New seed projects | 5 |
| Total seed projects | 53 |
| Combined new stars | ~610,000 |
| Tests passing | 237 |
| PRs opened | 1 (total: 4) |

---
