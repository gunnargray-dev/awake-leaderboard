"""Cyclomatic complexity analyzer for Awake.

Walks all Python files in ``src/`` using AST analysis to compute McCabe
cyclomatic complexity for every function and async function definition.

Complexity is counted as:
- Base of 1 per function
- +1 for each ``if``, ``elif``, ``for``, ``while``, ``except``, ``with``
- +1 for each boolean operator (``and`` / ``or``) in an ``ast.BoolOp``
- +1 for each ``assert`` statement
- +1 for each list, dict, or set comprehension (``ListComp``, ``DictComp``,
  ``SetComp``, ``GeneratorExp``)
- +1 for each ternary (``IfExp``)

Ranks are assigned as:
- LOW:    1–5
- MEDIUM: 6–14
- HIGH:   15+

Public API
----------
- ``FunctionComplexity`` — per-function result
- ``ComplexityReport``   — full report with aggregate helpers
- ``analyze_complexity(repo_path)``  → ``ComplexityReport``
- ``save_complexity_report(report, output_path)``

CLI
---
    awake complexity [--write] [--json]
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Complexity thresholds (inclusive lower bounds)
_HIGH_THRESHOLD = 15
_MEDIUM_THRESHOLD = 6

#: Node types that each add 1 to complexity
_DECISION_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.AsyncWith,
    ast.With,
    ast.Assert,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
    ast.GeneratorExp,
    ast.IfExp,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FunctionComplexity:
    """Cyclomatic complexity result for a single function or method.

    Attributes
    ----------
    function:
        Qualified function name (e.g. ``"MyClass.my_method"`` or ``"my_func"``).
    file:
        Relative path of the source file within the repository.
    line:
        Line number of the function definition (1-based).
    complexity:
        McCabe cyclomatic complexity score (>= 1).
    rank:
        Human-readable tier: ``"HIGH"``, ``"MEDIUM"``, or ``"LOW"``.
    """

    function: str
    file: str
    line: int
    complexity: int
    rank: str

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "function": self.function,
            "file": self.file,
            "line": self.line,
            "complexity": self.complexity,
            "rank": self.rank,
        }


@dataclass
class ComplexityReport:
    """Full cyclomatic-complexity analysis report.

    Attributes
    ----------
    results:
        Per-function complexity entries, sorted by descending complexity.
    repo_path:
        Absolute path of the analysed repository (as a string).
    files_scanned:
        Number of Python source files parsed during analysis.
    """

    results: list[FunctionComplexity] = field(default_factory=list)
    repo_path: str = ""
    files_scanned: int = 0

    # ---------------------------------------------------------------------------
    # Derived helpers
    # ---------------------------------------------------------------------------

    @property
    def total_functions(self) -> int:
        """Total number of functions analysed."""
        return len(self.results)

    @property
    def avg_complexity(self) -> float:
        """Mean cyclomatic complexity across all functions (0.0 if none)."""
        if not self.results:
            return 0.0
        return round(sum(r.complexity for r in self.results) / len(self.results), 2)

    @property
    def high_count(self) -> int:
        """Number of functions with complexity >= 15 (HIGH)."""
        return sum(1 for r in self.results if r.rank == "HIGH")

    @property
    def medium_count(self) -> int:
        """Number of functions with complexity in 6–14 (MEDIUM)."""
        return sum(1 for r in self.results if r.rank == "MEDIUM")

    @property
    def low_count(self) -> int:
        """Number of functions with complexity in 1–5 (LOW)."""
        return sum(1 for r in self.results if r.rank == "LOW")

    @property
    def average_complexity(self) -> float:
        """Alias for avg_complexity for pipeline compatibility."""
        return self.avg_complexity

    @property
    def max_complexity(self) -> int:
        """Maximum complexity across all functions."""
        if not self.results:
            return 0
        return max(r.complexity for r in self.results)

    @property
    def functions(self) -> list:
        """Alias for results for pipeline compatibility."""
        return self.results

    # ---------------------------------------------------------------------------
    # Rendering
    # ---------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "repo_path": self.repo_path,
            "files_scanned": self.files_scanned,
            "total_functions": self.total_functions,
            "avg_complexity": self.avg_complexity,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self) -> str:
        """Serialise to a pretty-printed JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Render the report as a Markdown string."""
        lines: list[str] = []
        lines.append("# Cyclomatic Complexity Report\n")
        lines.append(f"**Repo:** `{self.repo_path}`  ")
        lines.append(f"**Files scanned:** {self.files_scanned}  ")
        lines.append(f"**Functions analysed:** {self.total_functions}\n")

        if not self.results:
            lines.append("_No functions found._\n")
            return "\n".join(lines)

        lines.append("## Summary\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Average complexity | {self.avg_complexity:.1f} |")
        lines.append(f"| HIGH (>= 15) | {self.high_count} |")
        lines.append(f"| MEDIUM (6–14) | {self.medium_count} |")
        lines.append(f"| LOW (1–5) | {self.low_count} |")
        lines.append("")

        if self.high_count:
            lines.append("## HIGH Complexity Functions\n")
            lines.append("| Function | File | Line | Complexity |")
            lines.append("|----------|------|------|------------|")
            for r in self.results:
                if r.rank == "HIGH":
                    lines.append(
                        f"| `{r.function}` | `{r.file}` | {r.line} | {r.complexity} |"
                    )
            lines.append("")

        if self.medium_count:
            lines.append("## MEDIUM Complexity Functions\n")
            lines.append("| Function | File | Line | Complexity |")
            lines.append("|----------|------|------|------------|")
            for r in self.results:
                if r.rank == "MEDIUM":
                    lines.append(
                        f"| `{r.function}` | `{r.file}` | {r.line} | {r.complexity} |"
                    )
            lines.append("")

        lines.append("## All Functions\n")
        lines.append("| Function | File | Line | Complexity | Rank |")
        lines.append("|----------|------|------|------------|------|")
        for r in self.results:
            lines.append(
                f"| `{r.function}` | `{r.file}` | {r.line} | {r.complexity} | {r.rank} |"
            )
        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# AST complexity visitor
# ---------------------------------------------------------------------------


class _ComplexityVisitor(ast.NodeVisitor):
    """Compute cyclomatic complexity for a single function node.

    Intended to be used on the *body statements* of a function, not on the
    function node itself.  Any nested ``FunctionDef`` / ``AsyncFunctionDef``
    encountered during traversal is skipped so that inner functions do not
    inflate the outer function's score.

    Boolean operators are weighted by the number of operands minus 1, since
    each additional operand introduces one more branch.
    """

    def __init__(self) -> None:
        # Start at 1 (the single entry path through the function)
        self.complexity: int = 1

    def _count(self, node: ast.AST) -> None:
        """Increment complexity and recurse into children."""
        self.complexity += 1
        self.generic_visit(node)

    # --- decision-point nodes ---

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        """Count the ``if`` branch; elif chains are nested If nodes."""
        self._count(node)

    def visit_For(self, node: ast.For) -> None:  # noqa: N802
        """Count a ``for`` loop."""
        self._count(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:  # noqa: N802
        """Count an ``async for`` loop."""
        self._count(node)

    def visit_While(self, node: ast.While) -> None:  # noqa: N802
        """Count a ``while`` loop."""
        self._count(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        """Count each ``except`` clause."""
        self._count(node)

    def visit_With(self, node: ast.With) -> None:  # noqa: N802
        """Count a ``with`` statement."""
        self._count(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:  # noqa: N802
        """Count an ``async with`` statement."""
        self._count(node)

    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        """Count an ``assert`` statement."""
        self._count(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:  # noqa: N802
        """Count a list comprehension."""
        self._count(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:  # noqa: N802
        """Count a dict comprehension."""
        self._count(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:  # noqa: N802
        """Count a set comprehension."""
        self._count(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:  # noqa: N802
        """Count a generator expression."""
        self._count(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:  # noqa: N802
        """Count a ternary expression (``x if cond else y``)."""
        self._count(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:  # noqa: N802
        """Count each additional boolean operand as a branch.

        ``a and b`` → +1 (two operands, one extra branch)
        ``a and b and c`` → +2
        """
        # Each additional operand beyond the first adds a branch
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    # --- nested function / class definitions are NOT counted in the outer scope ---

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """Skip nested function definitions entirely.

        Nested functions are analysed independently by :func:`_analyse_tree`;
        their decision points must not be counted toward the outer function.
        """
        # Do NOT call generic_visit — stop traversal into this sub-tree.
        pass

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """Skip nested class definitions entirely.

        Methods defined inside nested classes are collected by the top-level
        ``ast.walk`` in :func:`_analyse_tree` and analysed independently.
        """
        pass


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------


def _rank(complexity: int) -> str:
    """Classify a complexity score into a rank string."""
    if complexity >= _HIGH_THRESHOLD:
        return "HIGH"
    if complexity >= _MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def _parse_file(py_file: Path) -> Optional[ast.Module]:
    """Parse *py_file* and return its AST, or ``None`` on syntax error."""
    from src._ast_utils import parse_file
    return parse_file(py_file)


def _analyse_tree(
    tree: ast.Module,
    rel_path: str,
) -> list[FunctionComplexity]:
    """Extract per-function complexity records from a parsed module AST.

    Walks the top-level AST to find all ``FunctionDef`` and
    ``AsyncFunctionDef`` nodes (including methods inside classes).
    For each, a dedicated :class:`_ComplexityVisitor` computes complexity
    so that nested functions/classes do not inflate the outer score.

    Args:
        tree: Parsed AST of a Python source file.
        rel_path: Repository-relative file path (used in the result records).

    Returns:
        List of :class:`FunctionComplexity` entries, one per function.
    """
    entries: list[FunctionComplexity] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        visitor = _ComplexityVisitor()
        # We visit the body of the function, not the function node itself
        # so that the outermost visit_FunctionDef guard works correctly.
        for child in ast.iter_child_nodes(node):
            visitor.visit(child)

        complexity = visitor.complexity
        entries.append(
            FunctionComplexity(
                function=node.name,
                file=rel_path,
                line=node.lineno,
                complexity=complexity,
                rank=_rank(complexity),
            )
        )

    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_complexity(repo_path: Optional[Path] = None) -> ComplexityReport:
    """Compute cyclomatic complexity for every function in ``src/``.

    Scans all ``*.py`` files under ``<repo_path>/src/`` (recursively),
    parses each with Python's :mod:`ast` module, and measures McCabe
    cyclomatic complexity per function.

    Files that fail to parse due to syntax errors are silently skipped.

    Args:
        repo_path:
            Root of the repository.  Defaults to the parent of the directory
            containing this module (i.e. the repository root when installed
            normally).

    Returns:
        :class:`ComplexityReport` with all per-function results and
        aggregate statistics.
    """
    if repo_path is None:
        repo_path = Path(__file__).resolve().parent.parent
    repo_path = Path(repo_path)
    src_dir = repo_path / "src"

    report = ComplexityReport(repo_path=str(repo_path))

    if not src_dir.exists():
        return report

    py_files = sorted(src_dir.rglob("*.py"))
    parsed_count = 0

    all_results: list[FunctionComplexity] = []

    for py_file in py_files:
        tree = _parse_file(py_file)
        if tree is None:
            continue
        parsed_count += 1
        rel_path = str(py_file.relative_to(repo_path))
        entries = _analyse_tree(tree, rel_path)
        all_results.extend(entries)

    # Sort by descending complexity, then file, then line for stable ordering
    all_results.sort(key=lambda r: (-r.complexity, r.file, r.line))

    report.results = all_results
    report.files_scanned = parsed_count
    return report


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_complexity_report(report: ComplexityReport, output_path: Path) -> None:
    """Write the complexity report as Markdown + JSON sidecar.

    Creates parent directories as needed.

    Args:
        report: The :class:`ComplexityReport` to serialise.
        output_path: Destination path for the Markdown file.  A ``.json``
            sidecar is written alongside it automatically.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path = output_path.with_suffix(".json")
    json_path.write_text(report.to_json(), encoding="utf-8")
