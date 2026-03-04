"""AST parsing utilities shared by Awake analyzers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional


def parse_file(py_file: Path) -> Optional[ast.Module]:
    """Parse a Python file and return its AST, or None on syntax error."""
    try:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        return ast.parse(source, filename=str(py_file))
    except (SyntaxError, OSError):
        return None
