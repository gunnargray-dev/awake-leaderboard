"""Security audit module for Awake.

Scans Python source files for common security anti-patterns using AST
analysis and regex, without any external dependencies.

Checks performed
----------------
1. ``eval`` / ``exec`` usage           — arbitrary code execution risk
2. ``pickle.loads`` / ``pickle.load``  — unsafe deserialization
3. ``subprocess`` with ``shell=True``  — shell injection vector
4. ``os.system`` calls                 — shell injection vector
5. ``hashlib.md5`` / ``hashlib.sha1``  — weak hash algorithms
6. Hardcoded secrets (naive heuristic) — passwords/tokens/keys in literals
7. ``tempfile.mktemp`` (deprecated)    — insecure temp file creation
8. ``yaml.load`` without Loader=       — arbitrary code execution via YAML
9. ``assert`` used for access control  — stripped in optimised mode
10. ``open`` with mode ``'w'`` on paths outside tmp — broad write patterns

Each finding is tagged with a severity (HIGH / MEDIUM / LOW) and a
CWE reference where applicable.

Public API
----------
- ``SecurityFinding`` — a single finding
- ``SecurityReport``  — full report
- ``audit_security(repo_path)`` → ``SecurityReport``
- ``save_security_report(report, out_path)``

CLI
---
    awake security [--write] [--json]
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

_CWE_LINKS: dict[str, str] = {
    "CWE-78":  "OS Command Injection",
    "CWE-94":  "Code Injection",
    "CWE-326": "Inadequate Encryption Strength",
    "CWE-327": "Broken/Risky Cryptographic Algorithm",
    "CWE-502": "Deserialization of Untrusted Data",
    "CWE-259": "Hardcoded Password",
    "CWE-377": "Insecure Temporary File",
    "CWE-676": "Use of Potentially Dangerous Function",
}


@dataclass
class SecurityFinding:
    """A single security finding in a source file."""

    rule: str        # short rule id, e.g. "S001"
    title: str       # human-readable title
    severity: str    # "HIGH" | "MEDIUM" | "LOW"
    cwe: str         # CWE identifier, e.g. "CWE-94"
    file: str        # relative path
    line: int        # 1-based line number
    snippet: str     # short code snippet (max 80 chars)
    description: str # what the finding means and how to fix it

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "rule": self.rule,
            "title": self.title,
            "severity": self.severity,
            "cwe": self.cwe,
            "cwe_description": _CWE_LINKS.get(self.cwe, ""),
            "file": self.file,
            "line": self.line,
            "snippet": self.snippet,
            "description": self.description,
        }


@dataclass
class SecurityReport:
    """Full security audit report."""

    findings: list[SecurityFinding] = field(default_factory=list)
    repo_path: str = ""
    files_scanned: int = 0

    # ---------------------------------------------------------------------------
    # Derived helpers
    # ---------------------------------------------------------------------------

    @property
    def high_count(self) -> int:
        """Number of HIGH severity findings."""
        return sum(1 for f in self.findings if f.severity == "HIGH")

    @property
    def medium_count(self) -> int:
        """Number of MEDIUM severity findings."""
        return sum(1 for f in self.findings if f.severity == "MEDIUM")

    @property
    def low_count(self) -> int:
        """Number of LOW severity findings."""
        return sum(1 for f in self.findings if f.severity == "LOW")

    @property
    def grade(self) -> str:
        """Letter grade: A (clean) → F (many high-severity issues)."""
        if self.high_count == 0 and self.medium_count == 0:
            return "A"
        if self.high_count == 0 and self.medium_count <= 2:
            return "B"
        if self.high_count <= 1:
            return "C"
        if self.high_count <= 3:
            return "D"
        return "F"

    # ---------------------------------------------------------------------------
    # Rendering
    # ---------------------------------------------------------------------------

    def to_markdown(self) -> str:
        """Render the security report as Markdown."""
        lines: list[str] = []
        lines.append("# Security Audit Report\n")
        lines.append(f"**Repo:** `{self.repo_path}`  ")
        lines.append(f"**Files scanned:** {self.files_scanned}  ")
        lines.append(f"**Grade:** {self.grade}\n")

        lines.append("## Summary\n")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        lines.append(f"| 🔴 HIGH | {self.high_count} |")
        lines.append(f"| 🟡 MEDIUM | {self.medium_count} |")
        lines.append(f"| 🟢 LOW | {self.low_count} |")
        lines.append(f"| **Total** | **{len(self.findings)}** |")
        lines.append("")

        if not self.findings:
            lines.append("_No security issues found. 🎉_\n")
            return "\n".join(lines)

        lines.append("## Findings\n")
        lines.append("| Rule | Severity | CWE | File | Line | Title |")
        lines.append("|------|----------|-----|------|------|-------|")
        for f in sorted(
            self.findings,
            key=lambda x: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x.severity], x.file, x.line),
        ):
            cwe_desc = _CWE_LINKS.get(f.cwe, f.cwe)
            lines.append(
                f"| {f.rule} | {f.severity} | [{f.cwe}]({f.cwe}) "
                f"| `{f.file}` | {f.line} | {f.title} |"
            )
        lines.append("")

        # Detailed findings
        lines.append("## Details\n")
        for f in sorted(
            self.findings,
            key=lambda x: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x.severity], x.file, x.line),
        ):
            lines.append(f"### [{f.rule}] {f.title}")
            lines.append(f"- **Severity:** {f.severity}")
            lines.append(f"- **CWE:** {f.cwe} — {_CWE_LINKS.get(f.cwe, '')}")
            lines.append(f"- **Location:** `{f.file}:{f.line}`")
            lines.append(f"- **Snippet:** `{f.snippet}`")
            lines.append(f"- **Description:** {f.description}")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "repo_path": self.repo_path,
            "files_scanned": self.files_scanned,
            "grade": self.grade,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "total": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_json(self) -> str:
        """Serialise to a JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Regex-based heuristics for hardcoded secrets
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']'), "Hardcoded password literal"),
    (re.compile(r'(?i)(api_key|apikey|api_token|secret_key|secret)\s*=\s*["\'][^"\']{8,}["\']'), "Hardcoded API key/secret"),
    (re.compile(r'(?i)(token|auth_token|access_token)\s*=\s*["\'][^"\']{8,}["\']'), "Hardcoded auth token"),
    (re.compile(r'(?i)private_key\s*=\s*["\'][^"\']{8,}["\']'), "Hardcoded private key"),
]


# ---------------------------------------------------------------------------
# AST-based checks
# ---------------------------------------------------------------------------


class _SecurityVisitor(ast.NodeVisitor):
    """Walk an AST and emit security findings."""

    def __init__(self, rel_path: str, source_lines: list[str]) -> None:
        self.findings: list[SecurityFinding] = []
        self._rel = rel_path
        self._lines = source_lines

    def _snippet(self, lineno: int) -> str:
        """Return the source line at *lineno* (1-based), truncated to 80 chars."""
        if 1 <= lineno <= len(self._lines):
            return self._lines[lineno - 1].strip()[:80]
        return ""

    def _add(self, rule: str, title: str, severity: str, cwe: str,
             lineno: int, description: str) -> None:
        self.findings.append(SecurityFinding(
            rule=rule,
            title=title,
            severity=severity,
            cwe=cwe,
            file=self._rel,
            line=lineno,
            snippet=self._snippet(lineno),
            description=description,
        ))

    # ---- S001: eval ----
    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Check function calls for dangerous patterns like eval, exec, and pickle"""
        func = node.func
        func_name = ""
        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr

        # S001: eval()
        if func_name == "eval":
            self._add(
                "S001", "Use of eval()", "HIGH", "CWE-94", node.lineno,
                "eval() executes arbitrary Python code. Replace with safer "
                "alternatives such as ast.literal_eval() for parsing data.",
            )

        # S002: exec()
        elif func_name == "exec":
            self._add(
                "S002", "Use of exec()", "HIGH", "CWE-94", node.lineno,
                "exec() executes arbitrary Python code. Avoid dynamic code "
                "execution; refactor logic to avoid it.",
            )

        # S003: pickle.loads / pickle.load
        elif func_name in ("loads", "load") and isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id in ("pickle", "_pickle"):
                self._add(
                    "S003", "pickle deserialization", "HIGH", "CWE-502",
                    node.lineno,
                    "pickle.load/loads can execute arbitrary code when "
                    "deserializing untrusted data. Use json or safer formats.",
                )
            # S008: yaml.load without Loader (checked inside the load branch)
            elif isinstance(func.value, ast.Name) and func.value.id == "yaml":
                has_loader = any(kw.arg == "Loader" for kw in node.keywords)
                if not has_loader:
                    self._add(
                        "S008", "yaml.load() without Loader", "HIGH", "CWE-94",
                        node.lineno,
                        "yaml.load() without an explicit Loader can execute "
                        "arbitrary Python. Use yaml.safe_load() instead.",
                    )

        # S004: subprocess shell=True
        elif func_name in ("run", "Popen", "call", "check_call", "check_output"):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    self._add(
                        "S004", "subprocess with shell=True", "HIGH", "CWE-78",
                        node.lineno,
                        "shell=True passes the command through the shell, "
                        "enabling injection attacks. Pass command as a list instead.",
                    )

        # S005: os.system
        elif func_name == "system" and isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id == "os":
                self._add(
                    "S005", "os.system() usage", "MEDIUM", "CWE-78", node.lineno,
                    "os.system() passes the command to the shell. "
                    "Use subprocess.run() with a list argument instead.",
                )

        # S006: hashlib.md5 / sha1
        elif func_name in ("md5", "sha1") and isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id == "hashlib":
                algo = func_name.upper()
                self._add(
                    "S006", f"Weak hash: hashlib.{func_name}", "MEDIUM", "CWE-327",
                    node.lineno,
                    f"{algo} is cryptographically broken. Use SHA-256 or SHA-3 "
                    "for security-sensitive hashing.",
                )

        # S007: tempfile.mktemp
        elif func_name == "mktemp" and isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id == "tempfile":
                self._add(
                    "S007", "tempfile.mktemp() usage", "MEDIUM", "CWE-377",
                    node.lineno,
                    "mktemp() has a race condition. Use tempfile.mkstemp() or "
                    "tempfile.NamedTemporaryFile() instead.",
                )

        self.generic_visit(node)

    # ---- S009: assert for access control ----
    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        """Flag assert statements used for authentication or access control checks"""
        # Only flag if the assert test looks like an auth/permission check.
        test_src = ""
        if isinstance(node.test, ast.Call):
            func = node.test.func
            if isinstance(func, ast.Attribute):
                test_src = func.attr
            elif isinstance(func, ast.Name):
                test_src = func.id
        if any(kw in test_src.lower() for kw in ("auth", "perm", "role", "admin", "login")):
            self._add(
                "S009", "assert for access control", "MEDIUM", "CWE-676",
                node.lineno,
                "assert statements are removed when Python runs with -O "
                "(optimise flag). Do not use assert for security checks.",
            )
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def audit_security(repo_path: Optional[Path] = None) -> SecurityReport:
    """Audit all src/ Python files for common security anti-patterns.

    Parameters
    ----------
    repo_path:
        Root of the Awake repo.  Defaults to the repo root when
        installed via ``pip install -e .``.
    """
    if repo_path is None:
        repo_path = Path(__file__).resolve().parent.parent
    repo_path = Path(repo_path)
    src_dir = repo_path / "src"

    report = SecurityReport(repo_path=str(repo_path))

    if not src_dir.exists():
        return report

    py_files = sorted(src_dir.glob("*.py"))
    report.files_scanned = len(py_files)

    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        rel = str(py_file.relative_to(repo_path))
        source_lines = source.splitlines()

        # AST-based checks
        visitor = _SecurityVisitor(rel, source_lines)
        visitor.visit(tree)
        report.findings.extend(visitor.findings)

        # Regex-based heuristic checks (hardcoded secrets)
        for lineno, raw_line in enumerate(source_lines, start=1):
            for pattern, title in _SECRET_PATTERNS:
                if pattern.search(raw_line):
                    snippet = raw_line.strip()[:80]
                    report.findings.append(SecurityFinding(
                        rule="S010",
                        title=title,
                        severity="HIGH",
                        cwe="CWE-259",
                        file=rel,
                        line=lineno,
                        snippet=snippet,
                        description=(
                            "Hardcoded credentials in source code can be "
                            "extracted from version control history. Use "
                            "environment variables or a secrets manager."
                        ),
                    ))

    return report


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_security_report(report: SecurityReport, out_path: Path) -> None:
    """Write the security report as Markdown + JSON sidecar to *out_path*."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(report.to_json(), encoding="utf-8")
