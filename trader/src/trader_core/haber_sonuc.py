"""Haber/duygu x islem sonucu raporu (`ml.haber_sonuc.v1`): `var/durum/haber_sonuc_v1.json`. YALNIZ BILGI: karar/emir yoluna girmez.

Bicim CT `copytrade/canli/rejim_sonuc.py` (`ct.rejim_sonuc.v1`) ile AYNI: satir = {etiket, n, kazanan, isabet_yuzde, toplam_pnl, ortalama_pnl};
PnL = gerceklesen K/Z (USD; defterde `realized_pnl`). Belirtim: docs/haber-sonuc-spec.md.
Baglama: kapanan islem (v_closed_trades) -> `decision_id` -> `decision_events.features` JSON'undaki `duygu` / `haber` etiketi.
Etiketsiz (eski) islemler "etiket yok" / "haber yok" kovasina duser. Donemler: son 7 gun (`tablolar`) ve tum zamanlar (`tum_zamanlar`).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SEMA = "ml.haber_sonuc.v1"
DOSYA = "haber_sonuc_v1.json"
PENCERE_GUN = 7
ETIKET_YOK = "etiket yok"
HABER_YOK = "haber yok"
DUYGU_SIRA = ("Aşırı Korku", "Korku", "Nötr", "Açgözlülük", "Aşırı Açgözlülük", ETIKET_YOK)
TON_SIRA = ("pozitif", "negatif", "notr", HABER_YOK)
_SINIF = {"extreme fear": "Aşırı Korku", "fear": "Korku", "neutral": "Nötr", "greed": "Açgözlülük", "extreme greed": "Aşırı Açgözlülük"}
SUTUNLAR = ("etiket", "n", "kazanan", "isabet_yuzde", "toplam_pnl", "ortalama_pnl")


def _say(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def duygu_kovasi(features: Any) -> str:
    d = features.get("duygu") if isinstance(features, Mapping) else None
    s = d.get("sinif") if isinstance(d, Mapping) else None
    if not isinstance(s, str) or not s.strip():
        return ETIKET_YOK
    return _SINIF.get(s.strip().lower(), ETIKET_YOK)


def ton_kovasi(features: Any, pair: str) -> str:
    h = features.get("haber") if isinstance(features, Mapping) else None
    e = h.get(str(pair).split("/", 1)[0].strip()) if isinstance(h, Mapping) else None
    t = e.get("ton") if isinstance(e, Mapping) else None
    return t if t in ("pozitif", "negatif", "notr") else HABER_YOK


def _satirlar(kv: dict[str, list[float]], sira: tuple[str, ...]) -> list[dict]:
    out = []
    for etiket in sira:
        p = kv.get(etiket)
        if not p:
            continue
        toplam, kaz = sum(p), sum(1 for x in p if x > 0)
        out.append({"etiket": etiket, "n": len(p), "kazanan": kaz, "isabet_yuzde": round(100.0 * kaz / len(p), 1),
                    "toplam_pnl": round(toplam, 2), "ortalama_pnl": round(toplam / len(p), 2)})
    return out


def _tablo(rows: Iterable[Mapping]) -> dict[str, list[dict]]:
    d: dict[str, list[float]] = {}
    t: dict[str, list[float]] = {}
    for r in rows:
        pnl = _say(r.get("pnl"))
        if pnl is None:
            continue
        d.setdefault(duygu_kovasi(r.get("features")), []).append(pnl)
        t.setdefault(ton_kovasi(r.get("features"), r.get("pair") or ""), []).append(pnl)
    return {"duygu": _satirlar(d, DUYGU_SIRA), "haber_ton": _satirlar(t, TON_SIRA)}


def topla(rows: list[Mapping], simdi: datetime, gun: int = PENCERE_GUN) -> dict:
    """Saf: rows = [{exit_ts: datetime, pnl, pair, features}]; son `gun` gun (`tablolar`) ve tum zamanlar (`tum_zamanlar`)."""
    alt = simdi - timedelta(days=gun)
    son = [r for r in rows if isinstance(r.get("exit_ts"), datetime) and alt <= r["exit_ts"] <= simdi]
    return {"tablolar": _tablo(son), "tum_zamanlar": _tablo(rows)}


def olustur(rows: list[Mapping], simdi: datetime) -> dict:
    t = topla(rows, simdi)
    n7 = sum(r["n"] for r in t["tablolar"]["duygu"])
    nt = sum(r["n"] for r in t["tum_zamanlar"]["duygu"])
    yok = sum(r["n"] for r in t["tum_zamanlar"]["duygu"] if r["etiket"] == ETIKET_YOK)
    notlar = ["Yalnız bilgi: karar/limit/eşik değiştirmez.",
              "Etiket bu sürümden sonraki kâğıt kararlarında var; eski işlemler 'etiket yok' / 'haber yok' (beklenen).",
              f"Pencere son {PENCERE_GUN} gün kapanan işlemler: {n7}; tüm zamanlar: {nt}; etiketsiz (tüm zamanlar): {yok}.",
              "PnL gerçekleşen K/Z (USD); duygu = Fear&Greed sınıfı, haber tonu = coinin 24 saatlik başlık tonu (giriş kararı anı)."]
    return {"sema": SEMA, "proje": "ML", "uretim": simdi.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pencere_gun": PENCERE_GUN, "tablolar": t["tablolar"], "tum_zamanlar": t["tum_zamanlar"], "notlar": notlar}


def defterden_satirlar(ledger: Any) -> list[dict]:
    """Kapanan islemler -> giris karari (decision_id) -> features. Karar okunamazsa o islem etiketsiz sayilir."""
    rows = []
    for t in ledger.list_closed_trades(limit=ledger.LIST_CLOSED_MAX):
        try:
            feats = dict(ledger.get_decision(t.decision_id).features)
        except Exception:  # noqa: BLE001
            feats = {}
        rows.append({"exit_ts": t.exit_ts, "pnl": t.realized_pnl, "pair": t.pair, "features": feats})
    return rows


def yaz_atomik(yol: Path, metin: str) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(yol.parent), prefix=".hs-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(metin)
        os.replace(tmp, yol)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def yaz(ledger: Any, simdi: datetime, yol: Path) -> dict:
    veri = olustur(defterden_satirlar(ledger), simdi)
    yaz_atomik(yol, json.dumps(veri, ensure_ascii=False, indent=1) + "\n")
    return veri


def telegram_satiri(veri: Any) -> str:
    """Haftalik rapor icin 1-2 satir (son 7 gun). Veri/islem yoksa 'Haber×sonuç: henüz veri yok'."""
    yok = "Haber×sonuç: henüz veri yok"
    try:
        tb = veri["tablolar"]
        if not isinstance(veri, dict) or veri.get("sema") != SEMA or not sum(r["n"] for r in tb["duygu"]):
            return yok

        def ozet(ad: str, satirlar: list[dict], bos: str) -> str | None:
            b = [r for r in satirlar if r["etiket"] != bos and int(r["n"]) >= 1]
            if not b:
                return None
            iyi, kotu = max(b, key=lambda r: r["toplam_pnl"]), min(b, key=lambda r: r["toplam_pnl"])
            f = lambda r: f"{r['etiket']} {r['toplam_pnl']:+.2f} $ (n={r['n']})".replace(".", ",")  # noqa: E731
            return f"{ad}: en iyi {f(iyi)}, en kötü {f(kotu)}"

        par = [ozet("Duygu", tb["duygu"], ETIKET_YOK), ozet("Haber tonu", tb["haber_ton"], HABER_YOK)]
        par = [p for p in par if p]
        if not par:
            return f"Haber×sonuç (7g): {sum(r['n'] for r in tb['duygu'])} işlem, etiketli işlem yok"
        return "Haber×sonuç (7g) — " + "; ".join(par)
    except Exception:  # noqa: BLE001
        return yok
