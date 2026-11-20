#!/usr/bin/env python3
"""CT/C1 ayriligi: tek seferlik, idempotent veri temizligi (docs/motor/ct-ayrilik-spec.md bolum 4). Saf stdlib; hata tolere eder.

Yaptiklari (hepsi dosya duzeyi; tekrar calistirmada no-op):
  1) var/ct/ (CT kadro dosyalari) silinir.
  2) Ogrenme paketleri: `**/models/ortak_filtre/aile_C1.json` ve `eski_kol/` altinda C1 kolu dosyalari silinir.
  3) `paper_models.csv`: C1 satirlari cikarilir (dosya atomik yeniden yazilir).
  4) `var/<bot>/arms_off.json`: C1 anahtarlari cikarilir.
  5) `var/durum/etiket_kurallari_v1.json`: kaldirilan `etiket_kalabalik` kurali durum kaydi cikarilir.
  6) Saglik durum dosyasi (--saglik-durum): kaldirilan `ct_kadro|bayat` uyari kaydi cikarilir (yoksa "Duzeldi" mesaji gider).
  7) Defter RAPORU (salt okunur): C1 karar/islem sayisi ve toplam net K/Z hesaplanir, yalniz yazdirilir (goc oncesi bilgi).

DEFTERE/STATE'E DOKUNULMAZ (onlar `scripts/c1_goc.py` / `trader_core/kol_kaldirma.py` ile, yedekli ve dogrulamali goc'tur): defter tablolari yalnizca-ekleme tetikleyicileriyle korunur (trg_*_no_update/no_delete) ve her acilista
`_verify` tetikleyici eksikse reddeder; ayrica kasa/mutabakat islem toplamlarindan turetilir. C1 satirlarini silmek bu butunluk
mekanizmasini bilincli bir goc'e (tetikleyicileri yeniden kuran, yedekli) baglar; bu betik bunu YAPMAZ (spec bolum 5).

Isaret dosyasi var/c1_temizle.done YALNIZ yukaridaki dosya adimlari hatasiz bitince yazilir."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ISARET = "c1_temizle.done"
KOL_RE = re.compile(r"(?<![A-Za-z0-9])C1(?![A-Za-z0-9])")
KALABALIK = "etiket_kalabalik"
SAGLIK_FP = "ct_kadro|bayat"


def _atomik_yaz(yol: Path, metin: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(yol.parent), prefix=yol.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(metin)
        os.replace(tmp, yol)
    except BaseException:
        try:
            os.unlink(tmp)
        finally:
            raise


def _sil(yol: Path, ozet: dict, anahtar: str) -> None:
    if yol.is_dir() and not yol.is_symlink():
        shutil.rmtree(yol)
    elif yol.exists() or yol.is_symlink():
        yol.unlink()
    else:
        return
    ozet[anahtar] = ozet.get(anahtar, 0) + 1


def ct_dizini(var: Path, ozet: dict) -> None:
    _sil(var / "ct", ozet, "ct_dizini")


def ogrenme_paketleri(var: Path, ozet: dict) -> None:
    for klasor in var.rglob("ortak_filtre"):
        if not klasor.is_dir():
            continue
        for p in list(klasor.iterdir()):
            if p.is_file() and KOL_RE.search(p.stem.replace("aile_", "")):
                _sil(p, ozet, "paket")
        eski = klasor / "eski_kol"
        if eski.is_dir():
            for p in list(eski.iterdir()):
                if KOL_RE.search(p.name):
                    _sil(p, ozet, "paket")


def paper_models(var: Path, ozet: dict) -> None:
    for p in var.rglob("paper_models.csv"):
        try:
            satirlar = list(csv.reader(p.read_text(encoding="utf-8").splitlines()))
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
        kalan = [r for i, r in enumerate(satirlar) if i == 0 or not any(KOL_RE.search(h) for h in r)]
        if len(kalan) == len(satirlar):
            continue
        import io
        b = io.StringIO()
        csv.writer(b, lineterminator="\n").writerows(kalan)
        _atomik_yaz(p, b.getvalue())
        ozet["paper_models_satir"] = ozet.get("paper_models_satir", 0) + len(satirlar) - len(kalan)


def _json_oku(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _c1_anahtarsiz(x):
    """Sozluk/liste icinden C1 kolunu tasiyan anahtar ve ogeleri cikarir. (yeni, degisti)"""
    if isinstance(x, dict):
        yeni, dg = {}, False
        for k, v in x.items():
            if isinstance(k, str) and KOL_RE.search(k):
                dg = True
                continue
            v2, d2 = _c1_anahtarsiz(v)
            yeni[k], dg = v2, dg or d2
        return yeni, dg
    if isinstance(x, list):
        yeni, dg = [], False
        for v in x:
            if isinstance(v, str) and KOL_RE.search(v):
                dg = True
                continue
            v2, d2 = _c1_anahtarsiz(v)
            yeni.append(v2)
            dg = dg or d2
        return yeni, dg
    return x, False


def arms_off(var: Path, ozet: dict) -> None:
    for p in var.glob("*/arms_off.json"):
        doc = _json_oku(p)
        if doc is None:
            continue
        yeni, dg = _c1_anahtarsiz(doc)
        if dg:
            _atomik_yaz(p, json.dumps(yeni, ensure_ascii=False, indent=1) + "\n")
            ozet["arms_off"] = ozet.get("arms_off", 0) + 1


def etiket_durumu(var: Path, ozet: dict) -> None:
    p = var / "durum" / "etiket_kurallari_v1.json"
    doc = _json_oku(p)
    if isinstance(doc, dict) and isinstance(doc.get("kurallar"), dict) and KALABALIK in doc["kurallar"]:
        del doc["kurallar"][KALABALIK]
        _atomik_yaz(p, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        ozet["etiket_durumu"] = 1


def saglik_durumu(yol: Path | None, ozet: dict) -> None:
    if yol is None:
        return
    doc = _json_oku(yol)
    if isinstance(doc, dict) and isinstance(doc.get("ek_uyarilar"), dict) and SAGLIK_FP in doc["ek_uyarilar"]:
        del doc["ek_uyarilar"][SAGLIK_FP]
        _atomik_yaz(yol, json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        ozet["saglik_durumu"] = 1


def defter_raporu(yol: Path) -> dict | None:
    """Salt okunur: C1 karar/islem sayisi ve kapanmis islemlerin toplam net K/Z'si. Yazmaz, silmez."""
    if not yol.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=10)
        try:
            kar = con.execute("SELECT COUNT(*) FROM decision_events WHERE setup='C1'").fetchone()[0]
            isl = con.execute("SELECT COUNT(*), COALESCE(SUM(realized_pnl),0), COALESCE(SUM(fee_entry),0) "
                              "FROM v_trades WHERE setup='C1'").fetchone()
            kap = con.execute("SELECT COUNT(*), COALESCE(SUM(realized_pnl),0), COALESCE(SUM(fee_exit),0), COALESCE(SUM(funding_paid),0) "
                              "FROM v_closed_trades WHERE setup='C1'").fetchone()
        finally:
            con.close()
    except sqlite3.Error as e:
        return {"hata": str(e)}
    return {"c1_karar": kar, "c1_islem": isl[0], "c1_kapanan": kap[0], "c1_net_kz": round(float(kap[1]), 6),
            "c1_giris_komisyon": round(float(isl[2]), 6), "c1_cikis_komisyon": round(float(kap[2]), 6),
            "c1_fonlama": round(float(kap[3]), 6)}


def calistir(var: Path, *, saglik_durum: Path | None = None, defter: Path | None = None, isaret_yaz: bool = True) -> dict:
    ozet: dict = {}
    for ad, fn in (("ct", ct_dizini), ("paketler", ogrenme_paketleri), ("paper_models", paper_models), ("arms_off", arms_off),
                   ("etiket", etiket_durumu)):
        fn(var, ozet)
    try:
        saglik_durumu(saglik_durum, ozet)
    except OSError as e:                      # baska kullanicinin dosyasi olabilir: temizlik bununla basarisiz sayilmaz
        ozet["saglik_durumu_hata"] = str(e)
    ozet["defter_rapor"] = defter_raporu(defter if defter is not None else var / "learner" / "ledger.sqlite")
    ozet["defter_dokunuldu"] = False
    if isaret_yaz:
        _atomik_yaz(var / ISARET, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")
    return ozet


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--var-dir", required=True)
    ap.add_argument("--saglik-durum", default=None, help="saglik izleyici durum dosyasi (ek_uyarilar)")
    ap.add_argument("--defter", default=None, help="salt okunur rapor icin defter (varsayilan var/learner/ledger.sqlite)")
    ap.add_argument("--isaret-yok", action="store_true", help="isaret dosyasi yazma (deneme)")
    a = ap.parse_args(argv)
    var = Path(a.var_dir)
    if not var.is_dir():
        print(f"var dizini yok: {var}", file=sys.stderr)
        return 1
    try:
        ozet = calistir(var, saglik_durum=Path(a.saglik_durum) if a.saglik_durum else None,
                        defter=Path(a.defter) if a.defter else None, isaret_yaz=not a.isaret_yok)
    except OSError as e:
        print(f"C1 temizligi basarisiz: {e}", file=sys.stderr)
        return 1
    print(json.dumps(ozet, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
