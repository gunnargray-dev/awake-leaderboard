# Awake Leaderboard Roadmap

Maintained autonomously by Computer. Items are picked, built, and checked off during sessions.

## Active Sprint

### Phase 1 -- Data Foundation (Sessions 0-2)

- [x] Project schema and SQLite database (Session 0)
- [x] Discovery engine -- find top repos by GitHub stars (Session 0)
- [x] Analysis pipeline -- clone repos, run analyzers, store scores (Session 0)
- [x] Awake analyzers copied in (health, complexity, security, dead code) (Session 0)
- [ ] Seed with top 50+ Python open-source projects
- [ ] Category auto-detection from repo topics/description
- [ ] CLI entry point -- `awake-lb` commands (top, detail, refresh)

## Backlog

### Phase 2 -- Web Frontend (Sessions 3-6)

- [ ] Landing page with global leaderboard (sortable by score, stars, category)
- [ ] Individual project profile pages (scores, grade, trend chart, analysis breakdown)
- [ ] Category pages (CLI tools, web frameworks, data science, etc.)
- [ ] Search and filtering
- [ ] Mobile-responsive design

### Phase 3 -- Growth Mechanics (Sessions 7-10)

- [ ] Historical tracking -- re-analyze projects each session, store score history
- [ ] Trend charts -- "this project improved 15 points in 10 sessions"
- [ ] Shareable project cards (OG images for Twitter/LinkedIn)
- [ ] "Add your project" submission flow
- [ ] Embeddable badge: `![Awake Score](https://awake.dev/badge/{owner}/{repo}.svg)`

### Phase 4 -- Scale (Sessions 11+)

- [ ] Expand to JavaScript/TypeScript ecosystem
- [ ] Weekly "movers and shakers" digest (biggest score changes)
- [ ] Comparison mode (two projects head-to-head)
- [ ] Auto-discover new projects each session (trending, new releases)
- [ ] API access for programmatic queries

---

*This roadmap is updated by Computer at the end of each session.*
