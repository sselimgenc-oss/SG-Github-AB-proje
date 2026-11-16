"""Thread ortam degiskenleri -- numpy/pandas/lightgbm ICE AKTARILMADAN once ayarlanabilsin diye bu modul
HICBIR agir paket ice aktarmaz (yalniz os)."""
import os

THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def preset_threads(argv, threads: int = 1) -> bool:
    """--research yoksa (varsayilan = sunucu limitleri) thread env'lerini sabitler. Doner: ayarlandi mi."""
    if "--research" in argv:
        return False
    for k in THREAD_ENV:
        os.environ[k] = str(threads)
    return True
