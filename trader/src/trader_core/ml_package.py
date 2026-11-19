"""Model paketi okuyucu (ML-0a, 19a): motor tarafi. Yalniz stdlib + numpy; trader_ml/lightgbm/sklearn/scipy yok.

`load_package` kurali trader_ml.package ile AYNIDIR (oradan buraya tasindi, geri-export edilir): kapidan gecmemis
(`meta.gate_passed` True degil) ya da esiksiz paket REDDEDILIR; hash'ler tutmali; 21 gunu asan paket REDDEDILIR.
`MlModelView` motorun stratejiye verdigi SALT OKUNUR bag lam alanidir (05 §13.2 `StrategyContext.model`)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .ml_eval import TreeModel

MODEL_EXPIRY_DAYS = 21


class PackageError(ValueError):
    pass


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def feature_list_hash(names: list[str]) -> str:
    return sha256_text("\n".join(names))


def _utc(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def expires_at(pkg: dict) -> datetime:
    """Gecerlilik siniri: meta.expires_at ile created_at + 21 gunun ERKENI (uzatilmis expires_at dolanamaz)."""
    meta = pkg["meta"]
    lim = _utc(meta["expires_at"])
    try:
        lim = min(lim, _utc(meta["created_at"]) + timedelta(days=MODEL_EXPIRY_DAYS))
    except (KeyError, ValueError, TypeError):
        pass
    return lim


def is_expired(pkg: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now >= expires_at(pkg)


def load_package(path: str | Path | dict, *, now: datetime | None = None, check_expiry: bool = True,
                 require_gate: bool = True) -> dict:
    """Okur, hash'leri dogrular (tutmuyorsa PackageError), suresi dolmussa PackageError. Kapidan gecmemis
    (meta.gate_passed true degil) ya da esiksiz paket require_gate=True iken REDDEDILIR; yalniz egitim hatti
    kendi gidis-donus kontrolunde ve inceleme icin require_gate=False kullanir."""
    pkg = path if isinstance(path, dict) else json.loads(Path(path).read_text(encoding="utf-8"))
    meta = pkg["meta"]
    if require_gate:
        if meta.get("gate_passed") is not True:
            raise PackageError(f"paket kapidan gecmedi (gate_passed={meta.get('gate_passed')!r}); yuklenemez")
        if pkg.get("threshold") is None:
            raise PackageError("paketin esigi yok (threshold null); yuklenemez")
    body = {"model": pkg["model"], "calibration": pkg["calibration"], "threshold": pkg["threshold"]}
    if sha256_text(canon(body)) != meta["model_hash"]:
        raise PackageError("model hash tutmuyor")
    if feature_list_hash(meta["features"]) != meta["feature_list_hash"]:
        raise PackageError("ozellik listesi hash tutmuyor")
    if check_expiry and is_expired(pkg, now):
        raise PackageError("model suresi dolmus")
    return pkg


@dataclass(frozen=True)
class MlModelView:
    """Stratejiye salt okunur verilen yuklenmis model (05 §13.2). Dosya/ag/saat gormez; `expired(D)` karar anina gore."""
    model_id: str
    threshold: float
    features: tuple[str, ...]
    expires_at: datetime
    user_approved: bool
    _tree: TreeModel = field(repr=False, compare=False)
    experimental: bool = False                    # golge deneyi: kapidan gecmemis paket (yalniz shadow); log/gerekcede ml_exp=1

    def expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def score(self, X) -> np.ndarray:
        """X: (n, len(features)) sutun sirasi `features` ile ayni; kalibre olasilik (n,)."""
        return self._tree.predict_proba(X)


def view_from_package(pkg: dict, *, experimental: bool = False) -> MlModelView:
    meta = pkg["meta"]
    thr = pkg["threshold"]
    return MlModelView(
        model_id=f"{meta.get('version', '?')}@{meta['model_hash'][:12]}", threshold=0.5 if thr is None else float(thr),
        features=tuple(meta["features"]), expires_at=expires_at(pkg), user_approved=meta.get("user_approved") is True,
        _tree=TreeModel(pkg["model"], pkg["calibration"]),
        experimental=experimental)


def load_model_view(path: str | Path | dict, *, expected_features, ml_mode: str,
                    now: datetime | None = None, experimental: bool = False) -> MlModelView:
    """Motor yukleyicisi: `load_package` (kapi + hash + 21 gun) + ozellik listesi canli ozellik ureticisiyle ayni olmali.
    `active` modu ayrica kullanici onayi ister (`meta.user_approved is True`); yoksa PackageError (19a).
    `experimental=True` yalniz `ml_mode == "shadow"` ile (aksi ValueError); kapi denetimi atlanir, hash + 21 gun kalir."""
    if experimental and ml_mode != "shadow":
        raise ValueError(f"experimental yalniz ml_mode='shadow' ile gecerli (ml_mode={ml_mode!r})")
    pkg = load_package(path, now=now, require_gate=not experimental)
    if list(pkg["meta"]["features"]) != list(expected_features):
        raise PackageError("model ozellik listesi canli ozellik ureticisiyle ayni degil")
    view = view_from_package(pkg, experimental=experimental)
    if ml_mode == "active" and not view.user_approved:
        raise PackageError("active modu icin model kullanici onayli degil (meta.user_approved)")
    return view


_ML_P = re.compile(r"(?:^|\|)ml:p=([0-9]+(?:\.[0-9]+)?)\|")


def ml_score_from_reasons(reasons: str | None) -> float | None:
    """Strateji -> motor kanali (05 §13.4a): `reasons` basindaki `ml:p=0.412300|` etiketi; yok/aralik disi -> None."""
    m = _ML_P.search(reasons or "")
    if m is None:
        return None
    v = float(m.group(1))
    return v if 0.0 <= v <= 1.0 else None


# ---------------------------------------------------------------------------------------------------------------------
# DD-12 WP-10: CELI PAKET (arm_id basina) + SICAK YUKLEME. Motor API'si:
#   ps = PackageSet(models_dir)                 # models_dir/<guvenli_arm_id>.json ; <...>.prev.json yedektir (yuklenmez)
#   ps.reload(now=...)        -> {"loaded": [...], "removed": [...], "rejected": {arm: neden}}   (bar kapanisinda cagir; dosya
#                                degismediyse (mtime_ns, size) ucuz atlanir; bozuk/suresi dolmus paket YALNIZ o kolu `ml_no_model` yapar,
#                                oncekini silmez ama suresi dolmussa kullanmaz; motor hic durmaz)
#   ps.decide(arm_id, fdict, now=...) -> SetupDecision(passed, score, code)   # code: "ok" | "ml_below_threshold" | "ml_no_model"
# `ml_no_model` => aday GECER (esiksiz kural, spec 5); puan yok. Puan > esik kosulu: score >= threshold gecer.
# `paper_only` paketler (meta.paper_only) yalniz `allow_paper_only=True` ile yuklenir (testnet/canliya kapidan gecmemis model yuklenmez).
# ---------------------------------------------------------------------------------------------------------------------
def safe_arm_name(arm_id: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._@-]", "_", str(arm_id))
    if not s or s.startswith("."):
        raise ValueError(f"gecersiz arm_id: {arm_id!r}")
    return s


@dataclass(frozen=True)
class SetupDecision:
    passed: bool
    score: float | None
    code: str


class PackageSet:
    def __init__(self, models_dir: str | Path, *, allow_paper_only: bool = True) -> None:
        self.dir = Path(models_dir)
        self.allow_paper_only = allow_paper_only
        self._views: dict[str, MlModelView] = {}
        self._sig: dict[str, tuple] = {}
        self._rejected: dict[str, str] = {}

    def arms(self) -> list[str]:
        return sorted(self._views)

    def rejected(self) -> dict[str, str]:
        return dict(self._rejected)

    def view(self, arm_id: str) -> MlModelView | None:
        return self._views.get(arm_id)

    def reload(self, *, now: datetime | None = None) -> dict:
        loaded, removed = [], []
        files = {}
        if self.dir.is_dir():
            for p in sorted(self.dir.glob("*.json")):
                if p.name.endswith(".prev.json") or p.name.startswith("."):
                    continue
                files[p.name] = p
        new_views: dict[str, MlModelView] = {}
        new_sig: dict[str, tuple] = {}
        rejected: dict[str, str] = {}
        by_file = {self._file_of(a): a for a in self._views}
        for name, p in files.items():
            try:
                st = p.stat()
                sig = (st.st_mtime_ns, st.st_size)
                prev_arm = by_file.get(name)
                if prev_arm is not None and self._sig.get(prev_arm) == sig and not is_expired(
                        {"meta": {"expires_at": self._views[prev_arm].expires_at.isoformat()}}, now):
                    new_views[prev_arm], new_sig[prev_arm] = self._views[prev_arm], sig
                    continue
                pkg = load_package(p, now=now)
                meta = pkg["meta"]
                if meta.get("paper_only") is True and not self.allow_paper_only:
                    raise PackageError("paper_only paket bu modda yuklenemez")
                arm = meta.get("arm_id")
                if not arm or safe_arm_name(arm) + ".json" != name:
                    raise PackageError("meta.arm_id dosya adiyla uyusmuyor")
                new_views[arm], new_sig[arm] = view_from_package(pkg), sig
                loaded.append(arm)
            except (PackageError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                rejected[name[:-5]] = f"{type(e).__name__}: {e}"
        removed = sorted(set(self._views) - set(new_views))
        self._views, self._sig, self._rejected = new_views, new_sig, rejected      # referans atamasi: okuyucular eski ya da yeni gorur
        return {"loaded": sorted(loaded), "removed": removed, "rejected": dict(rejected)}

    @staticmethod
    def _file_of(arm_id: str) -> str:
        return safe_arm_name(arm_id) + ".json"

    def decide(self, arm_id: str, fdict, *, now: datetime | None = None) -> SetupDecision:
        """Tek adayin kararini ver. Paket yok/suresi dolmus/ozellik hatasi -> (True, None, "ml_no_model")."""
        v = self._views.get(arm_id)
        now = now or datetime.now(timezone.utc)
        if v is None or v.expired(now):
            return SetupDecision(True, None, "ml_no_model")
        try:
            from .ml_live_v2 import setup_feature_vector
            p = float(v.score(setup_feature_vector(v.features, fdict))[0])
        except (ValueError, KeyError, TypeError):
            return SetupDecision(True, None, "ml_no_model")
        return SetupDecision(p >= v.threshold, p, "ok" if p >= v.threshold else "ml_below_threshold")
