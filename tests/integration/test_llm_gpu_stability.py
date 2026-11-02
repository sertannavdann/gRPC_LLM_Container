"""
Stability of the host-native GPU LLM tiers.

Runs scripts/llm_stability.py against every tier the supervisor has a live
pid file for (logs/llm/<tier>.pid). Skips when no host tier is running, so
the Docker CPU fallback and CI are unaffected. See docs/BENCHMARKS.md.

    make llm-up
    pytest tests/integration/test_llm_gpu_stability.py -v
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent.parent
SCRIPT = project_root / "scripts" / "llm_stability.py"
VENV_PY = project_root / "llm_service" / ".venv" / "bin" / "python"
TIER_DIR = project_root / "config" / "llm"
PID_DIR = project_root / "logs" / "llm"

SOAK_SECONDS = float(os.environ.get("LLM_STABILITY_SOAK", "20"))


def _pid_alive(pidfile: Path) -> bool:
    try:
        os.kill(int(pidfile.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def _tier_port(tier: str) -> str:
    for line in (TIER_DIR / f"{tier}.env").read_text().splitlines():
        if line.startswith("LLM_PORT="):
            return line.split("=", 1)[1].strip()
    raise ValueError(f"no LLM_PORT in {tier}.env")


def _running_tiers():
    return sorted(p.stem for p in PID_DIR.glob("*.pid") if _pid_alive(p) and (TIER_DIR / f"{p.stem}.env").exists())


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("tier", _running_tiers() or [pytest.param(None, marks=pytest.mark.skip("no host LLM tier running"))])
def test_gpu_tier_is_stable(tier):
    python = VENV_PY if VENV_PY.exists() else Path(sys.executable)
    cmd = [
        str(python), str(SCRIPT),
        "--addr", f"localhost:{_tier_port(tier)}",
        "--pidfile", str(PID_DIR / f"{tier}.pid"),
        "--soak", str(SOAK_SECONDS),
        "--expect-device", "metal",
    ]
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=900)
    print(result.stdout)
    assert result.returncode == 0, f"{tier} failed stability checks:\n{result.stdout}\n{result.stderr}"
    assert "RESULT PASS" in result.stdout
