"""스캐너 실행기. 각 모듈은 run(target, opts) -> ToolRun 하나만 밖으로 내놓는다."""
from . import config, gitleaks, osv, semgrep

RUNNERS = {
    "osv": osv.run,
    "semgrep": semgrep.run,
    "gitleaks": gitleaks.run,
    "config": config.run,
}

__all__ = ["RUNNERS", "osv", "semgrep", "gitleaks", "config"]
