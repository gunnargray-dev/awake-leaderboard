"""Awake Leaderboard -- command-line interface.

Entry point for all leaderboard operations. Uses argparse only (stdlib).

Commands
--------
    awake-lb top [--limit N] [--category CAT] [--sort-by COL]
    awake-lb detail <owner/repo>
    awake-lb refresh <owner/repo> [--session N] [--db PATH]
    awake-lb refresh-all [--session N] [--db PATH]
    awake-lb seed [--session N] [--db PATH]
    awake-lb trends [--limit N] [--sessions N]
    awake-lb categories
    awake-lb stats
    awake-lb compare <owner1/repo1> <owner2/repo2>
    awake-lb digest [--session N]
    awake-lb badge <owner/repo>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Default database path
# ---------------------------------------------------------------------------

DEFAULT_DB = Path(os.environ.get("AWAKE_DB", "leaderboard.db"))


# ---------------------------------------------------------------------------
# Table formatting helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, width: int) -> str:
    """Truncate a string to at most ``width`` characters."""
    if len(text) <= width:
        return text
    return text[:width - 1] + "…"


def _fmt_table(headers: list[str], rows: list[list[str]], col_widths: Optional[list[int]] = None) -> str:
    """Format a simple ASCII table."""
    if col_widths is None:
        col_widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0))
                      for i, h in enumerate(headers)]

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    def _row(cells: list[str]) -> str:
        parts = []
        for i, cell in enumerate(cells):
            w = col_widths[i]
            parts.append(f" {str(cell):<{w}} ")
        return "|" + "|".join(parts) + "|"

    lines = [sep, _row(headers), sep]
    for row in rows:
        lines.append(_row([str(c) for c in row]))
    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def cmd_top(args: argparse.Namespace) -> None:
    """Print the top N projects on the leaderboard."""
    from src.models import init_db, get_leaderboard

    conn = init_db(args.db)
    try:
        rows = get_leaderboard(
            conn,
            limit=args.limit,
            category=args.category or "",
            sort_by=args.sort_by,
        )
    finally:
        conn.close()

    if not rows:
        print("No projects found. Run `awake-lb seed` to populate the leaderboard.")
        return

    headers = ["#", "Project", "Score", "Grade", "Health", "Security", "Complexity", "Stars"]
    table_rows = []
    for i, p in enumerate(rows, 1):
        score = p.get("overall_score") or 0.0
        table_rows.append([
            i,
            _truncate(f"{p['owner']}/{p['repo']}", 40),
            f"{score:.1f}",
            p.get("grade") or "-",
            f"{p.get('health_score') or 0.0:.1f}",
            f"{p.get('security_score') or 0.0:.1f}",
            f"{p.get('complexity_score') or 0.0:.1f}",
            f"{p.get('stars') or 0:,}",
        ])

    print(f"\nAwake Leaderboard -- Top {len(rows)} Projects")
    print(_fmt_table(headers, table_rows, [4, 42, 7, 6, 8, 9, 12, 10]))


def cmd_detail(args: argparse.Namespace) -> None:
    """Print detailed scores for a single project."""
    from src.models import init_db, get_project
    from src.trends import get_trend_summary
    import json

    try:
        owner, repo = args.project.split("/", 1)
    except ValueError:
        print(f"Error: expected 'owner/repo', got '{args.project}'")
        sys.exit(1)

    conn = init_db(args.db)
    try:
        project = get_project(conn, owner, repo)
        if not project:
            print(f"Project {owner}/{repo} not found in database.")
            conn.close()
            sys.exit(1)

        run = conn.execute(
            """SELECT * FROM analysis_runs
               WHERE owner = ? AND repo = ?
               ORDER BY session DESC LIMIT 1""",
            (owner, repo),
        ).fetchone()
        trend = get_trend_summary(conn, owner, repo)
    finally:
        conn.close()

    print(f"\n{'=' * 60}")
    print(f"  {owner}/{repo}")
    print(f"{'=' * 60}")
    print(f"  Description : {_truncate(project.get('description') or '-', 55)}")
    print(f"  Language    : {project.get('language') or '-'}")
    print(f"  Category    : {project.get('category') or '-'}")
    print(f"  Stars       : {project.get('stars', 0):,}")
    print(f"  URL         : {project.get('url', '')}")

    if run:
        run = dict(run)
        print(f"\n  Latest Analysis (Session {run['session']})")
        print(f"  {'─' * 40}")
        print(f"  Overall Score  : {run['overall_score']:.1f}  ({run['grade']})")
        print(f"  Health         : {run['health_score']:.1f}")
        print(f"  Complexity     : {run['complexity_score']:.1f}")
        print(f"  Security       : {run['security_score']:.1f}")
        print(f"  Dead Code      : {run['dead_code_pct'] * 100:.1f}%")
        print(f"  Files Analyzed : {run['files_analyzed']}")
        print(f"  Total Lines    : {run['total_lines']:,}")
        print(f"  Analyzed At    : {run['analyzed_at']}")
    else:
        print("\n  No analysis runs yet.")

    stats = trend.get("stats", {})
    if stats.get("sessions_analyzed", 0) > 1:
        delta = trend.get("delta", {})
        change = delta.get("score_change", 0.0)
        arrow = "▲" if change > 0 else "▼" if change < 0 else "–"
        print(f"\n  Trend ({stats['sessions_analyzed']} sessions): "
              f"min={stats['min_score']} avg={stats['avg_score']} max={stats['max_score']} "
              f"| {arrow} {abs(change):.1f} vs last")


def cmd_refresh(args: argparse.Namespace) -> None:
    """Re-analyze a single project."""
    from src.pipeline import run_pipeline

    try:
        owner, repo = args.project.split("/", 1)
    except ValueError:
        print(f"Error: expected 'owner/repo', got '{args.project}'")
        sys.exit(1)

    from src.models import init_db, get_project
    conn = init_db(args.db)
    try:
        project = get_project(conn, owner, repo)
    finally:
        conn.close()

    if not project:
        print(f"Project {owner}/{repo} not found. Add it first.")
        sys.exit(1)

    url = project["url"]
    print(f"Analyzing {owner}/{repo} (session {args.session})...")

    run = run_pipeline(
        db_path=args.db,
        owner=owner,
        repo=repo,
        url=url,
        session=args.session,
        token=os.environ.get("GITHUB_TOKEN"),
    )
    if run:
        print(f"Done. Score: {run.overall_score:.1f} ({run.grade})")
    else:
        print("Analysis failed.")
        sys.exit(1)


def cmd_refresh_all(args: argparse.Namespace) -> None:
    """Re-analyze all projects in the database."""
    from src.pipeline import run_batch_analysis

    print(f"Running batch analysis for all projects (session {args.session})...")
    result = run_batch_analysis(
        db_path=args.db,
        session=args.session,
        token=os.environ.get("GITHUB_TOKEN"),
    )
    total = result["total"]
    success = result["success"]
    failed = result["failed"]
    print(f"\nDone: {success}/{total} succeeded, {failed} failed")

    if failed > 0:
        print("\nFailed projects:")
        for r in result["results"]:
            if r["status"] == "error":
                print(f"  {r['owner']}/{r['repo']}: {r['error']}")


def cmd_seed(args: argparse.Namespace) -> None:
    """Run the seed pipeline on all 50 curated projects."""
    from src.discovery import get_seed_projects
    from src.pipeline import run_pipeline
    from src.categories import detect_category

    seeds = get_seed_projects()
    print(f"Seeding {len(seeds)} projects (session {args.session})...")

    success = 0
    failed = 0
    for seed in seeds:
        owner = seed["owner"]
        repo = seed["repo"]
        url = seed["url"]
        category = seed.get("category") or detect_category("", "", repo)
        print(f"  {owner}/{repo}...", end=" ", flush=True)
        try:
            run = run_pipeline(
                db_path=args.db,
                owner=owner,
                repo=repo,
                url=url,
                session=args.session,
                category=category,
                token=os.environ.get("GITHUB_TOKEN"),
            )
            if run:
                print(f"{run.overall_score:.1f} ({run.grade})")
                success += 1
            else:
                print("FAILED")
                failed += 1
        except Exception as exc:
            print(f"ERROR: {exc}")
            failed += 1

    print(f"\nDone: {success}/{len(seeds)} succeeded, {failed} failed")


def cmd_trends(args: argparse.Namespace) -> None:
    """Show biggest movers in the last N sessions."""
    from src.models import init_db
    from src.trends import get_movers

    conn = init_db(args.db)
    try:
        movers = get_movers(conn, sessions=args.sessions, limit=args.limit)
    finally:
        conn.close()

    risers = movers.get("risers", [])
    fallers = movers.get("fallers", [])

    print(f"\nBiggest Movers (last {args.sessions} sessions)")
    print("=" * 50)

    if risers:
        print("\n▲ Rising")
        headers = ["Project", "Previous", "Current", "Change"]
        rows = [
            [
                f"{m['owner']}/{m['repo']}",
                f"{m['previous_score']:.1f}",
                f"{m['current_score']:.1f}",
                f"+{m['score_change']:.1f}",
            ]
            for m in risers
        ]
        print(_fmt_table(headers, rows, [40, 10, 10, 8]))

    if fallers:
        print("\n▼ Falling")
        headers = ["Project", "Previous", "Current", "Change"]
        rows = [
            [
                f"{m['owner']}/{m['repo']}",
                f"{m['previous_score']:.1f}",
                f"{m['current_score']:.1f}",
                f"{m['score_change']:.1f}",
            ]
            for m in fallers
        ]
        print(_fmt_table(headers, rows, [40, 10, 10, 8]))

    if not risers and not fallers:
        print("Not enough history to compute trends (need ≥ 2 sessions per project).")


def cmd_categories(args: argparse.Namespace) -> None:
    """List all categories with project counts."""
    from src.models import init_db

    conn = init_db(args.db)
    try:
        rows = conn.execute(
            """SELECT category, COUNT(*) AS cnt
               FROM projects
               GROUP BY category
               ORDER BY cnt DESC"""
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("No projects in database yet.")
        return

    headers = ["Category", "Projects"]
    table_rows = [[r["category"] or "other", r["cnt"]] for r in rows]
    total = sum(r["cnt"] for r in rows)
    table_rows.append(["TOTAL", total])
    print("\nCategory Breakdown")
    print(_fmt_table(headers, table_rows, [25, 10]))


def cmd_stats(args: argparse.Namespace) -> None:
    """Show aggregate leaderboard stats."""
    from src.models import init_db, get_stats

    conn = init_db(args.db)
    try:
        stats = get_stats(conn)
    finally:
        conn.close()

    print("\nAwake Leaderboard Stats")
    print("=" * 30)
    print(f"  Projects      : {stats['total_projects']}")
    print(f"  Analysis runs : {stats['total_runs']}")
    print(f"  Average score : {stats['average_score']}")


def cmd_compare(args: argparse.Namespace) -> None:
    """Compare two projects head-to-head."""
    from src.models import init_db
    from src.compare import compare_from_db

    try:
        owner1, repo1 = args.project_a.split("/", 1)
        owner2, repo2 = args.project_b.split("/", 1)
    except ValueError:
        print("Error: use 'owner/repo' format for both projects")
        sys.exit(1)

    conn = init_db(args.db)
    try:
        result = compare_from_db(conn, owner1, repo1, owner2, repo2)
    finally:
        conn.close()

    if result is None:
        print("One or both projects have no analysis data.")
        sys.exit(1)

    print(result.to_markdown())


def cmd_digest(args: argparse.Namespace) -> None:
    """Generate and print the session digest."""
    from src.models import init_db
    from src.digest import generate_digest

    conn = init_db(args.db)
    try:
        md = generate_digest(conn, session=args.session)
    finally:
        conn.close()

    print(md)


def cmd_generate_json(args: argparse.Namespace) -> None:
    """Generate website/data/leaderboard.json from seed data."""
    from src.generate_leaderboard import generate_leaderboard
    import json

    data = generate_leaderboard()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n")

    total = data["metadata"]["total_projects"]
    scores = [p["score"] for p in data["projects"]]
    avg = sum(scores) / len(scores)
    print(f"Generated {output} with {total} projects (avg score: {avg:.1f})")


def cmd_badge(args: argparse.Namespace) -> None:
    """Print badge URLs and Markdown for a project."""
    from src.models import init_db
    from src.badges import generate_badge_markdown, generate_all_badges

    try:
        owner, repo = args.project.split("/", 1)
    except ValueError:
        print(f"Error: expected 'owner/repo', got '{args.project}'")
        sys.exit(1)

    conn = init_db(args.db)
    try:
        run = conn.execute(
            """SELECT overall_score, grade, health_score,
                      security_score, complexity_score
               FROM analysis_runs
               WHERE owner = ? AND repo = ?
               ORDER BY session DESC LIMIT 1""",
            (owner, repo),
        ).fetchone()
    finally:
        conn.close()

    if not run:
        print(f"No analysis data for {owner}/{repo}.")
        sys.exit(1)

    run = dict(run)
    badges = generate_all_badges(
        owner=owner,
        repo=repo,
        score=run["overall_score"],
        grade=run["grade"],
        health_score=run["health_score"],
        security_score=run["security_score"],
        complexity_score=run["complexity_score"],
    )
    md = generate_badge_markdown(owner, repo, run["overall_score"], run["grade"])

    print(f"\nBadges for {owner}/{repo}")
    print("=" * 50)
    for name, url in badges.items():
        print(f"  {name:<12}: {url}")
    print(f"\n  Markdown: {md}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="awake-lb",
        description="Awake Leaderboard -- score and rank open-source Python projects",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"Path to SQLite database (default: {DEFAULT_DB})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # top
    p_top = sub.add_parser("top", help="Show top projects")
    p_top.add_argument("--limit", type=int, default=20, help="Number of results (default: 20)")
    p_top.add_argument("--category", default="", help="Filter by category")
    p_top.add_argument("--sort-by", dest="sort_by", default="overall_score",
                       choices=["overall_score", "health_score", "complexity_score",
                                "security_score", "stars"],
                       help="Sort column (default: overall_score)")

    # detail
    p_detail = sub.add_parser("detail", help="Show project detail")
    p_detail.add_argument("project", help="owner/repo")

    # refresh
    p_refresh = sub.add_parser("refresh", help="Re-analyze a project")
    p_refresh.add_argument("project", help="owner/repo")
    p_refresh.add_argument("--session", type=int, default=1, help="Session number")

    # refresh-all
    p_refresh_all = sub.add_parser("refresh-all", help="Re-analyze all projects")
    p_refresh_all.add_argument("--session", type=int, default=1, help="Session number")

    # seed
    p_seed = sub.add_parser("seed", help="Seed leaderboard with top Python projects")
    p_seed.add_argument("--session", type=int, default=0, help="Session number (default: 0)")

    # trends
    p_trends = sub.add_parser("trends", help="Show score trends")
    p_trends.add_argument("--limit", type=int, default=10, help="Number of movers (default: 10)")
    p_trends.add_argument("--sessions", type=int, default=5, help="Session window (default: 5)")

    # categories
    sub.add_parser("categories", help="List categories with project counts")

    # stats
    sub.add_parser("stats", help="Show aggregate stats")

    # compare
    p_compare = sub.add_parser("compare", help="Compare two projects")
    p_compare.add_argument("project_a", help="First project: owner/repo")
    p_compare.add_argument("project_b", help="Second project: owner/repo")

    # digest
    p_digest = sub.add_parser("digest", help="Print session digest")
    p_digest.add_argument("--session", type=int, default=None, help="Session (default: latest)")

    # badge
    p_badge = sub.add_parser("badge", help="Print badge URLs for a project")
    p_badge.add_argument("project", help="owner/repo")

    # generate-json
    p_gen = sub.add_parser("generate-json", help="Generate website leaderboard.json")
    p_gen.add_argument("-o", "--output", default="website/data/leaderboard.json",
                       help="Output path (default: website/data/leaderboard.json)")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> None:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    commands = {
        "top": cmd_top,
        "detail": cmd_detail,
        "refresh": cmd_refresh,
        "refresh-all": cmd_refresh_all,
        "seed": cmd_seed,
        "trends": cmd_trends,
        "categories": cmd_categories,
        "stats": cmd_stats,
        "compare": cmd_compare,
        "digest": cmd_digest,
        "badge": cmd_badge,
        "generate-json": cmd_generate_json,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
