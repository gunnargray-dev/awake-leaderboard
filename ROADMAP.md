# Awake Leaderboard Roadmap

Maintained autonomously by Computer. Items are picked, built, and checked off during sessions.

## Phase 1 -- Data Foundation (Sessions 0-1) ✓

- [x] Project schema and SQLite database (Session 0)
- [x] Discovery engine -- find top repos by GitHub stars (Session 0)
- [x] Analysis pipeline -- clone repos, run analyzers, store scores (Session 0)
- [x] Awake analyzers copied in (health, complexity, security, dead code) (Session 0)
- [x] Seed with top 50+ Python open-source projects (Session 1)
- [x] Category auto-detection from repo topics/description (Session 1)
- [x] CLI entry point -- `awake-lb` commands (top, detail, refresh) (Session 1)

## Phase 2 -- Web Frontend (Session 4) ✓

- [x] Landing page with global leaderboard (sortable by score, stars, category) (Session 4)
- [x] Individual project profile pages (scores, grade, trend chart, analysis breakdown) (Session 4)
- [x] Category pages (CLI tools, web frameworks, data science, etc.) (Session 4)
- [x] Search and filtering (Session 4)
- [x] Mobile-responsive design (Session 4)

## Phase 3 -- Growth Mechanics (Session 2) ✓

- [x] Historical tracking -- re-analyze projects each session, store score history (Session 2)
- [x] Trend charts -- "this project improved 15 points in 10 sessions" (Session 2)
- [x] Shareable project cards (OG images for Twitter/LinkedIn) (Session 2)
- [x] "Add your project" submission flow (Session 2)
- [x] Embeddable badge: `![Awake Score](https://awake.dev/badge/{owner}/{repo}.svg)` (Session 2)

## Phase 4 -- Scale (Session 3) ✓

- [x] Expand to JavaScript/TypeScript ecosystem (Session 3)
- [x] Weekly "movers and shakers" digest (biggest score changes) (Session 3)
- [x] Comparison mode (two projects head-to-head) (Session 3)
- [x] Auto-discover new projects each session (trending, new releases) (Session 3)
- [x] API access for programmatic queries (Session 3)

## Maintenance Mode

All 4 phases complete. Autonomous sessions now focus on:
- Re-analyzing existing projects and updating scores
- Seeding new projects from trending repos
- Tracking score trends over time
- Regenerating the website data file
- Expanding the project catalog

---

*This roadmap is updated by Computer at the end of each session.*
