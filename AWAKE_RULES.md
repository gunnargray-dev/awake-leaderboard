# Awake Rules

These rules govern the autonomous development of Awake Leaderboard by Computer.

## Operating System

1. **One feature per PR, atomic changes.** Each PR should do one thing well.
2. **PR descriptions should be detailed enough to be interesting Twitter content.** Every session = content for one tweet in a thread documenting the build.
3. **Pure Python, minimal dependencies.** Stdlib first, pip install last.
4. **Tests for everything.** No code ships without tests.
5. **The data is the moat.** Every session should add more projects, update scores, or track trends.

## Session Protocol

1. Read repo state (ROADMAP.md, AWAKE_LOG.md)
2. Pick next item(s) from the roadmap
3. Create a feature branch (`session{N}-{slug}`)
4. Write code + tests
5. Open a PR with a detailed description
6. Merge (squash)
7. Update AWAKE_LOG.md with session entry
8. Update ROADMAP.md to check off completed items

## Code Standards

- All public functions have docstrings
- Type hints on function signatures
- f-strings over .format()
- pathlib.Path over os.path
- dataclasses over dicts for structured data

## Scoring Weights

| Analyzer | Weight |
|----------|--------|
| Health | 30% |
| Security | 25% |
| Complexity | 20% |
| Coverage | 15% |
| Dead Code | 10% |
