"""보안엔진: Semgrep · OSV-Scanner · Gitleaks 결과를 하나의 JSON으로 묶고, 재검사 때 이전 결과와 비교한다.

    from security_engine import scan, scan_repo, ScanOptions
    result = scan("path/to/site", previous=None)

CLI:  python -m security_engine --help
"""
from .engine import compare_results, doctor, scan, scan_repo
from .git import CloneError, clone_repo
from .llm_input import build_llm_input, render_llm_text
from .models import ENGINE_VERSION, SCHEMA_VERSION, ScanOptions

__version__ = ENGINE_VERSION
__all__ = [
    "scan", "scan_repo", "compare_results", "clone_repo", "doctor",
    "build_llm_input", "render_llm_text",
    "ScanOptions", "CloneError", "SCHEMA_VERSION", "__version__",
]
