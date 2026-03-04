"""Code health monitor for Awake.

Analyzes the repository's source code for quality metrics:
- Line count per file and totals
- Function/class count (complexity proxy)
- TODO/FIXME/HACK comment density
- Long line violations (>88 chars, PEP 8 relaxed limit)
- Blank line ratio (readability proxy)
- Docstring coverage (% of public functions with docstrings)
- Overall health score (0–100)

Produces a structured HealthReport that can be rendered as Markdown
for inclusion in AWAKE_LOG.md or saved as health_report.md.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileHealth:
    """Health metrics for a single Python source file."""

    path: str
    total_lines: int = 0
    code_lines: int = 0
    blank_lines: int = 0
    comment_lines: int = 0
    long_lines: int = 0          # lines > MAX_LINE_LENGTH
    function_count: int = 0
    class_count: int = 0
    todo_count: int = 0          # TODO / FIXME / HACK / XXX markers
    docstring_coverage: float = 0.0   # 0.0–1.0
    parse_error: bool = False

    def to_dict(self) -> dict:
        """Return a dictionary representation of this file's health metrics"""
        return asdict(self)

    @property
    def health_score(self) -> float:
        """Compute a 0–100 health score for this file.

        Penalties (applied as subtractions from 100):
        - Each long line:        -0.5 pts (capped at -20)
        - Each TODO/FIXME:       -2 pts   (capped at -20)
        - Low docstring coverage:-up to 20 pts
        - Parse error:           -50 pts
        """
        if self.parse_error:
            return 50.0

        score = 100.0

        # Long lines penalty
        long_penalty = min(self.long_lines * 0.5, 20.0)
        score -= long_penalty

        # TODO/FIXME penalty
        todo_penalty = min(self.todo_count * 2.0, 20.0)
        score -= todo_penalty

        # Docstring coverage penalty (max -20 for 0% coverage)
        doc_penalty = (1.0 - self.docstring_coverage) * 20.0
        score -= doc_penalty

        return max(0.0, round(score, 1))


@dataclass
class HealthReport:
    """Aggregate health report for the repository."""

    files: list[FileHealth] = field(default_factory=list)
    generated_at: str = ""

    def to_dict(self) -> dict:
        """Return a dictionary representation of the aggregate health report"""
        return asdict(self)

    @property
    def total_lines(self) -> int:
        """Return the sum of total lines across all analyzed files"""
        return sum(f.total_lines for f in self.files)

    @property
    def total_code_lines(self) -> int:
        """Return the sum of code lines across all analyzed files"""
        return sum(f.code_lines for f in self.files)

    @property
    def total_functions(self) -> int:
        """Return the sum of function counts across all analyzed files"""
        return sum(f.function_count for f in self.files)

    @property
    def total_classes(self) -> int:
        """Return the sum of class counts across all analyzed files"""
        return sum(f.class_count for f in self.files)

    @property
    def total_todos(self) -> int:
        """Return the sum of TODO/FIXME markers across all analyzed files"""
        return sum(f.todo_count for f in self.files)

    @property
    def total_long_lines(self) -> int:
        """Return the sum of long line violations across all analyzed files"""
        return sum(f.long_lines for f in self.files)

    @property
    def overall_docstring_coverage(self) -> float:
        """Weighted average docstring coverage across all files."""
        if not self.files:
            return 0.0
        weighted = sum(
            f.docstring_coverage * max(f.function_count + f.class_count, 1)
            for f in self.files
        )
        total_items = sum(
            max(f.function_count + f.class_count, 1) for f in self.files
        )
        return round(weighted / total_items, 3) if total_items else 0.0

    @property
    def overall_health_score(self) -> float:
        """Average health score across all analyzed files."""
        if not self.files:
            return 100.0
        return round(sum(f.health_score for f in self.files) / len(self.files), 1)

    @property
    def overall_score(self) -> float:
        """Alias for overall_health_score for pipeline compatibility."""
        return self.overall_health_score

    def to_markdown(self) -> str:
        """Render the health report as Markdown."""
        lines = [
            "# Code Health Report",
            "",
            f"*Generated: {self.generated_at or 'N/A'}*",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Overall health score | **{self.overall_health_score}/100** |",
            f"| Total source lines | {self.total_lines} |",
            f"| Code lines | {self.total_code_lines} |",
            f"| Functions | {self.total_functions} |",
            f"| Classes | {self.total_classes} |",
            f"| Docstring coverage | {self.overall_docstring_coverage:.1%} |",
            f"| TODO/FIXME markers | {self.total_todos} |",
            f"| Long lines (>88 chars) | {self.total_long_lines} |",
            "",
            "## Per-File Breakdown",
            "",
            "| File | Lines | Score | Docstrings | TODOs | Long Lines |",
            "|------|-------|-------|------------|-------|-----------|",
        ]

        for fh in sorted(self.files, key=lambda f: f.path):
            score_str = f"{fh.health_score}/100"
            doc_str = f"{fh.docstring_coverage:.0%}"
            lines.append(
                f"| `{fh.path}` | {fh.total_lines} | {score_str} | {doc_str} | {fh.todo_count} | {fh.long_lines} |"
            )

        lines += ["", "---", ""]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

MAX_LINE_LENGTH = 88
TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)


def _count_docstring_coverage(tree: ast.Module) -> float:
    """Return the fraction of public functions/classes/methods with docstrings."""
    total = 0
    documented = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Skip private/dunder items
            if node.name.startswith("_"):
                continue
            total += 1
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                documented += 1

    if total == 0:
        return 1.0  # No public items → full coverage by convention
    return round(documented / total, 3)


def _count_ast_items(tree: ast.Module) -> tuple[int, int]:
    """Return (function_count, class_count) from a parsed AST."""
    functions = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    classes = sum(
        1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    )
    return functions, classes


def analyze_file(path: Path) -> FileHealth:
    """Analyze a single Python source file and return a FileHealth record."""
    fh = FileHealth(path=str(path))

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        fh.parse_error = True
        return fh

    raw_lines = source.splitlines()
    fh.total_lines = len(raw_lines)

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            fh.blank_lines += 1
        elif stripped.startswith("#"):
            fh.comment_lines += 1
        else:
            fh.code_lines += 1

        if len(line) > MAX_LINE_LENGTH:
            fh.long_lines += 1

        if TODO_PATTERN.search(line):
            fh.todo_count += 1

    # AST-based analysis
    try:
        tree = ast.parse(source, filename=str(path))
        fh.function_count, fh.class_count = _count_ast_items(tree)
        fh.docstring_coverage = _count_docstring_coverage(tree)
    except SyntaxError:
        fh.parse_error = True

    return fh


def analyze_directory(
    root: Path,
    glob: str = "src/**/*.py",
    exclude: Optional[list[str]] = None,
) -> list[FileHealth]:
    """Analyze all Python files matching a glob pattern under root."""
    exclude_patterns = exclude or []
    results = []

    for py_file in sorted(root.glob(glob)):
        # Skip excluded patterns
        rel = py_file.relative_to(root)
        if any(ex in str(rel) for ex in exclude_patterns):
            continue
        fh = analyze_file(py_file)
        # Store relative path for readability
        fh.path = str(rel)
        results.append(fh)

    return results


def generate_health_report(
    repo_path: Optional[Path] = None,
    *,
    glob: str = "src/**/*.py",
    exclude: Optional[list[str]] = None,
    timestamp: str = "",
) -> HealthReport:
    """Generate a full health report for the repository.

    Args:
        repo_path: Root of the repository. Defaults to CWD.
        glob: Glob pattern for Python source files.
        exclude: List of path substrings to exclude from analysis.
        timestamp: ISO timestamp string for the report header.

    Returns:
        HealthReport with per-file and aggregate metrics.
    """
    from datetime import datetime, timezone

    root = repo_path or Path.cwd()
    files = analyze_directory(root, glob=glob, exclude=exclude or ["__init__"])
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return HealthReport(files=files, generated_at=ts)


def save_health_report(report: HealthReport, output_path: Path) -> None:
    """Write the health report Markdown to disk."""
    output_path.write_text(report.to_markdown(), encoding="utf-8")


# Alias for pipeline compatibility
analyze_health = generate_health_report
