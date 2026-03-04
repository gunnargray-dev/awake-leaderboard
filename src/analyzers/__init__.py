"""Awake code analyzers -- copied from the Awake project (github.com/gunnargray-dev/Awake).

These are standalone, pure-Python static analysis tools. Each module exposes
an analysis function and a report dataclass.
"""

from src.analyzers.health import HealthReport, analyze_health
from src.analyzers.complexity import ComplexityReport, analyze_complexity
from src.analyzers.security import SecurityReport, audit_security
from src.analyzers.dead_code import DeadCodeReport, find_dead_code

__all__ = [
    "analyze_health", "HealthReport",
    "analyze_complexity", "ComplexityReport",
    "audit_security", "SecurityReport",
    "find_dead_code", "DeadCodeReport",
]
