from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TARGET = ROOT / "rebuild_dashboard_history.py"
if not TARGET.exists():
    raise FileNotFoundError(f"rebuild_dashboard_history.py not found: {TARGET}")

runpy.run_path(str(TARGET), run_name="__main__")
