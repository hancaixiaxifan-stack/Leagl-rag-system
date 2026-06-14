from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def project_python() -> str:
    if os.name == "nt":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate if candidate.exists() else Path(sys.executable))


def npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def run(label: str, command: list[str], cwd: Path = ROOT) -> None:
    print(f"\n==> {label}", flush=True)
    print(" ".join(command), flush=True)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    subprocess.run(command, cwd=cwd, check=True, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run core backend and frontend checks.")
    parser.add_argument(
        "--smoke-api",
        action="store_true",
        help="Also run scripts/smoke_api.py, which may be slower because it loads indexes/models.",
    )
    args = parser.parse_args()

    py = project_python()

    checks: list[tuple[str, list[str], Path]] = [
        ("Backend environment", [py, "scripts/inspect_env.py"], ROOT),
        ("Counterfactual unit script", [py, "scripts/test_counterfactual.py"], ROOT),
        ("Keyword coverage script", [py, "scripts/test_keyword_coverage.py"], ROOT),
        ("Python compile check", [py, "-m", "compileall", "app", "rag_contract", "scripts"], ROOT),
        ("Frontend lint", [npm_cmd(), "run", "lint"], FRONTEND),
        ("Frontend build", [npm_cmd(), "run", "build"], FRONTEND),
    ]

    if args.smoke_api:
        checks.insert(3, ("FastAPI smoke test", [py, "scripts/smoke_api.py"], ROOT))

    try:
        for label, command, cwd in checks:
            run(label, command, cwd)
    except subprocess.CalledProcessError as exc:
        print(f"\nFAILED: {exc.cmd} exited with {exc.returncode}", file=sys.stderr, flush=True)
        return exc.returncode

    print("\nAll checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
