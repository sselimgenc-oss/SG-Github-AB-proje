"""Etiket kurallari (kagit, 19-20 Kasim 2026): mevcut etiketler (rejim, duygu, CT kalabalik) bir girisi YALNIZ atlatabilir.

Saf mantik (ag/dosya yok, motor bagimliligi yok). Belirtim: docs/etiket-kurallari-spec.md. Desen: 1L3A `etiket_kurallari`.
- Kurallar yalnizca "hayir" diyebilir: boyut/kaldirac/limit/stop degismez; yeni giris acilmaz.
- Veri yok/bayat -> kural engellemez (fail-open) ve bunu sayar.
- Otomatik geri alma + yeniden acma (histerezis): kural acikken atladigi islemlerin karsi-olgu toplami (R) pencerede > +kapat_esik_r ise
  kapanir; kapaliyken kural "atlardi" islemleri yine NOT EDER (giris yapilir, `features.etiket_atlardi`) ve gercek sonuclari izlenir;
  son pencerede toplam < ac_esik_r (atlamak kazandirirdi) ise kural yeniden acilir. Her olay tarihle saklanir.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEMA = "ml.etiket_kurallari.v1"
DOSYA = "etiket_kurallari_v1.json"

REJIM, DUYGU, KALABALIK = "etiket_rejim", "etiket_duygu", "etiket_kalabalik"
KURALLAR = (REJIM, DUYGU, KALABALIK)
CFG_ANAHTAR = {"rejim": REJIM, "duygu": DUYGU, "kalabalik": KALABALIK}
SADE_AD = {REJIM: "rejim karşıtı", DUYGU: "uç duygu karşıtı", KALABALIK: "kalabalık yönü"}
VERI_ADI = {REJIM: "rejim", DUYGU: "duygu", KALABALIK: "CT kadro"}
FEATURE_ANAHTAR = "etiket_atlardi"        # defter features: kapali kuralin atlayacagi islem (virgullu kural kodlari)

VARSAYILAN = {
    "rejim": {"acik": True},
    "duygu": {"acik": True, "asiri_korku_max": 20, "asiri_acgozluluk_min": 80},
    "kalabalik": {"acik": True, "min_trader": 10, "oran_min": 0.8},
    "otomatik": {"pencere": 10, "kapat_esik_r": 1.0, "ac_esik_r": -1.0},
}


class EtiketConfigHatasi(ValueError):
    pass


def _sayi(ad: str, v: Any, lo: float, hi: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise EtiketConfigHatasi(f"etiket_kurallari.{ad} [{lo}, {hi}] araliginda sayi olmali: {v!r}")
    return float(v)


def build_config(raw: Any) -> dict:
    """Ham `etiket_kurallari` -> dogrulanmis sozluk. Bos/None -> {} (kapali). Bilinmeyen anahtar reddedilir."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, Mapping):
        raise EtiketConfigHatasi(f"etiket_kurallari nesne olmali: {raw!r}")
    out: dict = {}
    for k in raw:
        if k not in VARSAYILAN:
            raise EtiketConfigHatasi(f"etiket_kurallari bilinmeyen anahtar: {k!r}")
    for bolum, vars_ in VARSAYILAN.items():
        sec = raw.get(bolum, {})
        if not isinstance(sec, Mapping):
            raise EtiketConfigHatasi(f"etiket_kurallari.{bolum} nesne olmali")
        for k in sec:
            if k not in vars_:
                raise EtiketConfigHatasi(f"etiket_kurallari.{bolum} bilinmeyen anahtar: {k!r}")
        d = {**vars_, **sec}
        if "acik" in d and not isinstance(d["acik"], bool):
            raise EtiketConfigHatasi(f"etiket_kurallari.{bolum}.acik bool olmali")
        out[bolum] = d
    dg = out["duygu"]
    dg["asiri_korku_max"] = _sayi("duygu.asiri_korku_max", dg["asiri_korku_max"], 0, 50)
    dg["asiri_acgozluluk_min"] = _sayi("duygu.asiri_acgozluluk_min", dg["asiri_acgozluluk_min"], 50, 100)
    kb = out["kalabalik"]
    kb["min_trader"] = int(_sayi("kalabalik.min_trader", kb["min_trader"], 1, 10000))
    kb["oran_min"] = _sayi("kalabalik.oran_min", kb["oran_min"], 0.5, 1.0)
    ot = out["otomatik"]
    ot["pencere"] = int(_sayi("otomatik.pencere", ot["pencere"], 3, 1000))
    ot["kapat_esik_r"] = _sayi("otomatik.kapat_esik_r", ot["kapat_esik_r"], 0, 100)
    ot["ac_esik_r"] = _sayi("otomatik.ac_esik_r", ot["ac_esik_r"], -100, 0)
    return out


def kural_acik_config(cfg: Mapping | None, kod: str) -> bool:
    if not cfg:
        return False
    sec = {v: k for k, v in CFG_ANAHTAR.items()}[kod]
    return bool(cfg.get(sec, {}).get("acik"))


# ---------------------------------------------------------------- kural mantigi
def degerlendir(side: str, regime: str | None, duygu: Mapping | None, ct: Mapping | None, cfg: Mapping | None
                ) -> tuple[list[tuple[str, str]], list[str]]:
    """Doner: (tetiklenenler [(kural, ayrinti)], veri_yok [kural]). Yalniz config'te acik kurallar degerlendirilir.
    Veri yoksa kural tetiklenmez (fail-open) ve `veri_yok`ta listelenir."""
    if not cfg or side not in ("long", "short"):
        return [], []
    tet: list[tuple[str, str]] = []
    yok: list[str] = []
    if kural_acik_config(cfg, REJIM):
        if regime in ("trend_up", "trend_down"):
            if (side == "long" and regime == "trend_down") or (side == "short" and regime == "trend_up"):
                tet.append((REJIM, f"{side}/{regime}"))
        elif regime is None:
            yok.append(REJIM)
    if kural_acik_config(cfg, DUYGU):
        d = duygu.get("deger") if isinstance(duygu, Mapping) else None
        if isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d):
            yok.append(DUYGU)
        else:
            c = cfg["duygu"]
            if side == "long" and d <= c["asiri_korku_max"]:
                tet.append((DUYGU, f"long/korku={int(d)}"))
            elif side == "short" and d >= c["asiri_acgozluluk_min"]:
                tet.append((DUYGU, f"short/acgozluluk={int(d)}"))
    if kural_acik_config(cfg, KALABALIK):
        if not isinstance(ct, Mapping):
            yok.append(KALABALIK)
        else:
            c = cfg["kalabalik"]
            lg, sh = ct.get("long"), ct.get("short")
            if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in (lg, sh)):
                yok.append(KALABALIK)
            else:
                toplam = lg + sh
                taraf = lg if side == "long" else sh
                if ct.get("net_yon") == side and toplam >= c["min_trader"] and taraf / toplam >= c["oran_min"]:
                    tet.append((KALABALIK, f"{side}/{taraf}-{toplam}"))
    return tet, yok


# ---------------------------------------------------------------- durum (acik/kapali + gecmis)
def _utc(dt: Any) -> datetime | None:
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(dt, datetime):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bos_durum() -> dict:
    return {"sema": SEMA, "uretim": None, "kurallar": {k: {"acik": True, "gecmis": []} for k in KURALLAR}}


def durum_oku(yol: str | os.PathLike | None) -> dict:
    """Durum dosyasi; yok/bozuk -> hepsi acik (config belirler). Istisna firlatmaz."""
    d = bos_durum()
    try:
        raw = json.loads(Path(yol).read_text(encoding="utf-8"))
        if raw.get("sema") != SEMA:
            return d
        for k in KURALLAR:
            e = raw["kurallar"].get(k)
            if isinstance(e, Mapping) and isinstance(e.get("acik"), bool) and isinstance(e.get("gecmis"), list):
                d["kurallar"][k] = {"acik": e["acik"], "gecmis": [g for g in e["gecmis"] if isinstance(g, Mapping)]}
        d["uretim"] = raw.get("uretim")
    except Exception:  # noqa: BLE001 - yok/bozuk: varsayilan
        return bos_durum()
    return d


def acik_haritasi(durum: Mapping) -> dict[str, bool]:
    return {k: bool(durum["kurallar"][k]["acik"]) for k in KURALLAR}


def yaz_atomik(yol: str | os.PathLike, doc: Mapping) -> None:
    p = Path(yol)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        finally:
            raise


def _son_olay_ts(e: Mapping) -> datetime | None:
    g = e.get("gecmis") or []
    return _utc(g[-1].get("ts")) if g else None


def _pencere_toplam(rows: Iterable[Mapping], since: datetime | None, n: int) -> tuple[int, float]:
    """Son olaydan sonraki (kesin >) sonuclu satirlarin son `n` tanesi: (adet, toplam R)."""
    sec = []
    for r in rows:
        t = _utc(r.get("ts"))
        try:
            v = float(r.get("r"))
        except (TypeError, ValueError):
            continue
        if t is None or not math.isfinite(v) or (since is not None and t <= since):
            continue
        sec.append((t, v))
    sec.sort(key=lambda x: x[0])
    son = [v for _, v in sec[-n:]]
    return len(son), sum(son)


def guncelle(onceki: Mapping, cf_satirlari: Iterable[Mapping], gercek_satirlar: Iterable[Mapping], cfg: Mapping | None,
             simdi: datetime) -> tuple[dict, list[dict]]:
    """Saf. cf_satirlari: [{skip_reason, ts (karar zamani), r}] (kural acikken atladiklarinin "alinsaydi" R'si);
    gercek_satirlar: [{kural, ts (kapanis), r}] (kural kapaliyken "atlardi" olup girilen islemlerin gercek R'si).
    Doner: (yeni durum, olaylar [{kural, olay: kapandi|acildi, ts, n, toplam_r, neden}]). cfg yoksa degisiklik yok."""
    yeni = {"sema": SEMA, "uretim": _z(simdi), "kurallar": {}}
    olaylar: list[dict] = []
    ot = (cfg or {}).get("otomatik") or VARSAYILAN["otomatik"]
    cf_satirlari, gercek_satirlar = list(cf_satirlari), list(gercek_satirlar)
    for k in KURALLAR:
        e = (onceki.get("kurallar") or {}).get(k) or {"acik": True, "gecmis": []}
        e = {"acik": bool(e.get("acik", True)), "gecmis": list(e.get("gecmis") or [])}
        if cfg and kural_acik_config(cfg, k):
            since = _son_olay_ts(e)
            if e["acik"]:
                n, top = _pencere_toplam((r for r in cf_satirlari if r.get("skip_reason") == k), since, ot["pencere"])
                if n >= ot["pencere"] and top > ot["kapat_esik_r"]:
                    ev = {"kural": k, "olay": "kapandi", "ts": _z(simdi), "n": n, "toplam_r": round(top, 3),
                          "neden": "atladığı işlemler kâr ederdi"}
                    e["acik"] = False
                    e["gecmis"].append({a: b for a, b in ev.items() if a != "kural"})
                    olaylar.append(ev)
            else:
                n, top = _pencere_toplam((r for r in gercek_satirlar if r.get("kural") == k), since, ot["pencere"])
                if n >= ot["pencere"] and top < ot["ac_esik_r"]:
                    ev = {"kural": k, "olay": "acildi", "ts": _z(simdi), "n": n, "toplam_r": round(top, 3),
                          "neden": "atlamak kazandırırdı"}
                    e["acik"] = True
                    e["gecmis"].append({a: b for a, b in ev.items() if a != "kural"})
                    olaylar.append(ev)
        yeni["kurallar"][k] = e
    return yeni, olaylar


def olay_satiri(ev: Mapping) -> str:
    ad = SADE_AD.get(ev.get("kural"), str(ev.get("kural")))
    if ev.get("olay") == "kapandi":
        return f"Etiket kuralı kapatıldı: {ad} (atladığı işlemler kâr ederdi)"
    return f"Etiket kuralı yeniden açıldı: {ad} (atlamak kazandırırdı)"


def durum_etiketi(e: Mapping) -> str:
    """Panel/Telegram: 'Açık' | 'Kanıta göre kapandı (GG.AA)' | 'Kanıta göre yeniden açıldı (GG.AA)'."""
    g = (e.get("gecmis") or [])
    if not g:
        return "Açık"
    t = _utc(g[-1].get("ts"))
    tarih = t.strftime("%d.%m.%Y") if t else "?"
    if not e.get("acik"):
        return f"Kanıta göre kapandı ({tarih})"
    return f"Kanıta göre yeniden açıldı ({tarih})" if g[-1].get("olay") == "acildi" else "Açık"


# ---------------------------------------------------------------- girdiler (defter + karsi-olgu)
def gercek_satirlari(decisions: Iterable[Any], trades: Iterable[Any]) -> list[dict]:
    """Kural kapaliyken 'atlardi' olan girilmis islemler: karar `features.etiket_atlardi` -> kapanan islemin r_multiple'i."""
    atla: dict[Any, list[str]] = {}
    for d in decisions:
        if getattr(d, "final_action", None) != "entered":
            continue
        f = getattr(d, "features", None)
        if isinstance(f, str):
            try:
                f = json.loads(f)
            except ValueError:
                continue
        v = f.get(FEATURE_ANAHTAR) if isinstance(f, Mapping) else None
        if isinstance(v, str) and v:
            atla[d.id] = [x for x in v.split(",") if x in KURALLAR]
    out = []
    for t in trades:
        r = getattr(t, "r_multiple", None)
        for k in atla.get(getattr(t, "decision_id", None), []):
            out.append({"kural": k, "ts": getattr(t, "exit_ts", None), "r": r})
    return out


def kart_verisi(durum: Mapping, durum_var: bool, alinmayan: Mapping | None) -> dict | None:
    """Panel karti. durum: durum_oku(); alinmayan: `ml.alinmayan_sonuc.v1` belgesi (son 7 gun `tablolar.neden` + `cozulmedi`).
    Her kural: acik/kapali, durum metni, son 7 gunde atladigi islem sayisi (cozulen + cozulmeyen), alinsaydi sonucu (R, cozulenler; yoksa None).
    Durum dosyasi yok ve atlanan yoksa None (kart gizlenir)."""
    tab = ((alinmayan or {}).get("tablolar") or {}).get("neden") or []
    coz = (((alinmayan or {}).get("cozulmedi") or {}).get("tablolar")) or {}
    satirlar = []
    for k in KURALLAR:
        e = (durum.get("kurallar") or {}).get(k) or {"acik": True, "gecmis": []}
        row = next((r for r in tab if isinstance(r, Mapping) and r.get("etiket") == k), None)
        n_coz = int(row["n"]) if row else 0
        satirlar.append({"kural": k, "ad": SADE_AD[k], "acik": bool(e.get("acik", True)), "durum": durum_etiketi(e),
                         "atlanan_7g": n_coz + int(coz.get(k, 0) or 0), "cozulen": n_coz,
                         "alinsaydi_r": row.get("toplam_pnl") if row else None,
                         "gecmis": list(e.get("gecmis") or [])[-5:]})
    if not durum_var and not any(s["atlanan_7g"] for s in satirlar):
        return None
    return {"kurallar": satirlar, "birim": "R"}


# ---------------------------------------------------------------- gece isi (karsi-olgu betigi cagirir)
def yaz_gece(ledger_yol, cf_yol, bot: str, simdi: datetime, durum_yol, ham_cfg: Any) -> list[dict] | None:
    """Defteri (salt okunur) ve karsi-olgu deposunu okur, kural durumunu gunceller, dosyaya atomik yazar. Doner: olaylar (None = yapilmadi).
    Her hata yutulur (bilgi/guvenlik isi; motoru etkilemez; durum dosyasi bozulmaz)."""
    try:
        cfg = build_config(ham_cfg)
        if not cfg:
            return None
        from . import alinmayan_sonuc as AS
        from . import ledger as L
        led = L.open_ledger(str(ledger_yol), bot, create=False, read_only=True, migrate=False)
        try:
            kararlar = led.list_decisions()
            kapanan = led.list_closed_trades(limit=led.LIST_CLOSED_MAX)
        finally:
            led.close()
        cf = AS._cf_satirlari(Path(cf_yol), bot)
        gercek = gercek_satirlari(kararlar, kapanan)
        yeni, olaylar = guncelle(durum_oku(durum_yol), cf, gercek, cfg, simdi)
        yaz_atomik(durum_yol, yeni)
        return olaylar
    except Exception:  # noqa: BLE001
        return None
