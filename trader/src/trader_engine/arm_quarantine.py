"""Kurulum (arm) kod hatasi karantinasi (1L3A motor/canli/karantina.py + paper.py `_karantinaya_al*`'dan uyarlandi).

AMAC: bir kurulumun karar KODU art arda programlama hatasi verirse (errors.is_strategy_error: TypeError, KeyError,
ZeroDivisionError, ValueError...) yalniz o kurulum YENI giris uretmeyi birakir; tur dusmez, digerleri normal calisir. Bu bir
KOD-ARIZASI guvenlik durdurmasidir, performans kapatmasi DEGILDIR (kurulumu basarisizliga gore kapatma kullanici karariyla
yasaktir; yalniz kademeli boyut kucultme vardir). Ag/veri/borsa gibi GECICI hatalar asla karantinaya sokmaz.

Karantinada: kurulum kodu CAGRILMAZ (yeni aday yok); acik pozisyonlar motorun stop/hedef/zaman/KILL yonetimiyle surer (cikis
baglami cekirdek tablodan gelir; stop ve KILL her turda calisir).

Sayim: ayni kurulumda ARDISIK `KOD_HATASI_SINIRI` (5) kod hatasi -> karantina; arada basarili hesap sayaci sifirlar.
Kayit motor durumunda (kv `arm_quarantine`) kalicidir; status.json `dayaniklilik.karantina` ile panel/Telegram'a gorunur.
Kaldirma: Telegram `/karantina_kaldir <kurulum|hepsi>` (iki adimli) ya da CLI `arm-quarantine release`; ikisi de istek dosyasi
yazar (`arm_quarantine_release.json`), motor bir sonraki dakika kontrolunde isler: kurulum 'deneme'ye gecer (yeniden calisir);
ilk basarili hesapta kayit silinir (duzeldi), YENIDEN hata verirse hemen tekrar karantina.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from .fileio import atomic_write_json, fmt_ts

log = logging.getLogger("engine.arm_quarantine")

KOD_HATASI_SINIRI = 5            # ayni kurulumda ardisik kod hatasi sayisi (1L3A KOD_HATASI_SINIRI)
KV_KEY = "arm_quarantine"
RELEASE_FILE = "arm_quarantine_release.json"
ACTIVE, TRIAL = "aktif", "deneme"


def unit_for(lab, tf: str, key: str) -> tuple[str, list[str]]:
    """Karantina birimi: ('<anahtar>@<tf>', [arm_id...]). `core` anahtari birden fazla CORE kurulumun ortak tablosudur
    (T1, R1...): birimdeki tum kurulumlar birlikte karantinaya girer; digerleri kurulum koduyla tek basina."""
    from .strategies.arms import make_arm_id
    mods = lab.arms_at(tf)
    if key == "core":
        arms = [make_arm_id(m.SETUP, tf) for m in mods if getattr(m, "CORE", False)]
    else:
        arms = [make_arm_id(key, tf)]
    return f"{key}@{tf}", arms


class ArmQuarantine:
    def __init__(self, *, now_fn: Callable[[], datetime], limit: int = KOD_HATASI_SINIRI) -> None:
        self.limit = int(limit)
        self.now = now_fn                        # saat enjekte (motor saati)
        self._rec: dict[str, dict] = {}          # birim -> {"arms", "state", "since", "error", "count"}
        self._counts: dict[str, int] = {}        # birim -> ardisik hata (bellek; karantinadaki kayit kalicidir)
        self.dirty = False
        self.events: list[tuple[str, str, str]] = []   # (tur, birim, ayrinti): motor loglar; Telegram status'tan okur

    # ------------------------------------------------------------------ kalicilik
    def load(self, doc) -> None:
        self._rec = {}
        if isinstance(doc, dict):
            for k, v in doc.items():
                if isinstance(v, dict) and v.get("state") in (ACTIVE, TRIAL):
                    self._rec[str(k)] = {"arms": [str(a) for a in v.get("arms") or []], "state": v["state"],
                                         "since": str(v.get("since") or ""), "error": str(v.get("error") or ""),
                                         "count": int(v.get("count") or 0)}
        self.dirty = False

    def dump(self) -> dict:
        return {k: dict(v) for k, v in sorted(self._rec.items())}

    # ------------------------------------------------------------------ sorgu
    def blocked(self, unit: str) -> bool:
        r = self._rec.get(unit)
        return r is not None and r["state"] == ACTIVE

    def blocked_units(self) -> list[str]:
        return [k for k, v in sorted(self._rec.items()) if v["state"] == ACTIVE]

    def blocked_arms(self) -> list[str]:
        out: list[str] = []
        for k in self.blocked_units():
            out += self._rec[k]["arms"]
        return sorted(set(out))

    def status(self) -> list[dict]:
        return [{"birim": k, "kollar": list(v["arms"]), "durum": v["state"], "since": v["since"], "hata": v["error"]}
                for k, v in sorted(self._rec.items())]

    # ------------------------------------------------------------------ olaylar
    def ok(self, unit: str) -> None:
        """Birim basarili hesapladi: ardisik sayac sifirlanir; 'deneme' ise duzeldi (kayit silinir)."""
        self._counts.pop(unit, None)
        r = self._rec.get(unit)
        if r is not None and r["state"] == TRIAL:
            del self._rec[unit]
            self.dirty = True
            self.events.append(("duzeldi", unit, ""))
            log.warning("kurulum karantinadan cikti (duzeldi): %s", unit)

    def error(self, unit: str, arms: Iterable[str], exc: BaseException) -> bool:
        """Kod hatasi kaydi. -> bu cagriyla karantinaya girildi mi. Esik: ardisik `limit`; 'deneme'de ilk hata."""
        hata = f"{type(exc).__name__}: {str(exc)[:200]}"
        r = self._rec.get(unit)
        if r is not None and r["state"] == ACTIVE:
            return False
        n = self._counts.get(unit, 0) + 1
        if r is not None and r["state"] == TRIAL:
            n = self.limit
        self._counts[unit] = n
        log.error("kurulum kod hatasi (%s, ardisik %d/%d): %s", unit, n, self.limit, hata, exc_info=exc)
        if n < self.limit:
            return False
        self._rec[unit] = {"arms": list(arms), "state": ACTIVE, "since": fmt_ts(self.now()), "error": hata, "count": n}
        self._counts.pop(unit, None)
        self.dirty = True
        self.events.append(("karantina", unit, hata))
        log.critical("kurulum KARANTINAYA alindi (yeni giris yok, acik pozisyonlar yonetilir): %s: %s", unit, hata)
        return True

    # ------------------------------------------------------------------ kaldirma
    def release(self, target: str) -> list[str]:
        """`target`: birim anahtari, kurulum kimligi ya da 'hepsi'. Eslesen aktif birimler 'deneme'ye gecer. -> birimler."""
        t = (target or "").strip().lower()
        out: list[str] = []
        for k, v in self._rec.items():
            if v["state"] != ACTIVE:
                continue
            if t == "hepsi" or t == k.lower() or t in (a.lower() for a in v["arms"]):
                v["state"] = TRIAL
                out.append(k)
        if out:
            self._counts = {k: c for k, c in self._counts.items() if k not in out}
            self.dirty = True
            for k in out:
                self.events.append(("kaldirildi", k, ""))
                log.warning("kurulum karantinasi kaldirildi (yeniden denenecek): %s", k)
        return out


# ---------------------------------------------------------------------------------------------------------------------
# Kaldirma istek dosyasi (Telegram / CLI yazar, motor isler): {"hedef": "<kurulum|hepsi>", "zaman": ..., "kaynak": ...}
def request_release(directory, target: str, source: str, now: datetime) -> Path:
    return atomic_write_json(Path(directory) / RELEASE_FILE, {"hedef": str(target).strip(), "zaman": fmt_ts(now), "kaynak": source})


def take_release_request(directory) -> str | None:
    """Istek dosyasini okuyup siler. Dosya yok -> None; bozuk -> silinir, None (sessiz yutma yok: log)."""
    p = Path(directory) / RELEASE_FILE
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        target = str(doc.get("hedef") or "").strip() if isinstance(doc, dict) else ""
    except (OSError, ValueError):
        target = ""
        log.error("karantina kaldirma istegi okunamadi; silindi")
    try:
        os.unlink(p)
    except OSError:
        pass
    return target or None
