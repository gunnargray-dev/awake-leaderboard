"""Dead code detector for Awake.

Scans all Python files in src/ using AST analysis to find:
- Functions that are defined but never called anywhere in the src/ tree
- Classes that are defined but never instantiated or subclassed
- Imports that are brought in but never referenced in the same file

Results are ranked by confidence (HIGH / MEDIUM / LOW) and can be
exported to Markdown, JSON, or HTML via the standard export system.

Public API
----------
- ``DeadItem``   — a single dead-code candidate
- ``DeadCodeReport`` — full report with categorised candidates
- ``find_dead_code(repo_path)`` → ``DeadCodeReport``
- ``save_dead_code_report(report, out_path)``

CLI
---
    awake deadcode [--write] [--json]
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DeadItem:
    """A single dead-code candidate."""

    kind: str          # "function" | "class" | "import"
    name: str          # qualified name, e.g. "health.generate_health_report"
    file: str          # relative path within repo
    line: int          # line number of the definition
    confidence: str    # "HIGH" | "MEDIUM" | "LOW"
    reason: str        # human-readable explanation

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "kind": self.kind,
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass
class DeadCodeReport:
    """Full dead-code analysis report."""

    items: list[DeadItem] = field(default_factory=list)
    repo_path: str = ""
    files_scanned: int = 0

    # ---------------------------------------------------------------------------
    # Derived helpers
    # ---------------------------------------------------------------------------

    @property
    def dead_functions(self) -> list[DeadItem]:
        """Items of kind 'function'."""
        return [i for i in self.items if i.kind == "function"]

    @property
    def dead_classes(self) -> list[DeadItem]:
        """Items of kind 'class'."""
        return [i for i in self.items if i.kind == "class"]

    @property
    def dead_imports(self) -> list[DeadItem]:
        """Items of kind 'import'."""
        return [i for i in self.items if i.kind == "import"]

    @property
    def high_confidence(self) -> list[DeadItem]:
        """Items with HIGH confidence."""
        return [i for i in self.items if i.confidence == "HIGH"]

    # ---------------------------------------------------------------------------
    # Rendering
    # ---------------------------------------------------------------------------

    def to_markdown(self) -> str:
        """Render the report as a Markdown string."""
        lines: list[str] = []
        lines.append("# Dead Code Report\n")
        lines.append(f"**Repo:** `{self.repo_path}`  ")
        lines.append(f"**Files scanned:** {self.files_scanned}  ")
        lines.append(f"**Candidates found:** {len(self.items)}\n")

        if not self.items:
            lines.append("_No dead-code candidates found. 🎉_\n")
            return "\n".join(lines)

        lines.append("## Summary\n")
        lines.append("| Category | Count |")
        lines.append("|----------|-------|")
        lines.append(f"| Dead functions | {len(self.dead_functions)} |")
        lines.append(f"| Dead classes | {len(self.dead_classes)} |")
        lines.append(f"| Unused imports | {len(self.dead_imports)} |")
        lines.append(f"| HIGH confidence | {len(self.high_confidence)} |")
        lines.append("")

        for section_title, section_items in [
            ("Functions", self.dead_functions),
            ("Classes", self.dead_classes),
            ("Imports", self.dead_imports),
        ]:
            if not section_items:
                continue
            lines.append(f"## {section_title}\n")
            lines.append("| Name | File | Line | Confidence | Reason |")
            lines.append("|------|------|------|------------|--------|")
            for item in sorted(section_items, key=lambda i: (i.confidence, i.file, i.line)):
                lines.append(
                    f"| `{item.name}` | `{item.file}` | {item.line} "
                    f"| {item.confidence} | {item.reason} |"
                )
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "repo_path": self.repo_path,
            "files_scanned": self.files_scanned,
            "total_candidates": len(self.items),
            "dead_functions": len(self.dead_functions),
            "dead_classes": len(self.dead_classes),
            "dead_imports": len(self.dead_imports),
            "high_confidence": len(self.high_confidence),
            "items": [i.to_dict() for i in self.items],
        }

    def to_json(self) -> str:
        """Serialise to a JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# AST collectors
# ---------------------------------------------------------------------------


class _NameCollector(ast.NodeVisitor):
    """Collect every Name/Attribute reference used in a module."""

    def __init__(self) -> None:
        self.used: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        """Record a Name node reference as used"""
        self.used.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        """Record an Attribute node reference as used"""
        self.used.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Visit a Call node and recurse into its children"""
        self.generic_visit(node)


class _DefCollector(ast.NodeVisitor):
    """Collect top-level function/class definitions and imports in a module."""

    def __init__(self) -> None:
        self.functions: list[tuple[str, int]] = []   # (name, lineno)
        self.classes: list[tuple[str, int]] = []
        self.imports: list[tuple[str, int]] = []     # (alias, lineno)
        self._depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """Record a top-level function definition and recurse"""
        if self._depth == 0:
            self.functions.append((node.name, node.lineno))
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """Record a top-level class definition and recurse"""
        if self._depth == 0:
            self.classes.append((node.name, node.lineno))
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """Record imported names from an import statement"""
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".")[0]
            self.imports.append((local_name, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """Record imported names from a from-import statement"""
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            self.imports.append((local_name, node.lineno))
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def _parse_file(py_file: Path) -> Optional[ast.Module]:
    """Parse *py_file* and return its AST, or None on syntax error."""
    from src._ast_utils import parse_file
    return parse_file(py_file)


def find_dead_code(repo_path: Optional[Path] = None) -> DeadCodeReport:
    """Find dead-code candidates across all src/ Python files.

    Strategy
    --------
    1. Parse every ``src/*.py`` file and collect all defined names and all
       *used* names.
    2. Build a global ``used`` set from **all** files combined (so a function
       used only in cli.py is not flagged as dead just because it is defined
       in another module).
    3. Definitions whose name never appears anywhere in the global used-names
       set are HIGH confidence candidates.
    4. Dunder names (``__init__``, ``__str__``, …), ``main``, and names
       prefixed with ``_`` are excluded from function/class candidates to
       reduce false positives.
    5. Imports whose local alias is not used within the *same* file are
       flagged with MEDIUM confidence.

    Note: This is intentionally conservative.  We do not flag anything used
    via ``getattr`` or dynamic dispatch.
    """
    if repo_path is None:
        repo_path = Path(__file__).resolve().parent.parent
    repo_path = Path(repo_path)
    src_dir = repo_path / "src"

    report = DeadCodeReport(repo_path=str(repo_path))

    if not src_dir.exists():
        return report

    py_files = sorted(
        f for f in src_dir.rglob("*.py")
        if not f.name.startswith("_")
    )
    report.files_scanned = len(py_files)

    # ---- Pass 1: collect defs and uses per file ----
    per_file_defs: dict[Path, _DefCollector] = {}
    per_file_uses: dict[Path, _NameCollector] = {}
    global_uses: set[str] = set()

    for py_file in py_files:
        tree = _parse_file(py_file)
        if tree is None:
            continue
        defs = _DefCollector()
        uses = _NameCollector()
        defs.visit(tree)
        uses.visit(tree)
        per_file_defs[py_file] = defs
        per_file_uses[py_file] = uses
        global_uses.update(uses.used)

    # ---- Pass 2: flag dead functions/classes ----
    _SKIP_PREFIXES = ("_",)
    _SKIP_NAMES = {"main", "setup", "teardown"}

    for py_file, defs in per_file_defs.items():
        rel = str(py_file.relative_to(repo_path))
        module_name = py_file.stem

        for fname, lineno in defs.functions:
            if fname.startswith("_") or fname in _SKIP_NAMES:
                continue
            if fname not in global_uses:
                report.items.append(
                    DeadItem(
                        kind="function",
                        name=f"{module_name}.{fname}",
                        file=rel,
                        line=lineno,
                        confidence="HIGH",
                        reason="Never called in any src/ file",
                    )
                )

        for cname, lineno in defs.classes:
            if cname.startswith("_"):
                continue
            if cname not in global_uses:
                report.items.append(
                    DeadItem(
                        kind="class",
                        name=f"{module_name}.{cname}",
                        file=rel,
                        line=lineno,
                        confidence="HIGH",
                        reason="Never instantiated or referenced in any src/ file",
                    )
                )

    # ---- Pass 3: flag unused imports (per-file) ----
    for py_file, defs in per_file_defs.items():
        rel = str(py_file.relative_to(repo_path))
        local_uses = per_file_uses.get(py_file, _NameCollector()).used

        for alias, lineno in defs.imports:
            if alias.startswith("_"):
                continue
            if alias not in local_uses:
                report.items.append(
                    DeadItem(
                        kind="import",
                        name=alias,
                        file=rel,
                        line=lineno,
                        confidence="MEDIUM",
                        reason="Imported but never referenced in this file",
                    )
                )

    return report


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_dead_code_report(report: DeadCodeReport, out_path: Path) -> None:
    """Write the dead-code report as Markdown + JSON sidecar to *out_path*."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(report.to_json(), encoding="utf-8")
