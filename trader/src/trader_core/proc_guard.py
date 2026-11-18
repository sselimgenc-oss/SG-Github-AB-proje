"""Surec ortam korumasi (DD-9 §4.3): ayni kimlikli baska surecler /proc/<pid>/environ okuyamasin.

Yalniz stdlib/ctypes. prctl(PR_SET_DUMPABLE, 0) sureci 'dokulemez' yapar; boylece /proc/<pid>/* dosyalari root'a ait olur.
Linux degilse ya da cagri basarisizsa False doner; istisna sizmaz."""
from __future__ import annotations

import ctypes
import sys

PR_SET_DUMPABLE = 4
PR_GET_DUMPABLE = 3


def _libc():
    return ctypes.CDLL(None, use_errno=True)


def set_nondumpable() -> bool:
    """prctl(PR_SET_DUMPABLE, 0); basari True; Linux degil/hata -> False."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        rc = _libc().prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
        return int(rc) == 0
    except Exception:  # noqa: BLE001 - istisna sizmaz
        return False


def is_dumpable() -> bool | None:
    """prctl(PR_GET_DUMPABLE); okunamazsa None."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        rc = int(_libc().prctl(PR_GET_DUMPABLE, 0, 0, 0, 0))
    except Exception:  # noqa: BLE001
        return None
    if rc < 0:
        return None
    return rc == 1
