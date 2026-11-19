"""ML filtresi (kagit, AKTIF; 19.11 kullanici karari): `ortak_ogrenme.filtre` paketini kagit giris kapisina baglar.

Sinir (kod duzeyinde): filtre yalniz bir YENI girisi atlatabilir (`ml_filter`). Boyut, kaldirac, risk, limit, stop/hedef ve
kapi zincirine dokunamaz; yeni islem actiramaz (kapi: gates.EntryGate.decide, risk kontrolunden ONCE yalniz "hayir" der).
Hata/eksik/bozuk/suresi gecmis paket ya da kurulumun kapanmis islemi < MIN_ISLEM => o kurulum icin filtre YOK, giris serbest
(fail-open; `ml_no_model` YAZILMAZ). `TRADER_OGRENME_FILTRE_KAPALI=1` filtreyi tamamen kapatir. Yalniz kagit; testnet/canli yolu
degismez (orada ML kapisi/gecis kapisi eskisi gibi).

Egitim (gece birimi `scripts/ml_retrain_run.py`, 03:10 UTC): kagit defterinden kurulum (arm_id) basina, >= MIN_ISLEM kapanmis
islemle; her YENIDEN_ISLEM yeni kapanan islemde ya da paket YENIDEN_GUN gunu astiginda yeniden. Kilitli donem (HOLDOUT) satirlari
egitimden dusurulur. Paketler `<defter dizini>/models/ortak_filtre/<arm>.json`.
"""
from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from trader_core.ml_live_v2 import setup_feature_dict

from .holdout import HOLDOUT

log = logging.getLogger("engine.ogrenme_filtre")

MIN_ISLEM = 10             # kurulum basina asgari kapanmis islem (1L3A ile ayni, 2026-11-19)
YENIDEN_ISLEM = 10         # her 10 yeni kapanan islemde yeniden egit
YENIDEN_GUN = 20           # paket omru 21 gun: bir gun erken yenile (bosluk kalmasin)
ENV_KAPALI = "TRADER_OGRENME_FILTRE_KAPALI"
MODEL_ALT = ("models", "ortak_filtre")
DURUM_DOSYASI = "ogrenme_filtre_durum.json"


def paket_modulleri():
    """(filtre, kayit) ya da None (paket/numpy yok => filtre YOK)."""
    try:
        from ortak_ogrenme import filtre, kayit
        return filtre, kayit
    except ImportError:
        return None


def model_dizini(ledger_path: str | os.PathLike) -> Path:
    return Path(ledger_path).parent.joinpath(*MODEL_ALT)


def kapali(env: Mapping[str, str] | None = None) -> bool:
    return (os.environ if env is None else env).get(ENV_KAPALI) == "1"


def ozellikler(*, side, regime, atr_ratio, session_tag, pair, planned_entry, planned_stop, planned_target=None,
               rh_touches=0, rl_touches=0, features: Mapping | None = None) -> dict[str, float]:
    """Karar anindaki sayisal ozellikler (egitim ve giris AYNI islevi kullanir). Sonlu olmayanlar atilir (filtre `fill` kullanir)."""
    d = setup_feature_dict(side=side, regime=regime, atr_ratio=atr_ratio, session_tag=session_tag, asset_class=None, pair=pair,
                           planned_entry=planned_entry, planned_stop=planned_stop, planned_target=planned_target,
                           rh_touches=rh_touches, rl_touches=rl_touches, features=features)
    return {k: float(v) for k, v in d.items() if isinstance(v, (int, float)) and math.isfinite(v)}


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class Karar:
    izin: bool
    puan: float | None
    neden: str          # ok | esik_alti | filtre_yok | hata


class FiltreDeposu:
    """Kurulum (arm_id) basina paket onbellegi + puanlama. Her yol hata -> izin True (fail-open)."""

    def __init__(self, klasor: str | os.PathLike, *, kapali_: bool | None = None) -> None:
        self.klasor = Path(klasor)
        self.kapali = kapali() if kapali_ is None else kapali_
        self._mod = None if self.kapali else paket_modulleri()
        self._onbellek: dict[str, tuple[tuple, dict | None]] = {}
        self._uyarilan: set[str] = set()

    @property
    def calisiyor(self) -> bool:
        return self._mod is not None

    def _yol(self, arm: str) -> Path:
        return self.klasor / f"{self._mod[0]._guvenli_ad(arm)}.json"

    def paket(self, arm: str, simdi: datetime) -> dict | None:
        """Gecerli (hash + sure + n_egitim >= MIN_ISLEM) paket ya da None."""
        if self._mod is None:
            return None
        filtre = self._mod[0]
        try:
            yol = self._yol(arm)
            st = yol.stat()
        except (OSError, ValueError):
            self._onbellek.pop(arm, None)
            return None
        sig = (st.st_mtime_ns, st.st_size)
        ent = self._onbellek.get(arm)
        if ent is None or ent[0] != sig:
            try:
                p = filtre.yukle(yol, sure_kontrol=False)
                if int(p["meta"].get("n_egitim", 0)) < MIN_ISLEM:
                    p = None
            except Exception as e:  # noqa: BLE001 - bozuk paket: filtre YOK
                if arm not in self._uyarilan:
                    self._uyarilan.add(arm)
                    log.warning("ML filtre paketi gecersiz (%s), filtre YOK: %s", arm, e)
                p = None
            ent = (sig, p)
            self._onbellek[arm] = ent
        p = ent[1]
        if p is None:
            return None
        try:
            if _utc(simdi) >= _utc(datetime.fromisoformat(p["meta"]["son_kullanma"])):
                return None                                          # suresi gecmis: filtre YOK
        except Exception:  # noqa: BLE001
            return None
        return p

    def karar(self, arm: str, oz: Mapping[str, float], simdi: datetime) -> Karar:
        """Yalniz bir girisi atlatabilir. Esik alti puan => izin False; baska her durum => izin True."""
        if self._mod is None:
            return Karar(True, None, "filtre_yok")
        try:
            p = self.paket(arm, simdi)
            if p is None:
                return Karar(True, None, "filtre_yok")
            puan = float(self._mod[0].puan(p, oz))
            if not math.isfinite(puan) or not 0.0 <= puan <= 1.0:
                return Karar(True, None, "hata")
            return Karar(puan >= float(p["esik"]), puan, "ok" if puan >= float(p["esik"]) else "esik_alti")
        except Exception as e:  # noqa: BLE001 - filtre hatasi asla motoru durdurmaz, girisi engellemez
            log.warning("ML filtre hatasi (%s), giris serbest: %s: %s", arm, type(e).__name__, e)
            return Karar(True, None, "hata")

    def aktif_kurulumlar(self, simdi: datetime) -> list[str]:
        if self._mod is None or not self.klasor.is_dir():
            return []
        out = []
        for p in sorted(self.klasor.glob("*.json")):
            if p.name.endswith(".prev.json") or p.name.startswith("."):
                continue
            try:
                arm = json.loads(p.read_text(encoding="utf-8"))["meta"]["kurulum"]
            except Exception:  # noqa: BLE001
                continue
            if self.paket(str(arm), simdi) is not None:
                out.append(str(arm))
        return out


# ---------------------------------------------------------------------------------------------- egitim (gece birimi)
def _kilit_kesisir(ts: datetime, bitis: datetime | None) -> bool:
    b, e = HOLDOUT
    son = ts if bitis is None or bitis < ts else bitis
    return ts < e and son >= b


def adaylar_defterden(led) -> list:
    """Kapanmis kagit islemleri -> ortak_ogrenme Aday listesi (alindi=True, r = net R). Kilitle kesisen islem dusurulur.
    ts = karar mumunun kapanisi; ozellikler = karar anindaki ozellikler (girisle AYNI islev)."""
    mod = paket_modulleri()
    if mod is None:
        return []
    Aday = mod[1].Aday
    dec = {d.id: d for d in led.list_decisions()}
    out = []
    for t in led.list_closed_trades(limit=led.LIST_CLOSED_MAX):
        d = dec.get(t.decision_id)
        if d is None or t.r_multiple is None or not d.arm_id or not math.isfinite(float(t.r_multiple)):
            continue
        ts = _utc(d.bar_close_ts)
        if _kilit_kesisir(ts, None if t.exit_ts is None else _utc(t.exit_ts)):
            continue
        oz = ozellikler(side=d.side, regime=d.regime, atr_ratio=d.atr_ratio, session_tag=d.session_tag, pair=d.pair,
                        planned_entry=d.planned_entry, planned_stop=d.planned_stop, planned_target=d.planned_target,
                        rh_touches=d.rh_touches, rl_touches=d.rl_touches, features=d.features)
        out.append(Aday(id=str(t.trade_id), proje="ML", kurulum=d.arm_id, enstruman=d.pair, varlik_sinifi="kripto",
                        yon=d.side, ts=ts, alindi=True, r=float(t.r_multiple), rejim=d.regime, ozellikler=oz))
    return out


def egit_hepsi(adaylar, klasor: str | os.PathLike, simdi: datetime, *, durum_yolu: str | os.PathLike | None = None) -> dict:
    """Kurulum basina (>= MIN_ISLEM kapanmis islem) yeniden egitim kurali: son egitimden bu yana >= YENIDEN_ISLEM yeni islem ya da
    >= YENIDEN_GUN gun. Holdout satirlari `adaylar_defterden`de dusuruldu; `egit` kilit aralikla ayrica dusurur. Donus: rapor."""
    mod = paket_modulleri()
    if mod is None:
        return {"durum": "paket_yok"}
    filtre = mod[0]
    simdi = _utc(simdi)
    dy = Path(durum_yolu) if durum_yolu else Path(klasor) / DURUM_DOSYASI
    try:
        durum = json.loads(dy.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        durum = {}
    if not isinstance(durum, dict):
        durum = {}
    kilit = [HOLDOUT]
    by: dict[str, list] = {}
    for a in adaylar:
        by.setdefault(a.kurulum, []).append(a)
    rapor: dict[str, dict] = {}
    for arm in sorted(by):
        n = sum(1 for a in by[arm] if a.r is not None)
        son = durum.get(arm) if isinstance(durum.get(arm), dict) else None
        if n < MIN_ISLEM:
            rapor[arm] = {"n": n, "durum": "az_islem"}
            continue
        if son is not None:
            try:
                gun = (simdi - _utc(datetime.fromisoformat(son["zaman"]))).days
            except Exception:  # noqa: BLE001
                gun = YENIDEN_GUN
            if n - int(son.get("n", 0)) < YENIDEN_ISLEM and gun < YENIDEN_GUN:
                rapor[arm] = {"n": n, "durum": "guncel"}
                continue
        try:
            paket = filtre.egit(arm, by[arm], olusturma=simdi, kilit=kilit)
            yol = Path(klasor) / f"{filtre._guvenli_ad(arm)}.json"
            if paket is not None:
                filtre.kaydet(paket, klasor)
            elif yol.exists():
                yol.unlink()                                  # tek sinif: eski model de gecersiz => filtre YOK
            durum[arm] = {"zaman": simdi.isoformat(), "n": n, "model": paket is not None}
            rapor[arm] = {"n": n, "durum": "ok" if paket is not None else "tek_sinif"}
        except Exception as e:  # noqa: BLE001 - bir kurulumun hatasi digerini ve gece birimini durdurmaz
            log.warning("ML filtre egitimi basarisiz (%s): %s: %s", arm, type(e).__name__, e)
            rapor[arm] = {"n": n, "durum": "hata"}
    try:
        Path(klasor).mkdir(parents=True, exist_ok=True)
        tmp = dy.with_name(f".{dy.name}.tmp")
        tmp.write_text(json.dumps(durum, sort_keys=True), encoding="utf-8")
        os.replace(tmp, dy)
    except OSError as e:
        log.warning("ML filtre durumu yazilamadi: %s", e)
    return {"durum": "ok", "kurulumlar": rapor}
