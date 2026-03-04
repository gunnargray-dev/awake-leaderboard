# Awake Leaderboard

An open-source project leaderboard that builds itself.

Scores and ranks the top Python projects on GitHub using automated code analysis. Built autonomously by [Computer](https://computer.perplexity.ai) -- every session discovers new projects, re-analyzes existing ones, and tracks how code quality changes over time.

## How It Works

1. **Discover** -- finds top Python repos on GitHub by stars, trending, and community submissions
2. **Analyze** -- clones each repo and runs 4 static analysis passes (health, complexity, security, dead code)
3. **Score** -- computes a weighted composite score (health 30%, complexity 20%, security 25%, dead code 10%, coverage 15%)
4. **Rank** -- letter grade (A+ through F) and position on the leaderboard
5. **Track** -- re-analyzes every session, stores history, shows trends

## Scoring Weights

| Analyzer | Weight | What it measures |
|----------|--------|-----------------|
| Health | 30% | Docstrings, line length, TODOs, function/class structure |
| Security | 25% | Hardcoded secrets, eval/exec, unsafe imports, SQL injection patterns |
| Complexity | 20% | Cyclomatic complexity (McCabe's method) |
| Coverage | 15% | Test coverage percentage |
| Dead Code | 10% | Unused functions, classes, and imports |

## Project Structure

```
src/
├── analyzers/     # Static analysis tools (from Awake)
│   ├── health.py
│   ├── complexity.py
│   ├── security.py
│   └── dead_code.py
├── models.py      # SQLite schema, scoring, CRUD
├── discovery.py   # GitHub repo discovery engine
└── pipeline.py    # Clone → analyze → score → store
tests/
├── test_models.py
├── test_discovery.py
└── test_pipeline.py
```

## Built With

- Pure Python, minimal dependencies
- SQLite for storage
- Awake's static analyzers for scoring
- GitHub API for discovery

## Development

This project is built autonomously by Computer. Each session picks tasks from the [roadmap](ROADMAP.md), writes code, runs tests, and opens a PR. Progress is logged in [AWAKE_LOG.md](AWAKE_LOG.md).

---

*Built by Computer. Powered by [Awake](https://github.com/gunnargray-dev/Awake).*
