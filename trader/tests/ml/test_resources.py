"""§6: dusuk oncelik, tek cekirdek, bellek tavani (alt surecte; pytest sureci etkilenmez)."""
import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[2] / "src")


def _run(code: str):
    return subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {SRC!r})\n" + code],
                          capture_output=True, text=True, timeout=120)


def test_apply_limits_sets_nice_affinity_and_rlimits():
    r = _run("import os, resource\nfrom trader_ml.resources import apply_limits\ninfo = apply_limits()\n"
             "print(os.getpriority(os.PRIO_PROCESS, 0), len(os.sched_getaffinity(0)), "
             "resource.getrlimit(resource.RLIMIT_DATA)[0], resource.getrlimit(resource.RLIMIT_CPU)[0], "
             "os.environ['OMP_NUM_THREADS'])")
    assert r.returncode == 0, r.stderr
    nice, ncpu, data, cpu, omp = r.stdout.split()
    assert int(nice) == 19 and int(ncpu) == 1 and int(data) == 450 * 1024 * 1024 and int(cpu) == 1200 and omp == "1"


def test_memory_cap_kills_the_job_not_the_bot():
    r = _run("import numpy as np\nfrom trader_ml.resources import apply_limits\napply_limits()\n"
             "try:\n    a = np.ones(120_000_000)   # ~960 MB > 450 MB tavan\n    a[::4096] = 1; print('ALLOCATED')\n"
             "except MemoryError:\n    print('MEMORYERROR')")
    assert "MEMORYERROR" in r.stdout, (r.stdout, r.stderr)


def test_training_recipe_is_single_threaded():
    from trader_ml.config import LGBM_PARAMS, TRAIN_MEM_CAP_MB
    assert LGBM_PARAMS["num_threads"] == 1 and LGBM_PARAMS["max_depth"] <= 4 and LGBM_PARAMS["min_data_in_leaf"] >= 50
    assert TRAIN_MEM_CAP_MB == 450
