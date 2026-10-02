"""Run the whole pipeline end to end: python src/run_all.py  (about 3 minutes)."""
import runpy
import time
from pathlib import Path

STEPS = [
    "01_simulate_data.py",
    "02_build_warehouse.py",
    "03_power_analysis.py",
    "04_experiment_analysis.py",
    "05_ltv_model.py",
    "06_validate_against_truth.py",
    "07_build_reports.py",
]

if __name__ == "__main__":
    here = Path(__file__).parent
    t0 = time.time()
    for step in STEPS:
        print(f"\n{'=' * 70}\n{step}\n{'=' * 70}")
        runpy.run_path(str(here / step), run_name="__main__")
    print(f"\nPipeline finished in {time.time() - t0:.0f}s")
