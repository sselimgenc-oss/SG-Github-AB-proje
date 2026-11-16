"""Kaynak kurallari (§6): egitim isi botla ayni surecte degil, dusuk oncelikli, tek cekirdek, bellek
tavani 450 MB (asarsa is olur, bot etkilenmez), <= 20 dk. Arastirma (CPCV, PBO, yeni tarif) sunucu DISI
calisir: `apply_limits` yalniz sunucu modunda (--limits) cagrilir; gelistirme makinesinde cagrilmaz."""
from __future__ import annotations

import os
import resource

from .config import TRAIN_MEM_CAP_MB, TRAIN_NICE, TRAIN_THREADS, TRAIN_TIME_LIMIT_S

THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def apply_limits(mem_mb: int = TRAIN_MEM_CAP_MB, nice: int = TRAIN_NICE, cpu_seconds: int = TRAIN_TIME_LIMIT_S,
                 threads: int = TRAIN_THREADS) -> dict:
    """Bu SURECE: nice, tek cekirdek (affinity), thread env, RLIMIT_DATA (bellek tavani) ve RLIMIT_CPU.
    Tavan asilirsa MemoryError / SIGXCPU ile is olur."""
    for k in THREAD_ENV:
        os.environ[k] = str(threads)
    os.setpriority(os.PRIO_PROCESS, 0, nice)
    cpus = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, set(cpus[:threads]))
    cap = int(mem_mb) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_DATA, (cap, cap))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 30))
    return {"mem_mb": mem_mb, "nice": nice, "cpu_seconds": cpu_seconds, "cpus": cpus[:threads]}


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0   # Linux: KB
