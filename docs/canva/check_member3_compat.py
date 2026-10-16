"""Test a temporary peer-backend + current Member 4 overlay, without merging/editing peers.

Run with the backend dev environment:
uv run --project backend --frozen --extra dev python docs/canva/check_member3_compat.py
"""

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
ref = sys.argv[1] if len(sys.argv) > 1 else "origin/codex/member-2-backend-supabase"
sha = subprocess.check_output(
    ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=root, text=True
).strip()
archive = subprocess.check_output(["git", "archive", sha, "backend"], cwd=root)
with tempfile.TemporaryDirectory(prefix="member4-compat-") as directory:
    target = Path(directory)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(target, filter="data")
    for owned in ["providers/canva", "services/assets", "services/inclusion"]:
        relative = Path("backend/src/hackathon_backend") / owned
        shutil.copytree(
            root / relative,
            target / relative,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for pattern in ["test_canva_*.py", "test_assets_*.py", "test_inclusion_*.py"]:
        for test in (root / "backend/tests").glob(pattern):
            shutil.copy2(test, target / "backend/tests" / test.name)
    environment = {**os.environ, "PYTHONPATH": str(target / "backend/src")}
    print(
        f"Temporary compatibility overlay: {ref}@{sha}; current Member 4 owned files",
        flush=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests", "-q"],
        cwd=target,
        env=environment,
        check=False,
    )
    sys.exit(result.returncode)
