"""Pano (Aşama 3): durum dosyalarını okuyup TEK DOSYALIK statik HTML + terminal özeti + Telegram kısa metni üretir.

İLKE (DURUM.md Aşama 3): PANO YENİ HESAP YAPMAZ. Gösterilen her sayı durum dosyasında (motorun yazdığı) olduğu gibi vardır;
burada yalnız biçimlendirme (yüzde işareti, binlik ayraç), sıralama, ilk-N kesme ve çizim ölçekleme yapılır. Tek istisna ZAMAN karşılaştırmasıdır:
dosya yaşı (şimdi - durum zamanı) motor ölmüşse eski dosyanın 'sağlıklı' görünmemesi için eşikle (saglik.json'daki
`dosya_esik_dk`) karşılaştırılır. Durum dosyası yok/bozuksa açık hata gösterilir; uydurma değer yazılmaz.
Gösterim saatleri Türkiye saatidir (TSİ, Europe/Istanbul); terminal/Telegram metni UTC kalır. Tarayıcı JS'i yalnız
yazildi_zaman bayatlık bandını açar (gösterim kontrolü; JS yoksa sayfa yine çalışır).
Telegram: bu modül MESAJ GÖNDERMEZ, yalnız metin üretir (`telegram_metni`).

CLI: python -m motor.canli.pano [--durum durum] [--cikti durum/pano.html] [--simdi 2026-11-07T12:00:00Z]
Çıkış kodu: 0 sorunsuz, 1 durum sorunu (dosya eksik/bozuk), 2 kritik uyarı (bayat veri / kill / alarm) — HTML her durumda yazılır.
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html import escape as esc
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from motor.canli import durum as d
from motor.canli import hesap_adlari as ha
from motor.canli.telegram import tr_sayi            # Telegram ile aynı sayı biçimi (tek kaynak)
from motor.risk.limitler import SERT_LIMITLER      # risk limitleri tek kaynaktan (kopya yok); pano yalnız okur

BANT_ADI = {"p05_alti": "%5 altı", "p05_p25": "%5–%25", "p25_p50": "%25–%50", "p50_p75": "%50–%75", "p75_p95": "%75–%95",
            "p95_ustu": "%95 üstü"}
BANT_SEVIYE = {"p05_alti": "kotu", "p05_p25": "uyari", "p25_p50": "iyi", "p50_p75": "iyi", "p75_p95": "iyi", "p95_ustu": "uyari"}
KAYNAK_ADI = {"backtest": "BACKTEST (canlı değil)", "paper": "KÂĞIT", "canli": "CANLI"}


# ----------------------------------------------------------------------------------------------- biçimleyiciler
def _tr(x, ondalik: int = 2, isaretli: bool = False) -> str:
    """Türkçe sayı gösterimi (Telegram ile aynı kural: binlik nokta, ondalık virgül, eksi '−'): 10250.5 -> '10.250,50'.
    isaretli: pozitif/sıfır için '+'. Yalnız GÖSTERİM; makine biçimi (data-*, SVG koordinatı) bunu kullanmaz."""
    v = x if isinstance(x, Decimal) else Decimal(str(x))
    s = tr_sayi(abs(v), ondalik)
    return ("−" if v < 0 else ("+" if isaretli else "")) + s


def f_yuzde(x: Optional[float], isaretli: bool = False, ondalik: int = 2) -> str:
    """Oran -> '%2,51' / '+%2,51' / '−%0,12' (Telegram ile aynı: % önde)."""
    if x is None:
        return "—"
    v = Decimal(str(x)) * 100
    return ("−" if v < 0 else ("+" if isaretli else "")) + "%" + tr_sayi(abs(v), ondalik)


def f_para(s: Optional[str], isaretli: bool = False) -> str:
    """Durum dosyasındaki para metni -> '10.250,55' (değer değişmez)."""
    if s is None:
        return "—"
    return _tr(Decimal(s), 2, isaretli)


def f_sayi(x: Optional[float], ondalik: int = 2) -> str:
    return "—" if x is None else _tr(x, ondalik)


def kisa_kimlik(k: str) -> str:
    """'strateji|SEMBOL|tf' -> 'strateji · SEMBOL · tf' (ön ek __ öncesi kısaltılmaz; yalnız ayraç)."""
    return k.replace("|", " · ")


# ----------------------------------------------------------------------------------------------- uyarılar (durum dosyasındaki bayraklar)
def uyarilar(veri: dict, sorunlar: list, simdi: datetime) -> list:
    """-> [(seviye 'kritik'|'uyari'|'bilgi', metin)]. Hesap değil: dosyadaki bayrakların ve zamanların okunması."""
    u = [("kritik", f"Durum sorunu: {s}") for s in sorunlar]
    oz, sg, st = veri.get("ozet"), veri.get("saglik"), veri.get("stratejiler")
    if oz and oz["kaynak"] == "backtest":
        u.append(("bilgi", f"BACKTEST görünümü — dönem {_gun_tr(oz['donem']['bas'][:10])} → {_gun_tr(oz['donem']['bit'][:10])}; canlı/paper verisi değildir."))
    if oz and sg and oz["kaynak"] != "backtest":
        esik = sg.get("dosya_esik_dk")
        yas_dk = (simdi - d.zaman_oku(oz["zaman"])).total_seconds() / 60
        if esik is None:
            u.append(("uyari", "Durum dosyasının yaşı denetlenemedi."))
        elif yas_dk > esik:
            u.append(("kritik", f"VERİ BAYAT: durum dosyası {_tr(yas_dk, 0)} dk önce yazıldı (eşik {esik} dk) — motor durmuş olabilir."))
    if sg:
        for v in sg["veri"]:
            if v["bayat"]:
                u.append(("kritik", f"VERİ BAYAT: {v['sembol']} {v['tf']} son mum {v['son_mum_zamani']} ({v['bayatlik_dk']} dk, eşik {v['esik_dk']} dk)"))
        if sg["durum"] != "ok":
            u.append(("kritik", f"Motor durumu: {sg['durum']}"))
        for m in sg["uyarilar"]:
            u.append(("bilgi" if oz and oz["kaynak"] == "backtest" else "uyari", m))
        u += [("uyari", "Karantinada (kod hatası; yeni giriş yok, açık pozisyon zarar-kes/hedefle sürer): " + ", ".join([*(_ad_goster(k) for k in kq.get("gorunur", [])), *([f"Diğer hesaplar ({kq['gizli']})"] if kq.get("gizli") else [])]))] if (kq := sg.get("karantina")) and (kq.get("gorunur") or kq.get("gizli")) else []
        # sg["bilgiler"] (beklenen/kalıcı durumlar, ör. Binance'te karşılığı olmayan semboller) ÜST bantta gösterilmez: yalnız SAĞLIK sekmesi (evren_disi tablosu).
    bt = veri.get("butunluk")
    if bt and bt.get("genel_durum") == "uyusmuyor":
        u.append(("uyari", "Backtest dosyalarının bütünlük denetimi başarısız."))
    if oz:
        r = oz["risk"]
        if r["kill_switch"]["tetiklendi"]:
            u.append(("kritik", "KILL SWITCH tetiklendi: tüm işlemler durdu."))
        if r["gunluk_kayip"].get("tetiklendi"):
            u.append(("kritik", "Günlük kayıp limiti tetiklendi: yeni işlem yok."))
    if st:
        for x in st["stratejiler"]:
            for hf, b in x["beklenti"].items():
                for m in ("net_getiri", "max_dusus"):
                    if b[m]["alarm"]:
                        u.append(("kritik", f"BEKLENTİ ALARMI: {_ad_goster(x['kimlik'])} {hf} hafta {m.replace('_', ' ')} {f_yuzde(b[m]['deger'], True)}"))
        for hf, b in st["set"]["beklenti"].items():
            for m in ("net_getiri", "max_dusus"):
                if b[m]["alarm"]:
                    u.append(("kritik", f"BEKLENTİ ALARMI: SET {hf} hafta {m.replace('_', ' ')} {f_yuzde(b[m]['deger'], True)}"))
    return u


def yukle(dizin) -> tuple:
    """Zorunlu 5 dosya + ek dosyalar (maruziyet, maliyet, reddedilen, olaylar, icgoruler). Ek dosya YOKSA değeri None (eski motor: ilgili
    kart 'veri yok' der, sorun sayılmaz); BOZUKSA None + sorun metni."""
    veri, sorunlar = d.oku_hepsi(dizin)
    for ad in d.EK_DOSYALAR:
        try:
            veri[ad] = d.ek_oku(dizin, ad)
        except d.DurumHatasi as e:
            veri[ad] = None
            sorunlar.append(str(e))
    try:                                                                      # CT / aday / öğrenme kartları: ortak okuyucu, hata sayfayı düşürmez
        from motor.canli import kurulum_ozeti as ko
        veri["kurulumlar"] = ko.hesaplar(dizin)
    except Exception:  # noqa: BLE001
        veri["kurulumlar"] = None
    try:
        from motor.canli import bosluk_maruziyet
        veri["bosluk"] = bosluk_maruziyet.oku(dizin)                          # boşluk riski kartı: yalnız okur
    except Exception:  # noqa: BLE001
        veri["bosluk"] = None
    veri["ogrenme_ek"] = _ogrenme_ek(dizin)                                   # ders / makine öğrenmesi kartları için ham kayıtlar
    veri["alinsaydi_gevsetme"] = _json_oku(dizin, "alinsaydi_gevsetme.json")      # başka ajan yazar; yoksa "Henüz değişiklik yok"
    veri["aday_hesap"] = _aday_oku()                                          # aday hesapların açık pozisyon + kapanan işlemleri (yalnız okur)
    veri["ct_hesap"] = _ct_oku()                                              # CT konsensüs açık pozisyon + kapanan işlemleri (ayrı durum dizini; yalnız okur)
    veri["alinmayan_sonuc"] = _json_oku(dizin, "alinmayan_sonuc.json")           # alınmayan sinyallerin "alınsaydı" sonucu: yalnız okur
    veri["cikis_kanit"] = {"karsi_olgu": _json_oku(dizin, "cikis_karsi_olgu.json"), "override": _json_oku(dizin, "cikis_override.json"),
                           "yasak": _json_oku(dizin, "cikis_yasak.json")}
    veri["disk"] = _disk_oku(dizin)
    veri["etiket_sonuc"] = _etiket_oku(dizin)                                 # etiket × sonuç kartı: yalnız okur; dosya yoksa "veri yok"
    return veri, sorunlar


def _hesap_oku(dizin, kimlik_sart: bool = False) -> Optional[dict]:
    """Bir hesabın açık pozisyonları (maruziyet.json) ve kapanan işlemleri (islemler.jsonl). Dizin yok -> None; bozuk satır atlanır."""
    dizin = Path(dizin)
    if not dizin.is_dir():
        return None
    gerekli = ("sembol", "yon", "kimlik") if kimlik_sart else ("sembol", "yon")
    mr = _json_oku(dizin, "maruziyet.json")
    poz = [{**p, "ct": True} for p in mr.get("pozisyonlar", []) if isinstance(p, dict) and all(k in p for k in gerekli)] if isinstance(mr, dict) else []
    isl = []
    try:
        satirlar = (dizin / "islemler.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        satirlar = []
    for ln in satirlar:
        try:
            isl.append({**d.dogrula_islem(json.loads(ln)), "ct": True})
        except (ValueError, TypeError, KeyError, d.DurumHatasi):
            continue
    return {"pozisyonlar": poz, "islemler": isl}


def _ct_oku() -> Optional[dict]:
    """CT konsensüs hesabı (ayrı durum dizini; yalnız okur). Dizin yok/okunamaz -> None."""
    try:
        from motor.canli import kurulum_ozeti as ko
        return _hesap_oku(ko.ct_dizini(), kimlik_sart=True)
    except Exception:  # noqa: BLE001
        return None


def _aday_oku() -> dict:
    """Aday hesapların (klasör adı -> {pozisyonlar, islemler}). Okunamazsa boş sözlük."""
    try:
        from motor.canli import kurulum_ozeti as ko
        kok = ko.aday_dizini()
        if not kok.is_dir():
            return {}
        out = {}
        for alt in sorted(p for p in kok.iterdir() if p.is_dir()):
            h = _hesap_oku(alt)
            if h is not None:
                out[alt.name] = h
        return out
    except Exception:  # noqa: BLE001
        return {}


_GIZLI: Optional[set] = None


class _HepsiGizli(set):
    """Gizli hesap listesi okunamadığında (kapalı-başarısız): her hesap gizli sayılır -> tüm adlar "Diğer hesap"; önbelleğe yazılmaz."""

    def __contains__(self, x) -> bool:
        return True


def _gizli_adlar() -> set:
    global _GIZLI
    if _GIZLI is None:
        try:
            from motor.canli import gunluk_ozet as go
            kayit = go._set_kayitlari(None)
            if kayit is None:
                raise ValueError("set kaydı okunamadı")
            _GIZLI = {k for k, _, g in kayit if not g}
        except Exception:  # noqa: BLE001
            return _HepsiGizli()                            # önbelleğe yazma: sonraki çağrı yeniden dener
    return _GIZLI


def _ad_goster(kimlik: str, ct: bool = False) -> str:
    """Tek ortak adlandırma (motor/canli/hesap_adlari.py): konsensüs hesabı "Konsensüs", gizli hesap "Diğer hesap" (adı asla yazılmaz)."""
    if ct or str(kimlik).startswith("ct_konsensus"):
        return KONSENSUS_AD
    return ha.hesap_adi(kimlik, gorunur=kimlik.split("|")[0] not in _gizli_adlar())


def _disk_oku(dizin) -> Optional[dict]:
    """Disk kartı: disk_bakim.json (durum dizininde, L3A_DISK_KOK'ta ya da bir üstte) + anlık doluluk. Okunamazsa None."""
    try:
        from motor.canli import disk_bakim
        durum = None
        for k in (Path(dizin), Path(os.environ.get("L3A_DISK_KOK") or disk_bakim.KOK_DIZIN), Path(dizin).parent):
            durum = _json_oku(k, disk_bakim.DURUM_DOSYASI)
            if isinstance(durum, dict):
                break
        try:
            olcum = disk_bakim.olc()
        except Exception:  # noqa: BLE001
            olcum = {}
        return {"durum": durum if isinstance(durum, dict) else None, "olcum": olcum}
    except Exception:  # noqa: BLE001
        return None


def _etiket_oku(dizin) -> Optional[dict]:
    try:
        o = json.loads((Path(dizin) / "etiket_sonuc_v1.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return o if isinstance(o, dict) and o.get("sema") == "etiket_sonuc.v1" else None


# ----------------------------------------------------------------------------------------------- terminal / telegram
def _beklenti_satiri(ad: str, b: dict) -> str:
    n = b["net_getiri"]
    return f"{ad}: net {f_yuzde(n['deger'], True)} [{BANT_ADI[n['bant']]}] (p50 {f_yuzde(n['p50'], True)}), düşüş {f_yuzde(b['max_dusus']['deger'])}"


def terminal_ozet(veri: dict, sorunlar: list, simdi: datetime) -> str:
    L = [f"1L3A PANO — {simdi:%Y-%m-%d %H:%M} UTC"]
    for sev, m in uyarilar(veri, sorunlar, simdi):
        L.append(f"[{sev.upper()}] {m}")
    oz = veri.get("ozet")
    if oz:
        r = oz["risk"]
        L += [f"Kaynak {KAYNAK_ADI[oz['kaynak']]} · durum zamanı {oz['zaman']}",
              f"Özsermaye {f_para(oz['ozsermaye'])} (başlangıç {f_para(oz['baslangic_ozsermaye'])}) · toplam {f_para(oz['toplam_pnl'], True)} "
              f"({f_yuzde(oz['toplam_getiri'], True)}) · gün {f_para(oz['gun_pnl'], True)} ({f_yuzde(oz['gun_getiri'], True)})",
              f"Zirveden düşüş {f_yuzde(oz['zirveden_dusus'])} · max düşüş {f_yuzde(oz['max_dusus'])} · durdurma sınırına kalan {f_yuzde(r['kill_switch']['mesafe'])}",
              f"Risk: günlük kayıp {f_yuzde(r['gunluk_kayip']['deger'])}/{f_yuzde(r['gunluk_kayip']['limit'], ondalik=0)} · "
              f"kaldıraç {f_sayi(r['kaldirac']['deger'])}/{f_sayi(r['kaldirac']['limit'], 1)} · açık zarar-kes riski "
              f"{f_yuzde(r['acik_stop_riski']['deger'])}/{f_yuzde(r['acik_stop_riski']['limit'], ondalik=0)}",
              f"Açık pozisyon {oz['sayaclar']['acik_pozisyon']} · kapanan işlem {oz['sayaclar']['kapanan_islem']}"]
    st = veri.get("stratejiler")
    if st:
        L.append("Stratejiler (katkı | işlem | 8 hafta konum):")
        for x in st["stratejiler"]:
            b8 = x["beklenti"].get("8")
            L.append(f"  {kisa_kimlik(x['kimlik'])}: {f_para(x['ozsermaye_katkisi'], True)} | {x['islem_sayisi']} | "
                     + (f"{f_yuzde(b8['net_getiri']['deger'], True)} [{BANT_ADI[b8['net_getiri']['bant']]}]" if b8 else "—"))
        for hf, b in sorted(st["set"]["beklenti"].items(), key=lambda kv: int(kv[0])):
            L.append("  " + _beklenti_satiri(f"SET {hf} hafta", b))
    return "\n".join(L)


def telegram_metni(veri: dict, sorunlar: list, simdi: datetime) -> str:
    """Telegram'a gidecek KISA düz metin (bu modül göndermez)."""
    oz, st = veri.get("ozet"), veri.get("stratejiler")
    L = []
    kritik = [m for s, m in uyarilar(veri, sorunlar, simdi) if s == "kritik"]
    if not oz:
        return "1L3A DURUM YOK\n" + "\n".join(kritik or ["ozet.json okunamadı"])
    r = oz["risk"]
    L.append(f"1L3A · {KAYNAK_ADI[oz['kaynak']]} · {oz['zaman'][:16].replace('T', ' ')}Z")
    L.append(f"Özsermaye {f_para(oz['ozsermaye'])} · gün {f_para(oz['gun_pnl'], True)} ({f_yuzde(oz['gun_getiri'], True)}) · toplam {f_yuzde(oz['toplam_getiri'], True)}")
    L.append(f"Düşüş {f_yuzde(oz['zirveden_dusus'])} (durdurma sınırına kalan {f_yuzde(r['kill_switch']['mesafe'])}) · gün kaybı {f_yuzde(r['gunluk_kayip']['deger'])}/{f_yuzde(r['gunluk_kayip']['limit'], ondalik=0)}")
    L.append(f"Açık {oz['sayaclar']['acik_pozisyon']} · kapanan {oz['sayaclar']['kapanan_islem']}")
    if st and "8" in st["set"]["beklenti"]:
        b = st["set"]["beklenti"]["8"]["net_getiri"]
        L.append(f"Set 8 hafta: {f_yuzde(b['deger'], True)} [{BANT_ADI[b['bant']]}]")
    for m in kritik:
        L.append("⚠ " + m)
    return "\n".join(L)


# ----------------------------------------------------------------------------------------------- HTML
CSS = """
:root{--bg:#f1f2f5;--kart:#fff;--yazi:#15171c;--sessiz:#5f6673;--cizgi:#d6d9e0;--iyi:#0d7a4c;--uyari:#8a6a00;--kotu:#c62828;--bilgi:#1f5fbf;--vurgu:#a85f00;--bar:#e6e9ef;--yan:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0a0a0b;--kart:#111113;--yazi:#e9e9ee;--sessiz:#8a8a94;--cizgi:#25252a;--iyi:#3ddc84;--uyari:#f5d90a;--kotu:#ff5d5d;--bilgi:#5b9dff;--vurgu:#f5a524;--bar:#1c1c21;--yan:#000}}
:root[data-theme="dark"]{--bg:#0a0a0b;--kart:#111113;--yazi:#e9e9ee;--sessiz:#8a8a94;--cizgi:#25252a;--iyi:#3ddc84;--uyari:#f5d90a;--kotu:#ff5d5d;--bilgi:#5b9dff;--vurgu:#f5a524;--bar:#1c1c21;--yan:#000}
:root[data-theme="light"]{--bg:#f1f2f5;--kart:#fff;--yazi:#15171c;--sessiz:#5f6673;--cizgi:#d6d9e0;--iyi:#0d7a4c;--uyari:#8a6a00;--kotu:#c62828;--bilgi:#1f5fbf;--vurgu:#a85f00;--bar:#e6e9ef;--yan:#fff}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--yazi);font:13px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;padding:12px}
main{max-width:1400px;margin:0 auto;padding-bottom:28px}
h1{font-size:15px;letter-spacing:.06em;margin:0}
button{white-space:nowrap;background:var(--kart);color:var(--yazi);border:1px solid var(--cizgi);border-radius:12px;padding:3px 10px;font:inherit;font-size:11px;cursor:pointer}
button:hover{border-color:var(--vurgu);color:var(--vurgu)}
.ust{display:flex;justify-content:space-between;align-items:center;gap:8px 14px;flex-wrap:wrap;margin-bottom:10px;padding-bottom:9px;border-bottom:1px solid var(--cizgi)}
.mk{display:flex;align-items:center;gap:9px}.lg0{background:var(--vurgu);color:#000;font-weight:800;padding:2px 7px;border-radius:12px}
.un{display:flex;align-items:center;gap:6px 12px;flex-wrap:wrap;font-size:11px}.so{color:var(--sessiz)}
.rozet{border:1px solid var(--vurgu);border-radius:12px;padding:1px 9px;color:var(--vurgu);font-size:11px;font-weight:700;letter-spacing:.06em}
.rozet.r-backtest{border-color:var(--bilgi);color:var(--bilgi)}.rozet.r-canli{border-color:var(--kotu);color:var(--kotu)}
.alt{color:var(--sessiz);font-size:11px}
.uyari{border-radius:12px;padding:8px 12px;margin:0 0 8px;border:1px solid var(--cizgi);background:var(--kart);border-left-width:4px}
.uyari.kritik{border-left-color:var(--kotu);background:color-mix(in srgb,var(--kotu) 13%,var(--kart));font-weight:700}
.uyari.uyari{border-left-color:var(--uyari)}.uyari.bilgi{border-left-color:var(--bilgi)}
.uyari.bayat-bant{background:var(--kotu);color:#fff;border-color:var(--kotu);font-weight:800}
.iyi{color:var(--iyi)}.kotu{color:var(--kotu)}.uyarir{color:var(--uyari)}
.izgara{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.izgara.c2{grid-template-columns:repeat(2,minmax(0,1fr))}.izgara.oto{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
.serit{grid-template-columns:repeat(3,minmax(0,1fr))}
@media (min-width:640px){.izgara.c4{grid-template-columns:repeat(4,minmax(0,1fr))}.izgara.oto{grid-template-columns:repeat(auto-fill,minmax(210px,1fr))}}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:12px;padding:8px 11px;min-width:0}
.kart .e{font-size:10px;letter-spacing:.09em;color:var(--sessiz);text-transform:uppercase}.kart .d{font-size:18px;font-weight:700;margin:2px 0;font-variant-numeric:tabular-nums}
.p .kart{background:var(--bg)}
.serit{gap:1px;background:var(--cizgi);border:1px solid var(--cizgi);margin-bottom:10px}
.serit .kart{border:0;border-radius:0;background:var(--kart);padding:9px 11px}.serit .d{font-size:17px}
.cubuk{height:7px;background:var(--bar);border-radius:4px;overflow:hidden;margin:5px 0 4px}.cubuk>i{display:block;height:100%;background:var(--vurgu)}.cubuk.k>i{background:var(--kotu)}
.sat{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid var(--bar)}
.sat:last-child{border-bottom:0}.sat>span{color:var(--sessiz);min-width:6ch}.sat>span b{color:var(--yazi)}.sat b{font-variant-numeric:tabular-nums;text-align:right}.sat b.nw{white-space:nowrap;flex:none;overflow-wrap:normal}
.kolonlar{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px}
.cip{border:1px solid var(--cizgi);border-radius:12px;padding:1px 7px;font-size:11px;white-space:nowrap}
.cip.iyi{border-color:var(--iyi)}.cip.uyari{border-color:var(--uyari);color:var(--uyari)}.cip.kotu{border-color:var(--kotu);color:var(--kotu);font-weight:700}
.ig{display:grid;grid-template-columns:minmax(0,1fr);gap:8px;margin-top:8px}.sag{display:contents}
.p{background:var(--kart);border:1px solid var(--cizgi);border-radius:12px;min-width:0}
.pb{font-size:10px;letter-spacing:.09em;color:var(--vurgu);text-transform:uppercase;padding:8px 11px;border-bottom:1px solid var(--cizgi);display:flex;justify-content:space-between;gap:10px}
.pb span{color:var(--sessiz);text-transform:none;letter-spacing:0;font-size:11px;text-align:right}
.pi{padding:10px 11px}.pi.duz{padding:0}.pi.duz>.kart{border:0;background:transparent}
.bol{margin-top:8px}.mr{padding:6px 0;border-bottom:1px solid var(--bar)}.mr:last-child{border-bottom:0}.mr .sat{border:0;padding:0}.mr .cubuk{margin:4px 0 2px}
svg{display:block;width:100%;height:auto}
.gk{display:grid;grid-template-columns:auto minmax(0,1fr);column-gap:7px}
.gk svg{height:130px}.yt{display:flex;flex-direction:column;justify-content:space-between;text-align:right;font-size:10px;color:var(--sessiz);font-variant-numeric:tabular-nums;padding:1px 0}
.gk .ek{grid-column:2;display:flex;justify-content:space-between;gap:8px;font-size:10px;color:var(--sessiz);margin-top:4px}
.gk.kz svg{height:110px}
.izg{stroke:var(--cizgi);stroke-width:1;vector-effect:non-scaling-stroke;opacity:.8}.baz{stroke:var(--sessiz);stroke-width:1;stroke-dasharray:4 3;vector-effect:non-scaling-stroke}
.cizgi{stroke:var(--vurgu);fill:none;stroke-width:1.8;vector-effect:non-scaling-stroke}.alan{fill:var(--vurgu);opacity:.14}
.cizgi.k{stroke:var(--kotu)}.alan.k{fill:var(--kotu);opacity:.18}
.bi{fill:var(--iyi)}.bk{fill:var(--kotu)}.taban{stroke:var(--sessiz);stroke-width:1;vector-effect:non-scaling-stroke;opacity:.6}
.grlej{margin-top:6px;text-align:center}.kb95{fill:var(--bilgi);opacity:.13}.kb75{fill:var(--bilgi);opacity:.25}.kn-med{fill:none;stroke:var(--bilgi);stroke-width:1.2;stroke-dasharray:3 2;vector-effect:non-scaling-stroke}.kn-nk{fill:var(--vurgu)}.cizgi.kc1{stroke:var(--uyari)}.cizgi.kc2{stroke:var(--bilgi)}.cizgi.kc3{stroke:var(--iyi);stroke-dasharray:4 3}.lg-i{display:inline-block;width:14px;height:4px;vertical-align:middle;margin-right:4px;border-radius:2px;background:var(--vurgu)}.lg-i.kb95{background:var(--bilgi);opacity:.35}.lg-i.kb75{background:var(--bilgi);opacity:.6}.lg-i.kn-medl{background:var(--bilgi)}.lg-i.gercl,.lg-paper{background:var(--vurgu)}.lg-btc{background:var(--uyari)}.lg-spx{background:var(--bilgi)}.lg-mevduat{background:var(--iyi)}.kor{display:block;text-align:center;padding:2px 4px;border-radius:2px;font-variant-numeric:tabular-nums}
.is{padding:5px 0;border-bottom:1px solid var(--bar)}.is:last-child{border-bottom:0}
.ic>div{padding:5px 0 5px 14px;border-bottom:1px solid var(--bar);position:relative;font-size:12px}.ic>div:last-child{border-bottom:0}.ic>div:before{content:"›";color:var(--vurgu);position:absolute;left:0}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%;border:1px solid var(--cizgi);border-radius:12px;background:var(--kart)}
.p .tw{border:0;border-radius:0;background:transparent}.kay{max-height:420px;overflow:auto}.kay>.tw{overflow:visible}.kay th{position:sticky;top:0;z-index:1}
table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px;text-align:left;white-space:nowrap;border-bottom:1px solid var(--bar)}
th{font-size:10px;color:var(--sessiz);text-transform:uppercase;letter-spacing:.08em;font-weight:600;background:color-mix(in srgb,var(--bg) 55%,var(--kart))}
td.sg,th.sg{text-align:right}tbody tr:last-child td{border-bottom:0}tbody tr:hover td{background:color-mix(in srgb,var(--vurgu) 6%,transparent)}
.sekme-kok{margin-top:2px;position:relative}
input[name=t]{position:absolute;opacity:0;pointer-events:none}
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--cizgi);overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:thin}
.tabs label{flex:0 0 auto;padding:9px 14px 8px;font-size:11px;font-weight:600;letter-spacing:.09em;color:var(--sessiz);cursor:pointer;white-space:nowrap;border-bottom:2px solid transparent}
.tabs label:hover{color:var(--yazi)}
.tabs em{font-style:normal;background:var(--bar);border-radius:9px;padding:0 6px;margin-left:4px;color:var(--yazi)}.tabs em.k{background:var(--kotu);color:#fff}
.sekmeler section{display:none}
#t1:checked~.tabs label[for=t1],#t2:checked~.tabs label[for=t2],#t3:checked~.tabs label[for=t3],#t4:checked~.tabs label[for=t4],#t5:checked~.tabs label[for=t5],#t6:checked~.tabs label[for=t6],#t7:checked~.tabs label[for=t7],#t8:checked~.tabs label[for=t8],#t9:checked~.tabs label[for=t9]{color:var(--vurgu);border-bottom-color:var(--vurgu)}
#t1:focus-visible~.tabs label[for=t1],#t2:focus-visible~.tabs label[for=t2],#t3:focus-visible~.tabs label[for=t3],#t4:focus-visible~.tabs label[for=t4],#t5:focus-visible~.tabs label[for=t5],#t6:focus-visible~.tabs label[for=t6],#t7:focus-visible~.tabs label[for=t7],#t8:focus-visible~.tabs label[for=t8],#t9:focus-visible~.tabs label[for=t9]{outline:2px solid var(--vurgu);outline-offset:-2px}
#t1:checked~.sekmeler .n1,#t2:checked~.sekmeler .n2,#t3:checked~.sekmeler .n3,#t4:checked~.sekmeler .n4,#t5:checked~.sekmeler .n5,#t6:checked~.sekmeler .n6,#t7:checked~.sekmeler .n7,#t8:checked~.sekmeler .n8,#t9:checked~.sekmeler .n9{display:block}
details.kd{border-bottom:1px solid var(--bar);min-width:0}details.kd:last-child{border-bottom:0}
details.kd>summary{cursor:pointer;list-style:none;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 10px;align-items:start;padding:10px 12px}details.kd>summary::-webkit-details-marker{display:none}
details.kd>summary:hover{background:color-mix(in srgb,var(--vurgu) 6%,transparent)}
details.kd>summary [data-e]:before{content:attr(data-e);display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--sessiz)}
.ad{grid-column:1/-1}.ad:before{content:"▸";color:var(--sessiz);display:inline-block;width:14px}details.kd[open] .ad:before{content:"▾"}
.sh{display:none}.gb{padding:8px 12px 4px;font-size:11px;letter-spacing:.08em;color:var(--sessiz);border-bottom:1px solid var(--cizgi)}
details.kd .govde{padding:6px 12px 12px;background:var(--bg);border-top:1px solid var(--cizgi)}.govde .alt{margin-top:4px}.govde .sat>span{flex:0 0 auto;max-width:48%;overflow-wrap:normal}
details.ince>summary{cursor:pointer;color:var(--vurgu);font-size:11px;padding:6px 0}
.ayak{margin:14px 0 4px}
.ifr .ust{display:none}
.yap{display:flex;flex-wrap:wrap;align-items:baseline;gap:3px 12px;padding:8px 12px;margin:0 0 10px;border:1px solid var(--cizgi);border-left:4px solid var(--iyi);border-radius:12px;background:var(--kart)}
.yap.gerek{border-left-color:var(--kotu);background:color-mix(in srgb,var(--kotu) 10%,var(--kart))}.yap b{letter-spacing:.04em}.yap .gunc{margin-left:auto;color:var(--sessiz);font-size:11px}
details.uyari-kat{margin:0 0 8px}details.uyari-kat>summary{cursor:pointer;color:var(--vurgu);font-size:12px;padding:4px 2px}details.uyari-kat .uyari:last-child{margin-bottom:0}
.serit .rk .d{font-size:15px}.lst h4{margin:10px 0 4px;font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--sessiz)}
@media (min-width:900px){
body{padding:16px 20px}
.serit{grid-template-columns:repeat(6,minmax(0,1fr))}.serit .d{font-size:20px}
.ig{grid-template-columns:repeat(3,minmax(0,1fr))}.g2{grid-column:span 2}.g3{grid-column:1/-1}
.sag{display:grid;gap:8px;grid-column:3;grid-row:1 / span 2;align-content:start;min-width:0}.sag.s1{grid-row:auto}
.p.yuk{display:flex;flex-direction:column}.yuk>.pi{flex:1;display:flex;flex-direction:column}.yuk .gk{flex:1;grid-template-rows:minmax(0,1fr) auto}.yuk .gk svg{height:100%;min-height:210px;max-height:340px}
.gk svg{height:210px}.gk.kz svg{height:150px}.gk.dus svg{height:150px}
.stw{min-width:1020px}
.sh,details.kd>summary{display:grid;grid-template-columns:minmax(270px,2.6fr) minmax(70px,.9fr) minmax(110px,1.2fr) minmax(110px,1.3fr) minmax(48px,.55fr) minmax(64px,.75fr) minmax(48px,.55fr) minmax(72px,.8fr) minmax(190px,2.2fr) minmax(40px,.5fr);gap:10px;align-items:center;padding:9px 12px}
.sh{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--sessiz);border-bottom:1px solid var(--cizgi);background:color-mix(in srgb,var(--bg) 55%,var(--kart))}
details.kd>summary [data-e]:before{display:none}.ad{grid-column:auto}
.stw .sg{text-align:right}
.govde{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 32px}.govde .alt{grid-column:1/-1}
}

.nk{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:var(--sessiz);vertical-align:baseline}
.aj-scalp{background:#ff7a59}.aj-daytrade{background:#5b9dff}.aj-swing{background:#3ddc84}.aj-portfoy{background:#b084ff}
.fbar{display:none;flex-wrap:wrap;align-items:center;gap:6px 8px;padding:8px 0 2px}
html.js #t2:checked~.fbar,html.js #t3:checked~.fbar,html.js #t4:checked~.fbar{display:flex}
.fbar button.on,.fbar2 button.on{border-color:var(--vurgu);color:var(--vurgu);font-weight:700}
.fbar select,.fbar input[type=search],.fbar2 select{background:var(--kart);color:var(--yazi);border:1px solid var(--cizgi);border-radius:12px;padding:3px 6px;font:inherit;font-size:11px;min-width:0;max-width:100%}
.fbar input[type=search]{flex:1 1 130px}
.fbar .say{color:var(--sessiz);font-size:11px;margin-left:auto}
.fg,.gz{display:none!important}
.fbar2{display:none;gap:6px;flex-wrap:wrap;align-items:center;padding:8px 11px;border-bottom:1px solid var(--bar)}
html.js .fbar2{display:flex}
.daha{display:none;margin:8px 11px}html.js .daha.ac{display:inline-block}
.sirala th{cursor:pointer;user-select:none}.sirala th:hover{color:var(--vurgu)}
.sirala th[data-yon="1"]:after{content:" ▲"}.sirala th[data-yon="-1"]:after{content:" ▼"}
.ars{padding:5px 0}.ar{position:relative;height:12px;margin:5px 0 3px;background:var(--bar);border-radius:6px}
.ar i{position:absolute;top:0;height:100%;display:block}
.ar .a95{background:color-mix(in srgb,var(--vurgu) 28%,var(--bar));border-radius:6px}.ar .a50{background:color-mix(in srgb,var(--vurgu) 55%,var(--bar))}
.ar .p50{width:2px;background:var(--yazi);opacity:.7}
.ar .dg{width:10px;height:14px;top:-1px;margin-left:-5px;border-radius:12px;background:var(--vurgu);border:2px solid var(--kart)}
.ar .dg.iyi{background:var(--iyi)}.ar .dg.uyari{background:var(--uyari)}.ar .dg.kotu{background:var(--kotu)}
.ak{display:flex;justify-content:space-between;gap:6px;font-size:10px}
.ip{padding:8px 11px}
.kzb{display:grid;grid-template-columns:minmax(80px,32%) minmax(0,1fr) auto;gap:6px;align-items:center;padding:3px 0;font-size:12px}
.kzb .ad2{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kzb .ray{position:relative;height:12px;background:var(--bar);border-radius:2px}.kzb .ray:after{content:"";position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--sessiz)}
.kzb .ray i{position:absolute;top:0;height:100%}.kzb .ray i.p{background:var(--iyi)}.kzb .ray i.n{background:var(--kotu)}
.kzb b{font-variant-numeric:tabular-nums;white-space:nowrap}
.tkv{overflow-x:auto}.tkay{margin-bottom:10px}.tkay h4{margin:0 0 4px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--sessiz)}
.tkg{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px}
.tkg .bsl{font-size:9px;text-align:center;color:var(--sessiz);letter-spacing:.06em}
.tk,.tkb{min-height:46px;border:1px solid var(--cizgi);border-radius:12px;background:var(--bg);padding:2px 3px;text-align:left;display:flex;flex-direction:column;justify-content:space-between;gap:1px;color:var(--yazi);white-space:normal;min-width:0}
.tkb{border-style:dashed;opacity:.35}
.tk .gn{font-size:9px;color:var(--sessiz)}.tk .pn{font-size:10.5px;font-weight:700;font-variant-numeric:tabular-nums;overflow-wrap:normal;word-break:break-all}
.tk.sec{outline:2px solid var(--vurgu)}
.gd{display:none;margin-top:8px;border:1px solid var(--cizgi);border-radius:12px;background:var(--bg)}.gd.ac{display:block}
.gd h4{margin:0;padding:8px 11px;font-size:12px;border-bottom:1px solid var(--bar)}
.isi td,.isi th{text-align:right}.isi td:first-child,.isi th:first-child{text-align:left}.isi td.h{font-weight:700}
.bk{border-style:dashed}.bk code{color:var(--vurgu)}
.soz dt{color:var(--vurgu);font-weight:700;margin-top:8px}.soz dd{margin:2px 0 0;color:var(--sessiz)}
.yaz{display:inline-block}
@media (max-width:420px){.kzb{grid-template-columns:minmax(60px,34%) minmax(0,1fr) auto}.tk .pn{font-size:9px}.tk,.tkb{min-height:40px}}
.rdr{max-width:290px;margin:2px auto 6px}.rdr-h,.rdr-k{fill:none;stroke:var(--cizgi);stroke-width:1}
.rdr-s{fill:var(--vurgu);fill-opacity:.22;stroke:var(--vurgu);stroke-width:1.6}.rdr-n{fill:var(--vurgu)}
.rdr-t{fill:var(--yazi);font-size:9.5px}.rdr-t.yok{fill:var(--sessiz)}
.karneg{padding:10px 11px}.karne .kz2{padding:4px 0;border-bottom:1px solid var(--bar)}.karne .kz2k{padding:2px 0 4px}
.koc{padding:8px 11px;border-bottom:1px solid var(--bar);border-left:3px solid var(--cizgi)}.koc.kotu{border-left-color:var(--kotu)}.koc.uyari{border-left-color:var(--uyari)}
.koc>div{white-space:normal;margin:2px 0}
.cekmece{position:fixed;top:0;right:0;bottom:0;width:min(430px,100vw);overflow:auto;background:var(--kart);border-left:2px solid var(--vurgu);padding:12px 14px;z-index:20;box-shadow:-8px 0 24px rgba(0,0,0,.35)}
.cekmece[hidden]{display:none}.cekmece h4{margin:8px 0 2px;font-size:13px}.cekmece h5{margin:12px 0 4px;font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--vurgu)}
.gerekce{white-space:normal;padding:4px 0}.cek{padding:8px 11px;border-bottom:1px solid var(--bar)}.cek-liste{padding:0 11px}
tr[data-ix]{cursor:pointer}tr[data-ix].sec td{background:color-mix(in srgb,var(--vurgu) 14%,transparent)}
html.js .cek-liste{display:none}
.serit .d{font-size:14px}.serit .e{font-size:9px;letter-spacing:.05em}.serit-not{margin:-4px 0 10px}
.isik{padding:6px 0;font-weight:700}.yapm{font-weight:700;padding:2px 0}.yapm.gerek{color:var(--kotu)}
.lnk{color:var(--vurgu);cursor:pointer;font-size:11px;font-weight:600;white-space:nowrap}.bag{text-align:right;margin-top:4px}
.lh,.sr>summary{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1.1fr) minmax(0,1fr) minmax(0,.8fr);gap:6px;padding:8px 6px;align-items:start}
.lh{font-size:9px;letter-spacing:.07em;text-transform:uppercase;color:var(--sessiz);border-bottom:1px solid var(--cizgi);padding-top:2px}
.sr{border-bottom:1px solid var(--bar)}.sr>summary{cursor:pointer;list-style:none}.sr>summary::-webkit-details-marker{display:none}
.sr .c{min-width:0;display:block;font-variant-numeric:tabular-nums}.sr .c b{display:block}.sr .alt{display:block}
.sr .ayr{padding:4px 8px 10px;background:var(--bg)}.bos{padding:10px 0;color:var(--sessiz)}
.don{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}.don button.on{border-color:var(--vurgu);color:var(--vurgu);font-weight:700}
.kozet{display:flex;gap:4px 14px;flex-wrap:wrap;margin-bottom:6px}
details.tk{border-bottom:1px solid var(--bar)}details.tk>summary{cursor:pointer;padding:10px 11px;font-weight:700;list-style:none}details.tk>summary::-webkit-details-marker{display:none}
details.tk>summary:before{content:"▸ ";color:var(--sessiz)}details.tk[open]>summary:before{content:"▾ "}
.tkg2{padding:0 0 8px}.tkg2 .p{border:0;background:transparent}.tkg2 .pb{display:none}.tkg2 .pi{padding:4px 11px}
@media (max-width:600px){.tabs label{padding:9px 7px 8px;letter-spacing:.03em;font-size:10.5px}}
.fg,.gz{display:none!important}.daha{display:none;margin:8px 0}html.js .daha.ac{display:inline-block}
"""

JS = """
var K='1l3a-sekme';try{var s=localStorage.getItem(K),r=s&&/^t[1-6]$/.test(s)&&document.getElementById(s);if(r)r.checked=true}catch(e){}
Array.prototype.forEach.call(document.querySelectorAll('input[name=t]'),function(i){i.addEventListener('change',function(){try{localStorage.setItem(K,i.id)}catch(e){}})});
(function(){var k='1l3a-tema-v2',h=document.documentElement;try{localStorage.removeItem('1l3a-tema')}catch(e){}if(!/\bifr\b/.test(h.className)){try{var t=localStorage.getItem(k);if(t==='light'||t==='dark')h.setAttribute('data-theme',t)}catch(e){}}
var b=document.getElementById('tema');if(b)b.addEventListener('click',function(){var m=h.getAttribute('data-theme');var koyu=m?m==='dark':window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;var y=koyu?'light':'dark';h.setAttribute('data-theme',y);try{localStorage.setItem(k,y)}catch(e){}})})();
(function(){var b=document.getElementById('bayat');if(!b)return;var t=Date.parse(b.getAttribute('data-zaman')),e=Number(b.getAttribute('data-esik-dk'));
if(!isFinite(t)||!isFinite(e))return;var dk=Math.floor((Date.now()-t)/60000);if(dk>e){var x=document.getElementById('bayat-dk');if(x)x.textContent=String(dk);b.hidden=false}})();
(function(){var g=document.getElementById('gunc');if(!g)return;var t=Date.parse(g.getAttribute('data-uretim'));if(!isFinite(t))return;
function yaz(){var dk=Math.max(0,Math.floor((Date.now()-t)/60000));g.textContent='Son güncelleme '+(dk<1?'az önce':(dk<120?dk+' dk önce':Math.floor(dk/60)+' sa önce'))+'.'}
yaz();setInterval(yaz,30000)})();
(function(){var H=document.documentElement;H.className+=' js';var ADIM=20;
function para(v){var a=Math.abs(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}).replace(/,/g,'#').replace('.',',').replace(/#/g,'.');return (v<0?'\u2212':'+')+a+' $'}
Array.prototype.forEach.call(document.querySelectorAll('.lst'),function(k){
var sat=Array.prototype.slice.call(k.querySelectorAll('.sr')),lim=ADIM,f=null,ust=k.parentNode,dh=ust.querySelector('.daha'),bos=ust.querySelector('.bos');
k.ciz=function(){var n=0,w=0,net=0;sat.forEach(function(r){var ok=!f||f(r);r.classList.toggle('fg',!ok);r.classList.remove('gz');
if(ok){n++;var v=Number(r.getAttribute('data-net'));if(isFinite(v)){net+=v;if(v>0)w++}if(n>lim)r.classList.add('gz')}});
if(dh)dh.classList.toggle('ac',n>lim);if(bos)bos.hidden=n>0;return {n:n,w:w,net:net}};
k.sifirla=function(g){f=g;lim=ADIM;return k.ciz()};
if(dh)dh.addEventListener('click',function(){lim+=ADIM;k.ciz()});k.ciz()});
var kk=document.getElementById('kapanan'),dn=document.getElementById('don');
if(kk&&dn){Array.prototype.forEach.call(dn.querySelectorAll('button'),function(b){b.addEventListener('click',function(){
Array.prototype.forEach.call(dn.querySelectorAll('button'),function(x){x.classList.toggle('on',x===b)});
var d=b.getAttribute('data-don'),simdi=Date.now(),gun=new Date(simdi+3*3600000).toISOString().slice(0,10);
var f=d===''?null:(d==='gun'?function(r){return r.getAttribute('data-gun')===gun}:function(r){return Number(r.getAttribute('data-t'))*1000>=simdi-Number(d)*86400000});
var o=kk.sifirla(f),a=document.getElementById('k-n'),w=document.getElementById('k-w'),t=document.getElementById('k-net');
if(a)a.textContent=String(o.n);if(w)w.textContent='%'+(o.n?Math.floor(o.w*100/o.n):0);
if(t){t.textContent=para(o.net);t.className=o.net>0?'iyi':(o.net<0?'kotu':'')}})})}
var yb=document.getElementById('yenile');if(yb)yb.addEventListener('click',function(){location.reload()})})();
"""

BAYATLIK_ESIK_DK = 60                      # tarayıcı tarafı gösterim eşiği (iş hesabı değil: "sistem durmuş olabilir" uyarısı)
try:
    TSI = ZoneInfo("Europe/Istanbul")
except Exception:                          # noqa: BLE001 — tzdata yoksa: Türkiye 2016'dan beri kalıcı UTC+3
    TSI = timezone(timedelta(hours=3), "TSİ")


def tsi(s: Optional[str]) -> str:
    """Durum dosyasındaki UTC zaman metni -> Türkiye saati metni (yalnız saat dilimi dönüşümü). Gün metni ('2026-10-01') aynen döner."""
    if not s:
        return "—"
    try:
        return d.zaman_oku(s).astimezone(TSI).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return _gun_tr(str(s))


def _gun_tr(g) -> str:
    """'2026-01-05' -> '05.01.2026' (yalnız gösterim; data-* ve sıralama anahtarları makine biçiminde kalır)."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(g or ""))
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else str(g)


def _tsi_makine(s) -> str:
    """JS'in okuduğu TSİ gün/saat metni (YYYY-MM-DD HH:MM): data-* için; kullanıcıya gösterilmez."""
    try:
        return d.zaman_oku(s).astimezone(TSI).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(s)


def _h(metin, sinif: str = "") -> str:
    """Kaçışlı metin (isteğe bağlı renk sınıfı ile)."""
    return f'<span class="{sinif}">{esc(str(metin))}</span>' if sinif else esc(str(metin))


def _sat(ad: str, deger: str, sinif: str = "") -> str:
    return f'<div class="sat"><span>{esc(ad)}</span><b class="{sinif}">{esc(deger)}</b></div>'


def _isaret_sinifi(x) -> str:
    """Renk sınıfı: sayı ya da para metni (işaretine bakar; değer değişmez)."""
    if x is None:
        return ""
    try:
        v = Decimal(x) if isinstance(x, str) else x
    except Exception:  # noqa: BLE001
        return ""
    return "" if v == 0 else ("iyi" if v > 0 else "kotu")


def _guvenli(f):
    """Ek veri bölümü beklenmedik biçimde gelirse sayfa kırılmaz: o bölüm 'biçim uyumsuz' der, değer uydurulmaz."""
    def sar(*a, **k):
        try:
            return f(*a, **k)
        except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError, IndexError):
            return '<div class="kart alt">Bu bölümün verisi beklenen biçimde değil; gösterilemiyor.</div>'
    return sar


def _kutu(etiket: str, deger: str, sinif: str = "", alt="", oznitelik: str = "") -> str:
    """Rakam kutusu. `alt`: tek metin ya da satır listesi (boşlar atlanır)."""
    satirlar = [alt] if isinstance(alt, str) else list(alt)
    return (f'<div class="kart"{oznitelik}><div class="e">{esc(etiket)}</div><div class="d {sinif}">{esc(deger)}</div>'
            + "".join(f'<div class="alt">{esc(a)}</div>' for a in satirlar if a) + "</div>")


def _kullanim_cubugu(ad: str, deger: Optional[float], limit_metin: str, kullanim: Optional[float], deger_metin: str,
                     alt_metin: Optional[str] = None) -> str:
    gen = 0.0 if kullanim is None else max(0.0, min(1.0, kullanim)) * 100        # çizim ölçeği (kırpma yalnız genişlik için)
    sinif = "k" if kullanim is not None and kullanim >= 0.8 else ""
    kul = alt_metin if alt_metin is not None else ("ölçülmedi" if kullanim is None else f"kullanım {f_yuzde(kullanim, ondalik=1)}")
    return (f'<div class="kart"><div class="e">{esc(ad)}</div><div class="d">{esc(deger_metin)} <span class="alt">/ {esc(limit_metin)}</span></div>'
            f'<div class="cubuk {sinif}"><i style="width:{gen:.1f}%"></i></div><div class="alt">{esc(kul)}</div></div>')


def _kullanim_satiri(ad: str, limit_metin: str, kullanim: Optional[float], deger_metin: str, alt_metin: Optional[str] = None) -> str:
    """Panel içi kompakt kullanım satırı (kart değil): ad, değer / limit, çubuk, kullanım yüzdesi."""
    gen = 0.0 if kullanim is None else max(0.0, min(1.0, kullanim)) * 100
    sinif = "k" if kullanim is not None and kullanim >= 0.8 else ""
    kul = alt_metin if alt_metin is not None else ("ölçülmedi" if kullanim is None else f"kullanım {f_yuzde(kullanim, ondalik=1)}")
    return (f'<div class="mr"><div class="sat"><span>{esc(ad)} <span class="alt">· {esc(kul)}</span></span><b>{esc(deger_metin)} <span class="alt">/ {esc(limit_metin)}</span></b></div>'
            f'<div class="cubuk {sinif}"><i style="width:{gen:.1f}%"></i></div></div>')


SOZLUK = (("R", "Bir işlemin kazancı, ilk risk (giriş-stop mesafesi) kaç katı. +1R = riskin kadar kazandı, -1R = stop yedi."),
          ("PF (kâr faktörü)", "Toplam kâr / toplam zarar. 1'in üstü kârda, 2 ve üstü güçlü."),
          ("Kazanma oranı", "Kârla kapanan işlemlerin payı. Tek başına anlamsızdır; ortalama kâr/zarar ile birlikte okunur."),
          ("Katkı", "Stratejinin set özsermayesine eklediği (veya düşürdüğü) para; yüzdesi set başlangıcına oran."),
          ("Stil (ajan)", "scalp, day trade, swing ve portföy: stratejiler bu dört ajan altında toplanır."),
          ("Kol", "tek_grafik: strateji tek enstrümanda kendi başına; portfoy: birçok enstrümanı birlikte yöneten kol."),
          ("Beklenti konumu", "Backtest'in 4 ve 8 haftalık sonuç aralığına göre paper sonucunun yeri. %5-%95 arası normal; %5 altı kötü uç."),
          ("Beklenti alarmı", "8 haftalık net getiri alarm eşiğinin altına ya da düşüş eşiğinin üstüne düştü: strateji backtest gibi çalışmıyor olabilir."),
          ("Kill switch", "Zirveden düşüş sert limite ulaşırsa tüm işlemler durur. Mesafe: limite kalan pay."),
          ("Günlük kayıp limiti", "Bir günde kaybedilebilecek en çok pay. Dolarsa yeni işlem açılmaz."),
          ("Kaldıraç", "Brüt pozisyon tutarı / özsermaye. Sert tavan {kaldirac}."),
          ("Açık zarar-kes riski", "Tüm açık pozisyonlar stop'ta kapanırsa kaybedilecek toplam pay."),
          ("Brüt / net nominal", "Brüt: long ve short tutarlarının mutlak toplamı. Net: long eksi short."),
          ("Kayma", "Paper dolumları VARSAYILAN kayma ile hesaplanır (ölçüm değil): gerçekleşen dolum fiyatı ile beklenen fiyat arasındaki varsayılan fark x miktar."),
          ("Funding", "Vadesiz (perpetual) kripto sözleşmelerinde long/short taraflar arası periyodik ödeme."),
          ("Bayat veri", "Son mum beklenenden eski: veri akışı kopmuş olabilir. Hisse/emtia için kapalı piyasa süresi sayılmaz."),
          ("Backtest / Paper / Canlı", "Backtest: geçmiş veride simülasyon. Paper: canlı fiyatla sanal işlem (para yok). Canlı: gerçek hesap."))
SOZLUK_KISA = {"R": SOZLUK[0][1], "PF": SOZLUK[1][1], "Kazanma": SOZLUK[2][1], "Katkı": SOZLUK[3][1], "Stil": SOZLUK[4][1], "Kol": SOZLUK[5][1],
               "Beklenti konumu": SOZLUK[6][1], "Kayma": SOZLUK[13][1], "Varsayılan kayma": SOZLUK[13][1], "Katkı (açık dahil)": SOZLUK[3][1], "Grup": SOZLUK[4][1], "Funding": SOZLUK[14][1], "Set katkısı": SOZLUK[3][1]}


def _sk(x) -> str:
    """Tablo sıralama anahtarı (yalnız görüntü sırası): sayı ya da para metni -> sayı metni; yoksa boş."""
    if x is None:
        return ""
    try:
        return str(float(x))
    except (TypeError, ValueError):
        return ""


def _tablo(basliklar: list, satirlar: list, sag: tuple = (), sinif: str = "", sirala: bool = False, govde_id: str = "") -> str:
    """Kendi kutusunda yatay kayan tablo. Hücreler HAZIR (kaçışlı) HTML'dir; `sag`: sağa hizalı sütun numaraları.
    Satır: hücre listesi ya da (hücre listesi, öznitelik metni). Hücre: HTML metni ya da (HTML, sıralama anahtarı).
    `sirala`: başlığa tıklayınca tarayıcıda sıralanır (JS yoksa tablo olduğu gibi okunur)."""
    b = "".join(f'<th{" class=sg" if i in sag else ""}{(" title=" + chr(34) + esc(SOZLUK_KISA[x]) + chr(34)) if x in SOZLUK_KISA else ""}>{esc(x)}</th>'
                for i, x in enumerate(basliklar))
    r = []
    for s in satirlar:
        ozn = ""
        if isinstance(s, tuple):
            s, ozn = s
        td = ""
        for i, c in enumerate(s):
            v = ""
            if isinstance(c, tuple):
                c, k = c
                v = f' data-v="{esc(str(k))}"'
            td += f'<td{" class=sg" if i in sag else ""}{v}>{c}</td>'
        r.append(f"<tr{ozn}>{td}</tr>")
    t = (f'<div class="tw"><table{" class=sirala" if sirala else ""}><thead><tr>{b}</tr></thead>'
         f'<tbody{(" id=" + govde_id) if govde_id else ""}>{"".join(r)}</tbody></table></div>')
    return f'<div class="{sinif}">{t}</div>' if sinif else t


def _p(baslik: str, icerik: str, sag: str = "", sinif: str = "", duz: bool = False) -> str:
    """Panel: başlık şeridi (.pb) + içerik (.pi). `icerik` HAZIR HTML'dir; `sag`: başlığın sağındaki sönük not."""
    sag = re.sub(r"\s*·?\s*motor (?:yazar|hesaplar)\b", "", sag or "").strip(" ·")             # iç kaynak bilgisi kullanıcıya gösterilmez
    return (f'<div class="p{" " + sinif if sinif else ""}"><div class="pb">{esc(baslik)}' + (f"<span>{esc(sag)}</span>" if sag else "")
            + f'</div><div class="pi{" duz" if duz else ""}">{icerik}</div></div>')


def _ig(icerik: str) -> str:
    return f'<div class="ig">{icerik}</div>'


def _sag(icerik: str, sinif: str = "") -> str:
    return f'<div class="sag{" " + sinif if sinif else ""}">{icerik}</div>'


# ----------------------------------------------------------------------------------------------- grafikler (inline SVG; ölçekleme dışında hesap yok)
def _eksen(ust: str, alt: str, svg: str, x0: str, x1: str, sinif: str = "") -> str:
    """Grafik kutusu: solda y ekseni uç değerleri (dosyadaki değerler), altta ilk/son tarih."""
    return (f'<div class="gk {sinif}"><div class="yt"><span>{esc(ust)}</span><span>{esc(alt)}</span></div>{svg}'
            f'<span></span><div class="ek"><span>{esc(x0)}</span><span>{esc(x1)}</span></div></div>')


@_guvenli
def _egri(gecmis: dict, baz: Optional[str] = None) -> str:
    """Özsermaye eğrisi: alan grafiği + min/max etiketi + (varsa) başlangıç baz çizgisi. Yalnız çizim ölçeği."""
    n = gecmis["noktalar"]
    if len(n) < 2:
        return '<div class="alt">Özsermaye geçmişi için yeterli nokta yok.</div>'
    cift = [(float(x["ozsermaye"]), x["ozsermaye"]) for x in n]
    havuz = cift + ([(float(baz), baz)] if baz is not None else [])
    (hi, hi_s), (lo, lo_s) = max(havuz, key=lambda c: c[0]), min(havuz, key=lambda c: c[0])
    ar = (hi - lo) or 1.0
    y = lambda v: 76 - (v - lo) / ar * 72                                       # noqa: E731
    pts = " ".join(f"{i * 300 / (len(cift) - 1):.1f},{y(v):.1f}" for i, (v, _) in enumerate(cift))
    izgara = "".join(f'<line class="izg" x1="0" y1="{yy}" x2="300" y2="{yy}"/>' for yy in (4, 40, 76))
    baz_c = f'<line class="baz" x1="0" y1="{y(float(baz)):.1f}" x2="300" y2="{y(float(baz)):.1f}"/>' if baz is not None else ""
    svg = (f'<svg viewBox="0 0 300 80" preserveAspectRatio="none" role="img" aria-label="özsermaye eğrisi">{izgara}'
           f'<polygon class="alan" points="0,80 {pts} 300,80"/>{baz_c}<polyline class="cizgi" points="{pts}"/></svg>')
    return (_eksen(f_para(hi_s), f_para(lo_s), svg, _gun_tr(n[0]["gun"]), _gun_tr(n[-1]["gun"]))
            + f'<div class="alt grlej">ilk {esc(f_para(n[0]["ozsermaye"]))} · son {esc(f_para(n[-1]["ozsermaye"]))}'
            + (f' · kesikli çizgi: başlangıç {esc(f_para(baz))}' if baz is not None else "") + "</div>")


@_guvenli
def _dusus_grafigi(seri: list) -> str:
    """dusus_serisi [{gun, dusus}] -> aşağı sarkan alan grafiği (0 üstte; dosyadaki değerler aynen)."""
    if len(seri) < 2:
        return '<div class="alt">Zirveden düşüş serisi için yeterli nokta yok.</div>'
    ys = [float(x["dusus"]) for x in seri]
    tepe = max(ys) or 1.0                                                      # yalnız çizim ölçeği
    pts = " ".join(f"{i * 300 / (len(ys) - 1):.1f},{4 + v / tepe * 72:.1f}" for i, v in enumerate(ys))
    izgara = "".join(f'<line class="izg" x1="0" y1="{yy}" x2="300" y2="{yy}"/>' for yy in (40, 76))
    svg = (f'<svg viewBox="0 0 300 80" preserveAspectRatio="none" role="img" aria-label="zirveden düşüş">{izgara}'
           f'<polygon class="alan k" points="0,4 {pts} 300,4"/><polyline class="cizgi k" points="{pts}"/>'
           f'<line class="taban" x1="0" y1="4" x2="300" y2="4"/></svg>')
    return (_eksen(f_yuzde(0.0), f_yuzde(tepe), svg, _gun_tr(seri[0]["gun"]), _gun_tr(seri[-1]["gun"]), "dus")
            + f'<div class="alt grlej">ilk {esc(f_yuzde(seri[0]["dusus"]))} · son {esc(f_yuzde(seri[-1]["dusus"]))}</div>')


@_guvenli
def _kz_grafigi(seri: list) -> str:
    """gunluk_kz [{gun, pnl, getiri}] -> günlük K/Z çubukları (yeşil kâr / kırmızı zarar) + ayrıntı listesi (<details>)."""
    if not seri:
        return '<div class="alt">Günlük K/Z serisi boş.</div>'
    ys = [float(x["pnl"]) for x in seri]
    hi, lo = max(max(ys), 0.0), min(min(ys), 0.0)                              # yalnız çizim ölçeği (sıfır çizgisi dahil)
    ar = (hi - lo) or 1.0
    y = lambda v: 4 + (hi - v) / ar * 72                                       # noqa: E731
    gen = 300 / max(len(ys), 10)                                               # tek çubuk ekranı kaplamasın
    cubuklar = []
    for i, (x, v) in enumerate(zip(seri, ys)):
        ust, alt = y(max(v, 0.0)), y(min(v, 0.0))
        cubuklar.append(f'<rect class="{"bi" if v >= 0 else "bk"}" x="{i * gen + gen * 0.12:.2f}" y="{ust:.2f}" width="{gen * 0.76:.2f}" '
                        f'height="{max(alt - ust, 0.8):.2f}"><title>{esc(_gun_tr(x["gun"]))}: {esc(f_para(x["pnl"], True))}</title></rect>')
    en_ust = f_para(seri[ys.index(hi)]["pnl"], True) if hi > 0 else f_para("0")
    en_alt = f_para(seri[ys.index(lo)]["pnl"], True) if lo < 0 else f_para("0")
    svg = (f'<svg viewBox="0 0 300 80" preserveAspectRatio="none" role="img" aria-label="günlük K/Z">'
           f'<line class="izg" x1="0" y1="4" x2="300" y2="4"/><line class="izg" x1="0" y1="76" x2="300" y2="76"/>'
           f'<line class="taban" x1="0" y1="{y(0.0):.2f}" x2="300" y2="{y(0.0):.2f}"/>{"".join(cubuklar)}</svg>')
    satir = [[esc(_gun_tr(x["gun"])), _h(f_para(x["pnl"], True), _isaret_sinifi(x["pnl"])), _h(f_yuzde(x.get("getiri"), True), _isaret_sinifi(x.get("getiri")))]
             for x in reversed(seri)]
    return (_eksen(en_ust, en_alt, svg, _gun_tr(seri[0]["gun"]), _gun_tr(seri[-1]["gun"]), "kz")
            + f'<div class="sat"><span class="alt">son gün</span><b class="{_isaret_sinifi(seri[-1]["pnl"])}">{esc(f_para(seri[-1]["pnl"], True))}</b></div>'
            f'<details class="ince"><summary>Günlük değerler ({len(seri)} gün)</summary>{_tablo(["Gün", "K/Z", "Getiri"], satir, sag=(1, 2), sinif="kay")}</details>')


# ----------------------------------------------------------------------------------------------- süzgeç / ajan / enstrüman yardımcıları (yalnız gösterim)
AJAN_SIRA = ("scalp", "daytrade", "swing", "portfoy")
GRUP_SIRA = ("gunici", "swing", "yedek")                                          # kullanıcının kendi kategorileri (set kaydındaki "grup" + "yedek")
GRUP_ADI = {"gunici": "Gün içi", "swing": "Swing", "yedek": "Yedek"}
AY_ADI = ("", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
GUN_ADI = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")


def _nokta(ajan) -> str:
    """Stil (ajan) renk noktası; bilinmeyen ajan nötr renk."""
    ajan = {"gunici": "daytrade", "swing": "swing", "yedek": "portfoy"}.get(ajan, ajan)       # pano grupları mevcut renk sınıflarına eşlenir
    return f'<i class="nk aj-{ajan if ajan in AJAN_SIRA else "x"}" aria-hidden="true"></i>'


def _ajan_haritasi(st) -> dict:
    """kimlik -> ajan (stratejiler.json'daki alandan; arama tablosu)."""
    return {x["kimlik"]: (_grup(x) or x["ajan"]) for x in st["stratejiler"]} if st else {}


def _grup(x: dict) -> Optional[str]:
    """Pano grubu: yedek -> 'yedek'; yoksa motorun yazdığı 'grup' ('gunici'|'swing'). tf/stilden ÇIKARIM yok; alan yoksa grupsuz (süzgeç dışı)."""
    g = "yedek" if x.get("yedek") else x.get("grup")
    return g if g in GRUP_SIRA else None


def _kimlik_sembol(kimlik: str) -> str:
    p = kimlik.split("|")
    return p[1] if len(p) > 1 else ""


def _strateji_adi(kimlik: str) -> str:
    return kimlik.split("|")[0]


HENUZ_YOK = "Henüz veri yok"


def _bekleyen(alan: str = "", ne: str = "") -> str:
    """Motor bu alanı henüz yazmıyor: bölüm boş kalır, pano hesaplayıp doldurmaz. Dosya/alan adı kullanıcıya gösterilmez."""
    return f'<div class="kart alt bk" data-bos>{HENUZ_YOK}</div>'


@_guvenli
def _aralik(ad: str, n: dict, siddet: bool = True) -> str:
    """Beklenti aralığı konum şeridi: %5-%95 aralığı, %25-%75 kutusu, medyan çizgisi ve mevcut değer imi. Yalnız ölçekleme (dosyadaki p05..p95)."""
    if any(n.get(k) is None for k in ("deger", "p05", "p25", "p50", "p75", "p95")):
        return f'<div class="ars"><div class="sat"><span>{esc(ad)}</span><b>ölçülmedi</b></div></div>'
    lo, hi = min(n["p05"], n["deger"]), max(n["p95"], n["deger"])
    ar = (hi - lo) or 1.0
    k = lambda v: max(0.0, min(100.0, (v - lo) / ar * 100))                      # noqa: E731 — yalnız çizim konumu
    sev = BANT_SEVIYE[n["bant"]] if siddet else ""
    return (f'<div class="ars"><div class="sat"><span>{esc(ad)}</span><b class="nw">{esc(f_yuzde(n["deger"], True))} · {esc(BANT_ADI[n["bant"]])}</b></div>'
            f'<div class="ar" role="img" aria-label="{esc(ad)} aralık konumu"><i class="a95" style="left:{k(n["p05"]):.1f}%;width:{k(n["p95"]) - k(n["p05"]):.1f}%"></i>'
            f'<i class="a50" style="left:{k(n["p25"]):.1f}%;width:{k(n["p75"]) - k(n["p25"]):.1f}%"></i><i class="p50" style="left:{k(n["p50"]):.1f}%"></i>'
            f'<i class="dg {sev}" style="left:{k(n["deger"]):.1f}%"></i></div>'
            f'<div class="alt ak"><span>%5 {esc(f_yuzde(n["p05"], True))}</span><span>%50 {esc(f_yuzde(n["p50"], True))}</span><span>%95 {esc(f_yuzde(n["p95"], True))}</span></div></div>')


def _veri_yok(dosya: str = "") -> str:
    return f'<div class="kart alt" data-bos>{HENUZ_YOK}</div>'


def _ek_yok(dosya: str = "") -> str:
    return f'<div class="kart alt" data-bos>{HENUZ_YOK}</div>'


def _sirali(b: dict):
    return sorted(b.items(), key=lambda kv: int(kv[0]))


ETIKET_GOSTERIM = {"dogrulandi": ("doğrulandı", "iyi", "Resmi v2 holdout set kapısını geçti (gerekli, yeterli değil: asıl sınav paper)."),
                   "iyi_gorundu": ("iyi göründü", "uyari", "Sonuç sonrası keşif — KANIT DEĞİL (holdout sonucu görüldükten sonra seçildi)."),
                   "kapanis_aday": ("kapanış adayı", "uyari", "Kapanış turu paper adayı — ileri dönem sınavı gerekli, yeterli değil."),
                   "kapanis_aday_ek": ("kapanış adayı (ek)", "uyari", "Kapanış adayı — ileri dönem sınavından SONRA seçildi (sonuç sonrası seçim); 12 haftada canlı adayı olamaz, en fazla kapanis_aday'a yükselir.")}


def _etiket_cipi(etiket) -> str:
    """Paper v2 seti etiketi (stratejiler.json -> etiket); alan yoksa/boşsa hiçbir şey gösterilmez (eski motor)."""
    if not etiket:
        return ""
    ad, sinif, ipucu = ETIKET_GOSTERIM.get(etiket, (str(etiket), "uyari", ""))
    return f' <span class="cip {sinif}" title="{esc(ipucu)}">{esc(ad)}</span>'


BIRIKIYOR = "veri birikiyor"
NEDEN_ADI = {"ml_filtre": "ML filtresi", "sembol_islem_disi": "Sembol işlemden kalktı", "karantina": "Karantina", "risk": "Risk limiti", "kill": "Kill switch"}
ETIKET_AD = {"rejim_ml_4h": "Rejim (4 saat)", "rejim_ml_1d": "Rejim (1 gün)", "takvim_bayragi": "Takvim", "kalabalik": "Kalabalık",
             "korku_acgozluluk": "Korku / açgözlülük", "seans_dilimi": "Seans dilimi"}
ALT_AD = {"basabas_1R": "1R'de başabaş", "atr_iz_2": "2 ATR mesafeli iz-süren zarar-kes", "atr_iz_3": "3 ATR mesafeli iz-süren zarar-kes", "zaman_stopu_10": "10 mumda zaman çıkışı",
          "kismi_2R_yarim": "2R'de yarı kâr al", "brooks": "Brooks yöntemi", "farley": "Kâr koruyan iz-süren zarar-kes",
          "zirveden_geri_cekilme": "Zirveden geri çekilme"}


def _json_oku(dizin, ad: str):
    try:
        return json.loads((Path(dizin) / ad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _neden_adi(k: str) -> str:
    """Alınmayan sinyal nedeni -> sade Türkçe (teknik kod yok)."""
    k = str(k)
    if k in NEDEN_ADI:
        return NEDEN_ADI[k]
    if k.startswith("ders:"):
        return "Öğrenilen ders"
    if k.startswith("etiket:"):
        return "Etiket kuralı"
    return "Diğer"


def _r_txt(x) -> str:
    return "—" if x is None else f"{_tr(float(x), 2, True)} R"


def _kart(baslik: str, aciklama: str, govde: str, sag: str = "") -> str:
    return _p(baslik, govde, sag)                                                   # açıklama paragrafı gösterilmez (kalabalık)


def _birikiyor(baslik: str, aciklama: str = "") -> str:
    return _p(baslik, f'<div class="kart alt" data-bos>{BIRIKIYOR}</div>')


def _ogrenme_karti(kr: Optional[dict], simdi: datetime) -> str:
    from motor.canli import kurulum_ozeti as ko
    og = (kr or {}).get("ana_ogrenme")
    if not kr or not og or not og["veri_var"]:
        return _birikiyor("Öğrenme", "Yapay öğrenme filtresi ve öğrenilen dersler.")
    gizli = kr["gizli_kurulum"]
    karne = (og.get("karne") or {}).get("karne") or {}
    drift_uyari = set((og.get("durum") or {}).get("drift_uyari") or [])
    d = ko.dersler(og, gizli, simdi)
    alyn = [(k, v) for k, v in karne.items() if k not in gizli]
    uyar = sorted(_kurulum_adi(k, og, gizli) for k in drift_uyari if k not in gizli)
    ust = [_sat("ML filtresi aktif kurulum", str(len([k for k, _ in alyn if k in og["filtre"]]))), _sat("Aktif ders", str(len(d["aktif"]))),
           _sat("Son 7 gün emekli ders", str(len(d["emekli"]))), _sat("Atlanan giriş", str(og["alinmayan_toplam"])),
           _sat("Sapma uyarısı", ", ".join(uyar) if uyar else "yok", "kotu" if uyar else "")]
    gizli_n = len(karne) - len(alyn)
    if gizli_n or d["gizli_adet"]:
        ust.append(_sat("Diğer hesaplar", f"{gizli_n} kurulum, {d['gizli_adet']} ders"))
    satir = "".join(_sat(_kurulum_adi(k, og, gizli), f"alınan {v.get('alinan', '—')}/{v.get('aday', '—')} · {_r_txt(v.get('ort_r_alinan'))} · filtre {'açık' if k in og['filtre'] else 'kapalı'}")
                    for k, v in alyn[:8])
    return _kart("Öğrenme", "Yapay öğrenme hangi girişleri eledi ve kaç ders öğrendi; kurulum başına alınan/aday ve ortalama R.",
                 "".join(ust) + (f'<div class="bol">{satir}</div>' if satir else ""))


def _etiketle(adlar: list) -> list:
    """Aynı görünen ad birden çok kez geçerse (1), (2) ekler; yalnız sayma."""
    gor, out = {}, []
    for a in adlar:
        gor[a] = gor.get(a, 0) + 1
        out.append(a if adlar.count(a) == 1 else f"{a} ({gor[a]})")
    return out


def _alinmayan_karti(kr: Optional[dict], a: Optional[dict]) -> str:
    aciklama = "Atlanan sinyaller alınsaydı kaç R kazandırır ya da kaybettirirdi (maliyetsiz, yalnız bilgi)."
    if isinstance(a, dict) and isinstance(a.get("nedenler"), list) and a["nedenler"]:
        ust = [_sat("Atlanan sinyal", str(a.get("atlanan", "—"))), _sat("Sonucu belli olan", str(a.get("cozulen", "—"))),
               _sat("Alınsaydı toplam", _r_txt(a.get("toplam_r")), _isaret_sinifi(a.get("toplam_r"))),
               _sat("Alınsaydı ortalama", _r_txt(a.get("ort_r")), _isaret_sinifi(a.get("ort_r")))]
        nedenler = sorted(a["nedenler"], key=lambda o: -int(o.get("sinyal") or 0))[:8]
        adlar = _etiketle([_neden_adi(o["neden"]) for o in nedenler])
        satir = "".join(_sat(ad, f"{o.get('sinyal', 0)} sinyal · {_r_txt(o.get('toplam_r'))}", _isaret_sinifi(o.get("toplam_r"))) for ad, o in zip(adlar, nedenler))
        return _kart("Alınmayan sinyaller", aciklama, "".join(ust) + f'<div class="bol">{satir}</div>', f"son {a.get('pencere_gun', '—')} gün")
    og = (kr or {}).get("ana_ogrenme") or {}
    if og.get("alinmayan"):                                           # sonuç dosyası yok ama sayım var: R birikiyor
        sirali = sorted(og["alinmayan"].items(), key=lambda kv: -kv[1])[:8]
        adlar = _etiketle([_neden_adi(k) for k, _ in sirali])
        satir = "".join(_sat(ad, f"{n} sinyal · R: {BIRIKIYOR}") for ad, (_, n) in zip(adlar, sirali))
        return _kart("Alınmayan sinyaller", aciklama, _sat("Atlanan sinyal", str(og["alinmayan_toplam"])) + f'<div class="bol">{satir}</div>')
    return _birikiyor("Alınmayan sinyaller", aciklama)


def _etiket_karti(e: Optional[dict]) -> str:
    aciklama = "Kapanan işlemler giriş anındaki etikete göre: kaç işlem, isabet oranı, toplam sonuç."
    if not e or not isinstance(e.get("etiketler"), dict):
        return _birikiyor("Etiket × sonuç", aciklama)
    birim = e.get("birim") or "R"
    parcalar = []
    for ad, satirlar in e["etiketler"].items():
        if not satirlar:
            continue
        rows = "".join(_sat(str(x["deger"]), f"{x['islem']} işlem · %{f_sayi(x['isabet_yuzde'], 0)} · {_tr(float(x['toplam']), 2, True)}", _isaret_sinifi(x["toplam"])) for x in satirlar[:6])
        parcalar.append(f'<div class="alt bol">{esc(ETIKET_AD.get(ad, "Etiket"))}</div>{rows}')
    if not parcalar:
        return _birikiyor("Etiket × sonuç", aciklama)
    return _kart("Etiket × sonuç", aciklama + f" Birim: {birim}.", "".join(parcalar),
                 f"{e.get('islem_sayisi', 0)} işlem · ölçülemeyen {e.get('olculemeyen', 0)}")


def _cikis_karti(c: Optional[dict], kr: Optional[dict]) -> str:
    aciklama = "Aynı işlemlerde başka çıkış yöntemi denenseydi sonuç ne olurdu; uygulananlar ve geri alınanlar. Kâr koruyan iz-süren zarar-kes: kâr hedefe yaklaşınca zarar-kes daraltılır."
    ko_ = (c or {}).get("karsi_olgu")
    if not isinstance(ko_, dict) or not isinstance(ko_.get("stratejiler"), dict) or not ko_["stratejiler"]:
        return _birikiyor("Çıkış kanıtı", aciklama)
    ov = c.get("override") if isinstance(c.get("override"), dict) else {}
    yasak = c.get("yasak") if isinstance(c.get("yasak"), list) else []
    gizli = _gizli_adlar()
    gor = [(sk, v) for sk, v in ko_["stratejiler"].items() if sk.split("|")[0] not in gizli]
    gizli_n = len(ko_["stratejiler"]) - len(gor)
    gecen = [sk for sk, v in gor if any(o.get("olcut_gecti") for ad, o in (v.get("alternatifler") or {}).items() if not ad.startswith("_"))]
    ust = [_sat("Denenen strateji", str(len(ko_["stratejiler"]))), _sat("Ölçütü geçen strateji", str(len(gecen)), "iyi" if gecen else ""),
           _sat("Uygulanan değişiklik", str(len(ov)), "iyi" if ov else ""), _sat("Geri alınan", str(len(yasak)), "uyari" if yasak else "")]
    satir = []
    for sk, v in gor[:8]:
        alt = {ad: o for ad, o in (v.get("alternatifler") or {}).items() if not ad.startswith("_") and o.get("fark_r") is not None}
        parca = [f"{v.get('islem', 0)} işlem"]
        if "farley" in alt:
            parca.append(f"{ALT_AD['farley']} {_tr(float(alt['farley']['fark_r']), 1, True)} R")
        if alt:
            en = max(alt, key=lambda a: float(alt[a]["fark_r"]))
            parca.append(f"en iyi {ALT_AD.get(en, 'Diğer')} {_tr(float(alt[en]['fark_r']), 1, True)} R")
        if (v.get("geri_alma") or {}).get("gerekli"):
            parca.append("geri alma gerekli")
        if alt:
            parca.append(f"son {ko_.get('pencere_gun', 90)} gün")
        satir.append(_sat(_ad_goster(sk), " · ".join(parca)))
    ek = f'<div class="bol">{"".join(satir)}</div>' if satir else ""
    if gizli_n:
        ek += f'<div class="alt">Diğer hesaplar ({gizli_n}) ayrıca incelendi.</div>'
    uyg = sorted(ALT_AD.get((x or {}).get("alternatif"), "Diğer") for x in ov.values())
    if uyg:
        ek += f'<div class="alt bol">Uygulananlar: {esc(", ".join(uyg))}</div>'
    return _kart("Çıkış kanıtı", aciklama, "".join(ust) + ek, f"son {ko_.get('pencere_gun', '—')} gün")


def _bosluk_karti(o: Optional[dict]) -> str:
    aciklama = "Hisse/emtia pozisyonları piyasa kapanışında %20 boşlukla ters giderse kasanın kaç yüzdesi kaybedilir; eşik aşılırsa kırmızı."
    if not o or not isinstance(o.get("hesaplar"), list):
        return _birikiyor("Boşluk riski", aciklama)
    esik = o.get("esik_yuzde")

    def y(x):
        return "—" if x is None else "%" + _tr(float(x) * 100, 1)
    satir = "".join(_sat(str(r["ad"]).replace("gizli_hesaplar", DIGER_TOPLU), f"{f_para(str(round(r['hisse_emtia_nominal'], 2)))} · olası kayıp {y(r.get('kayip_yuzde'))} · en kötü {y(r.get('tarihsel_yuzde'))}",
                         "kotu" if r.get("ihlal") else "") for r in o["hesaplar"])
    kr = o.get("kripto") or {}
    alt = f'Kripto {f_para(str(round(kr.get("nominal", 0), 2)))} açık, 7/24 işlem olduğundan boşluk sayılmadı.'
    return _kart("Boşluk riski", aciklama + f" Eşik: {y(esik)}. " + alt, _sat("Eşik (kasa oranı)", y(esik)) + satir)


def _karantina_karti(sg: Optional[dict]) -> str:
    aciklama = "Kod hatası verip yeni giriş açması durdurulan stratejiler; açık pozisyonları zarar-kes/hedefle sürer."
    kq = (sg or {}).get("karantina")
    if not isinstance(kq, dict):
        return _birikiyor("Karantina", aciklama)
    gor = [_ad_goster(k) for k in (kq.get("gorunur") or [])]
    gz = int(kq.get("gizli") or 0)
    n = len(gor) + gz
    satir = "".join(_sat(k, "karantinada", "uyari") for k in gor[:6]) + (_sat("Diğer hesaplar", f"{gz} strateji", "uyari") if gz else "")
    return _kart("Karantina", aciklama, _sat("Karantinadaki strateji", str(n), "kotu" if n else "iyi") + satir)


def _disk_karti(dk: Optional[dict]) -> str:
    aciklama = "Sunucu diski ne kadar dolu; kayıt dosyaları günde bir arşivlenir, doluluk yükselirse Telegram'a uyarı gider."
    if not isinstance(dk, dict) or not (dk.get("olcum") or dk.get("durum")):
        return _birikiyor("Disk", aciklama)
    olc_ = dk.get("olcum") or {}
    g = []
    if olc_:
        pct = max(olc_.values())
        g.append(_sat("Doluluk (en yüksek)", f"%{_tr(pct, 0)}", "kotu" if pct >= 90 else ("uyari" if pct >= 80 else "iyi")))
    durum = dk.get("durum") or {}
    g.append(_sat("Alarm", "AÇIK" if durum.get("alarm") else "yok", "kotu" if durum.get("alarm") else "iyi"))
    sd = durum.get("son_dondurme")
    if sd is not None:
        try:
            g.append(_sat("Son arşivleme (TSİ)", datetime.fromtimestamp(float(sd), tz=timezone.utc).astimezone(TSI).strftime("%Y-%m-%d %H:%M")))
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    return _kart("Disk", aciklama, "".join(g))


def _sembol_karti(ol: Optional[list]) -> str:
    aciklama = "Borsada işlemden kalkan semboller: yeni giriş açılmaz, açık pozisyon varsa zarar-kes/hedefle sürer."
    if ol is None:
        return _birikiyor("Sembol durumu", aciklama)
    son: dict = {}
    for o in sorted(ol, key=lambda o: o.get("zaman") or ""):
        if o.get("tur") in ("sembol_islem_disi", "sembol_yeniden_acildi"):
            parca = str(o.get("mesaj") or "").split()
            if parca:
                son[parca[0]] = (o["tur"], o.get("zaman"), "açık pozisyon var" in str(o.get("mesaj")))
    kapali = {s: v for s, v in son.items() if v[0] == "sembol_islem_disi"}
    if not son:
        return _kart("Sembol durumu", aciklama, _sat("İşleme kapanan sembol", "0", "iyi") + _sat("Durum", "tüm semboller işlemde", "iyi"))
    acik = len([v for v in kapali.values() if v[2]])
    g = [_sat("İşleme kapanan sembol", str(len(kapali)), "kotu" if kapali else "iyi"), _sat("Açık pozisyonu olan", str(acik), "kotu" if acik else ""),
         _sat("Yeniden işleme açılan", str(len(son) - len(kapali)))]
    g += [_sat(s, f"{tsi(v[1])}", "kotu") for s, v in sorted(kapali.items())[:6]]
    return _kart("Sembol durumu", aciklama, "".join(g))


@_guvenli
def _risk_payi(oz: dict) -> str:
    r = oz["risk"]
    gk, kl, ks, ar = r["gunluk_kayip"], r["kaldirac"], r["kill_switch"], r["acik_stop_riski"]
    return (_kullanim_satiri("Günlük kayıp", f_yuzde(gk["limit"], ondalik=0), gk["kullanim"], f_yuzde(gk["deger"]))
            + _kullanim_satiri("Kaldıraç", f_sayi(kl["limit"], 1) + "x", kl["kullanim"], f_sayi(kl["deger"]) + ("x" if kl["deger"] is not None else ""))
            + _kullanim_satiri("Açık zarar-kes riski", f_yuzde(ar["limit"], ondalik=0), ar["kullanim"], f_yuzde(ar["deger"]))
            + _kullanim_satiri("Kill switch (zirveden düşüş)", f_yuzde(ks["limit"], ondalik=0), None, f_yuzde(ks["dusus"]),
                               alt_metin=f"mesafe {f_yuzde(ks['mesafe'])}" + (" — TETİKLENDİ" if ks["tetiklendi"] else "")))


@_guvenli
def _saglik_ozet(sg: dict) -> str:
    sv = sg["servis"]
    g = [_sat("Durum", sg["durum"], "iyi" if sg["durum"] == "ok" else "kotu"), _sat("Son çalışma (TSİ)", tsi(sg["son_calisma"])),
         _sat("Servis", {True: "çalışıyor", False: "ÇALIŞMIYOR", None: "yok (backtest)"}[sv["calisiyor"]], "kotu" if sv["calisiyor"] is False else "")]
    for v in sg["veri"][:4]:
        g.append(_sat(f"{v['sembol']} {v['tf']}", f"{v['bayatlik_dk']} dk" + (" · BAYAT" if v["bayat"] else ""), "kotu" if v["bayat"] else ""))
    if len(sg["veri"]) > 4:
        g.append(f'<div class="alt">+{len(sg["veri"]) - 4} veri akışı daha: SAĞLIK sekmesi</div>')
    return "".join(g)


@_guvenli
def _beklenti_tablosu(st: dict) -> str:
    satir = []
    for hf, b in _sirali(st["set"]["beklenti"]):
        n, m = b["net_getiri"], b["max_dusus"]
        satir.append([esc(f"{hf} hf"), _h(f_yuzde(n["deger"], True), _isaret_sinifi(n["deger"])), f'<span class="cip {BANT_SEVIYE[n["bant"]]}">{esc(BANT_ADI[n["bant"]])}</span>',
                      esc(f_yuzde(n["p05"], True)), esc(f_yuzde(n["p50"], True)), esc(f_yuzde(n["p95"], True)),
                      esc(f_yuzde(m["deger"])), esc(f_yuzde(m["p95"]))])
    if not satir:
        return '<div class="alt" style="padding:10px 11px">Referans yok: bu set için beklenti aralığı tanımlı değil.</div>'
    seritler = "".join(_aralik(f"{hf} hf net getiri", b["net_getiri"]) for hf, b in _sirali(st["set"]["beklenti"]))
    return (_tablo(["Pencere", "Net getiri", "Konum", "Net %5", "Net %50", "Net %95", "Düşüş", "Alarm üstü (%95)"], satir, sag=(1, 3, 4, 5, 6, 7))
            + (f'<div class="ip">{seritler}</div>' if seritler else ""))


@_guvenli
def _takvim(kz: list, isl: Optional[list], amap: Optional[dict] = None, gun_kesimi: Optional[str] = None) -> str:
    """Aylık takvim ısı haritası: her gün ozet.json -> gunluk_kz[].pnl (renk yoğunluğu yalnız ölçek). Güne dokununca o gün kapanan işlemler
    (islemler.jsonl'den, motorun yazdığı `gun` alanıyla süzme) açılır; hafta/ay toplamı pano tarafından hesaplanmaz. `gun` alanı olmayan satır
    hiçbir güne YERLEŞTİRİLMEZ (UTC tarihine düşürmek TSİ günüyle çelişirdi); sayısı açıkça yazılır."""
    if not kz:
        return '<div class="alt">Günlük K/Z serisi boş.</div>'
    amap = amap or {}
    gun_adi = "TSİ günü" if gun_kesimi == "Europe/Istanbul" else "UTC günü"          # motorun yazdığı gün kesimi (ozet.gun_kesimi)
    gun = {x["gun"]: x for x in kz}
    enb = max(abs(float(x["pnl"])) for x in kz) or 1.0
    aylar = sorted({x["gun"][:7] for x in kz})
    cikti = []
    for ay in aylar:
        y, m = int(ay[:4]), int(ay[5:7])
        hucre = "".join(f'<div class="bsl">{g}</div>' for g in GUN_ADI)
        for hafta in calendar.Calendar(0).monthdayscalendar(y, m):
            for dn in hafta:
                if dn == 0:
                    hucre += '<div></div>'
                    continue
                g = f"{ay}-{dn:02d}"
                x = gun.get(g)
                if not x:
                    hucre += f'<div class="tkb"><span class="gn">{dn}</span></div>'
                    continue
                v = float(x["pnl"])
                yog = 14 + abs(v) / enb * 56                                           # yalnız renk yoğunluğu
                ren = "var(--iyi)" if v > 0 else ("var(--kotu)" if v < 0 else "var(--sessiz)")
                hucre += (f'<button type="button" class="tk" data-gun="{esc(g)}" style="background:color-mix(in srgb,{ren} {yog:.0f}%,var(--bg))" '
                          f'title="{esc(_gun_tr(g))}: {esc(f_para(x["pnl"], True))} ({esc(f_yuzde(x.get("getiri"), True))})">'
                          f'<span class="gn">{dn}</span><span class="pn">{esc(f_para(x["pnl"], True))}</span></button>')
        cikti.append(f'<div class="tkay"><h4>{AY_ADI[m]} {y}</h4><div class="tkg">{hucre}</div></div>')
    detay = []
    gunsuz = len([i for i in (isl or []) if not i.get("gun")])                       # takvime yerleştirilemeyen satırlar (yalnız gösterim)
    for x in kz:
        g = x["gun"]
        liste = [i for i in (isl or []) if i.get("gun") == g]                         # i["gun"]: motorun yazdığı gün (yoksa yerleştirilmez)
        if isl is None:
            ic = f'<div class="alt ip">{HENUZ_YOK}</div>'
        elif not liste:
            ic = '<div class="alt ip">Bu gün kapanan işlem yok.</div>'
        else:
            ic = _tablo(["Zaman (TSİ)", "Sembol", "Yön", "R", "Net (kapanan)", "Strateji", "Çıkış"],
                        [[esc(tsi(i["zaman"])), esc(i["sembol"]), _h(i["yon"], "iyi" if i["yon"] == "long" else "kotu"), esc(f_sayi(i["r"])),
                          _h(f_para(i["net_pnl_yerel"], True), _isaret_sinifi(i["net_pnl_yerel"])), f'{_nokta(amap.get(i["kimlik"]))}{esc(kisa_kimlik(i["kimlik"]))}',
                          esc(i["cikis_nedeni"])] for i in sorted(liste, key=lambda i: i["zaman"])], sag=(3, 4))
        detay.append(f'<div class="gd" data-gun="{esc(g)}"><h4>{esc(_gun_tr(g))} ({gun_adi}) · K/Z {esc(f_para(x["pnl"], True))} ({esc(f_yuzde(x.get("getiri"), True))})</h4>{ic}</div>')
    return ('<div class="tkv">' + "".join(cikti) + '</div><div class="alt">Renk yoğunluğu o günün K/Z büyüklüğüne göre; bir güne dokun/tıkla: o gün kapanan işlemler.</div>'
            + (f'<div class="uyari takvim-gunsuz">{gunsuz} işlemin günü bilinmiyor: takvime yerleştirilmedi.</div>'
               if gunsuz else "")
            + "".join(detay))


@_guvenli
def _donemsel(oz: dict) -> str:
    """ozet.json -> gunluk_kz_ajan[] {gun, ajanlar{ajan:{pnl,getiri}}} (motor yazar): gün x stil getiri matrisi. Yoksa 'veri yok'."""
    m = oz.get("gunluk_kz_ajan")
    if m is None:
        return _bekleyen("ozet.json → gunluk_kz_ajan[]", "son günler için stil (ajan) başına günlük K/Z ve getiri")
    if not m:
        return '<div class="alt ip">Stil bazlı günlük K/Z serisi boş.</div>'
    sira = GRUP_SIRA + AJAN_SIRA
    ajanlar = [a for a in sira if any(a in x["ajanlar"] for x in m)] + sorted({a for x in m for a in x["ajanlar"]} - set(sira))
    enb = max([abs(float(v["getiri"])) for x in m for v in x["ajanlar"].values() if v.get("getiri") is not None] or [0.0]) or 1.0
    satir = []
    for x in sorted(m, key=lambda x: x["gun"], reverse=True):
        h = [f'<b>{esc(_gun_tr(x["gun"]))}</b>']
        for a in ajanlar:
            v = x["ajanlar"].get(a)
            if not v or v.get("getiri") is None:
                h.append("—")
                continue
            g = float(v["getiri"])
            yog = 10 + abs(g) / enb * 55                                               # yalnız renk yoğunluğu
            ren = "var(--iyi)" if g > 0 else ("var(--kotu)" if g < 0 else "var(--sessiz)")
            h.append(f'<span class="h" style="display:block;padding:2px 6px;border-radius:12px;background:color-mix(in srgb,{ren} {yog:.0f}%,transparent)" '
                     f'title="{esc(f_para(v.get("pnl"), True))}">{esc(f_yuzde(v["getiri"], True))}</span>')
        satir.append(h)
    return _tablo(["Gün"] + [GRUP_ADI.get(a, a) for a in ajanlar], satir, sag=tuple(range(1, len(ajanlar) + 1)), sinif="kay") + '<div class="alt ip">Hücre: günlük getiri (set başlangıcına oran); K/Z tutarı için hücreye bekle.</div>'


# ----------------------------------------------------------------------------------------------- koni / kıyas / korelasyon / yoğunlaşma (motor yazar; pano yalnız çizer)
def _noktalar(ciftler: list) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in ciftler)


def _parcalar(noktalar: list) -> list:
    """[(x, y|None)] -> kesintisiz parçalar (None noktada çizgi bölünür)."""
    out, cur = [], []
    for x, y in noktalar:
        if y is None:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append((x, y))
    if cur:
        out.append(cur)
    return out


KIYAS_SINIF = {"paper": "cizgi", "btc": "cizgi kc1", "spx": "cizgi kc2", "mevduat": "cizgi kc3"}


@_guvenli
def _kiyas_html(ky: dict) -> str:
    """kiyas.json (motor yazar): paper getirisi ↔ BTC / S&P 500 al-tut / mevduat (aynı tabana normalize birikimli getiri)."""
    gunler, seriler = ky["gunler"], ky["seriler"]
    if len(gunler) < 2:
        return '<div class="kart alt">Kıyas için yeterli gün yok.</div>'
    cizilen = [s for s in seriler if s["noktalar"] and any(x["getiri"] is not None for x in s["noktalar"])]
    degerler = [x["getiri"] for s in cizilen for x in s["noktalar"] if x["getiri"] is not None]
    hi, lo = max(degerler + [0.0]), min(degerler + [0.0])
    ar = (hi - lo) or 1.0
    Y = lambda v: 76 - (v - lo) / ar * 72                                       # noqa: E731
    cizgiler = []
    for s in cizilen:
        pts = [(i * 300 / (len(gunler) - 1), None if x["getiri"] is None else Y(x["getiri"])) for i, x in enumerate(s["noktalar"])]
        for pr in _parcalar(pts):
            cizgiler.append(f'<polyline class="{KIYAS_SINIF.get(s["kimlik"], "cizgi")}" points="{_noktalar(pr)}"/>' if len(pr) > 1
                            else f'<circle class="kn-nk {KIYAS_SINIF.get(s["kimlik"], "")}" cx="{pr[0][0]:.1f}" cy="{pr[0][1]:.1f}" r="2"/>')
    izg = "".join(f'<line class="izg" x1="0" y1="{yy}" x2="300" y2="{yy}"/>' for yy in (4, 40, 76))
    svg = (f'<svg viewBox="0 0 300 80" preserveAspectRatio="none" role="img" aria-label="paper ve kıyas serileri">{izg}'
           f'<line class="taban" x1="0" y1="{Y(0.0):.1f}" x2="300" y2="{Y(0.0):.1f}"/>{"".join(cizgiler)}</svg>')
    leg = '<div class="alt grlej">' + " &nbsp; ".join(f'<i class="lg-i lg-{esc(s["kimlik"])}"></i>{esc(s["etiket"])}' for s in cizilen) + "</div>"
    satir = []
    for s in seriler:
        durum = ('<span class="cip uyari">kullanıcı oranı girmeli</span> ' if s.get("kullanici_girmeli") else "")
        satir.append([f'<i class="lg-i lg-{esc(s["kimlik"])}"></i>{esc(s["etiket"])}', (esc(f_yuzde(s["son_getiri"], True)), _sk(s["son_getiri"])),
                      durum + esc(s["neden"] or s.get("kaynak") or "")])
    return (_eksen(f_yuzde(hi, True), f_yuzde(lo, True), svg, ky["gunler"][0], ky["gunler"][-1]) + leg
            + _tablo(["Seri", "Son getiri", "Not"], satir, sag=(1,))
            + f'<div class="alt">{esc(ky["taban_notu"])}</div>')


@_guvenli
def _korelasyon_html(kr: dict) -> str:
    """korelasyon.json (motor yazar): stratejiler arası günlük getiri korelasyon matrisi. Renk yoğunluğu |r| ölçeğidir; eşik/alarm yok."""
    if kr.get("matris") is None:
        return f'<div class="kart alt">Korelasyon yok: {esc(kr.get("neden") or "neden yazılmamış")}</div>'
    ks, m, ortak, ga = kr["kimlikler"], kr["matris"], kr["ortak_gun"], kr["guven_araligi"]
    bas = [""] + [f"{i + 1}" for i in range(len(ks))]
    satir = []
    for i, a in enumerate(ks):
        hucre = [f"<b>{i + 1}</b> {esc(_strateji_adi(a))} <span class=\"alt\">{esc(_kimlik_sembol(a))}</span>"]
        for j in range(len(ks)):
            r = m[i][j]
            if r is None:
                hucre.append('<span class="alt" title="hesaplanamadı (hucre_neden)">—</span>')
            else:
                ai = ga[i][j]
                ipucu = f"{ortak[i][j]} ortak gün" + (f"; %95 aralık {_tr(ai[0])} … {_tr(ai[1])}" if ai else "")
                ton = "--bilgi" if r < 0 else "--vurgu"
                hucre.append((f'<span class="kor" style="background:color-mix(in srgb,var({ton}) {min(abs(r), 1.0) * 70:.0f}%,var(--kart))" title="{esc(ipucu)}">{_tr(r)}</span>', r))
        satir.append(hucre)
    t = _tablo(bas, satir, sag=tuple(range(1, len(ks) + 1)), sinif="kormat")
    oz = kr.get("ozet") or {}
    ek = ""
    if oz:
        eu, ed = oz["en_yuksek"], oz["en_dusuk"]
        ek = (_sat("Ortalama |korelasyon|", f_sayi(oz["ort_mutlak"])) + _sat("En yüksek çift", f"{_strateji_adi(eu['a'])} / {_strateji_adi(eu['b'])}: {f_sayi(eu['korelasyon'])}")
              + _sat("En düşük çift", f"{_strateji_adi(ed['a'])} / {_strateji_adi(ed['b'])}: {f_sayi(ed['korelasyon'])}"))
    nedenler = "".join(f'<div class="alt">{esc(_strateji_adi(x["a"]))} × {esc(_strateji_adi(x["b"]))}: {esc(x["neden"])}</div>' for x in kr.get("hucre_neden", []) if x["a"] != x["b"])
    return (t + '<div class="bol">' + ek + "</div>" + nedenler
            + f'<div class="alt">{esc(kr["yontem"])}; en az {esc(str(kr["min_ortak_gun"]))} ortak gün. {esc(kr["esik_notu"])}</div>')


@_guvenli
def _yogunlasma_html(yg: dict) -> str:
    """yogunlasma.json (motor yazar): varlık sınıfı / sembol bazında brüt maruziyet ve açık zarar-kes riski payı. Uyarılar (tek sembol risk payı > %40) tablonun üstünde sarı çizgili kutu olarak gösterilir."""
    if yg.get("semboller") is None:
        return f'<div class="kart alt">Yoğunlaşma ölçülmedi: {esc(yg.get("olculmedi_neden") or "neden yazılmamış")}</div>'
    if not yg["semboller"]:
        return f'<div class="kart alt">{esc(yg.get("olculmedi_neden") or "Açık pozisyon yok.")}</div>'

    def pay(x) -> str:
        if x is None:
            return "—"
        return f'{esc(f_yuzde(x, ondalik=1))}<div class="cubuk"><i style="width:{min(max(x, 0.0), 1.0) * 100:.1f}%"></i></div>'

    def tablo(satirlar: list, ad: str, anahtar) -> str:
        return _tablo([ad, "Brüt", "Kasaya", "Brüt payı", "Açık risk", "Risk payı", "Strateji"],
                      [[f"<b>{esc(anahtar(x))}</b>", esc(f_para(x["brut_nominal"])), esc(f_yuzde(x["brut_oran"])), pay(x["brut_pay"]),
                        esc(f_para(x["stop_riski"])), pay(x["stop_riski_pay"]), esc(str(x["strateji_sayisi"]))] for x in satirlar], sag=(1, 2, 3, 4, 5, 6))
    ust = ""
    eb, es = yg.get("en_buyuk_sembol"), yg.get("en_buyuk_sinif")
    if eb and es:
        ust = (_sat("En büyük sembol (brüt payı)", f"{eb['sembol']} · {f_yuzde(eb['brut_pay'], ondalik=1)}") + _sat("En büyük sınıf (brüt payı)", f"{SINIF_ETIKET.get(es['sinif'], es['sinif'])} · {f_yuzde(es['brut_pay'], ondalik=1)}")
               + _sat("Etkin sembol sayısı (1 / Herfindahl)", f_sayi(yg.get("etkin_sembol_sayisi"))))
    uyar = "".join(f'<div class="uyari uyari">{esc(u["mesaj"] if isinstance(u, dict) else u)}</div>' for u in yg.get("uyarilar", []))
    return (uyar + '<div class="bol">' + ust + "</div>" + tablo(yg["siniflar"], "Varlık sınıfı", lambda x: x["ad"]) + tablo(yg["semboller"], "Sembol", lambda x: x["sembol"])
            + f'<div class="alt">{esc(yg["esikler"]["neden"])} {esc(yg["tanim"])}.</div>')


SINIF_ETIKET = {"kripto": "Kripto", "hisse": "ABD hissesi", "emtia": "Emtia"}


KARNE_DURUM = {"gecti": ("GEÇTİ", "iyi"), "kaldi": ("KALDI", "kotu"), "bilinmiyor": ("bilinmiyor", "uyari")}


def _karne_cip(durum: str, metin: str, ipucu: str = "") -> str:
    et, sn = KARNE_DURUM.get(durum, ("bilinmiyor", "uyari"))
    return f'{esc(metin)} <span class="cip {sn}" title="{esc(ipucu)}">{et}</span>'


@_guvenli
def _aralik_karnesi_html(k: list) -> str:
    """st['aralik_karnesi'] (motor hesaplar): görünür strateji başına 4 ölçüt; pano yalnız çizer."""
    if not k:
        return '<div class="kart alt">Henüz strateji yok.</div>'
    satir = []
    for r in k:
        i, d_, rd_, es = r["islem"], r["dusus"], r["reddedilen"], r["en_iyi_sembol"]
        dm = (f"{f_yuzde(d_['deger'])} / sınır {f_yuzde(d_['limit'])}" if d_.get("limit") is not None else (f"{f_yuzde(d_['deger'])} / referans yok" if d_.get("deger") is not None else "—"))
        satir.append([f"<b>{esc(_ad_goster(r['kimlik']))}</b> <span class=\"alt\">{esc(GRUP_ADI.get(r.get('grup'), ''))}</span>",
                      _karne_cip(i["durum"], f"{i['n']}/{i['esik']}", "kapanan işlem sayısı; eşiğin altı = bilinmiyor"),
                      _karne_cip(d_["durum"], dm, d_.get("neden") or "sınır = min(max(1,5 × geçmiş en kötü düşüş, %5), %15)"),
                      _karne_cip(rd_["durum"], f_yuzde(rd_.get("oran"), ondalik=1) if rd_.get("oran") is not None else "—", rd_.get("neden") or ""),
                      _karne_cip(es["durum"], (f"{es['sembol']} çıkınca {f_para(es['net_cikinca'], True)}" if es.get("sembol") else "—"), es.get("neden") or "")])
    return (_tablo(["Strateji", "İşlem n/20", "Düşüş sınırı (geçmiş en kötü ×1,5; en az %5, en çok %15)", "Limite takılan sinyal % (>%50 kaldı)", "En iyi sembol çıkınca net"], satir, sag=(), sinif="kay"))


def _sekme_ozet(oz, st, gc, ic, sg, isl=None, kn=None, ky=None) -> str:
    if not oz:
        return _veri_yok("ozet.json")
    ds, kz = oz.get("dusus_serisi"), oz.get("gunluk_kz")
    yok = lambda a: f'<div class="alt">{HENUZ_YOK}</div>'          # noqa: E731
    hesap = ('<div class="izgara c4">' + _kutu("Max düşüş", f_yuzde(oz["max_dusus"])) + _kutu("Başlangıç", f_para(oz["baslangic_ozsermaye"]))
             + _kutu("Zirve özsermaye", f_para(oz["zirve_ozsermaye"])) + _kutu("Kapanan işlem", str(oz["sayaclar"]["kapanan_islem"])) + "</div>")
    egri = _egri(gc, oz["baslangic_ozsermaye"]) if gc else _veri_yok("ozsermaye_gecmisi.json")
    g = [_p("Özsermaye eğrisi", egri + '<div class="bol">' + hesap + "</div>", f_para(oz["ozsermaye"]), "g2 yuk"),
         _sag(_p("Risk payı", _risk_payi(oz), "toplam (limit değil): limitler her hesapta ayrı") + _p("Sağlık", _saglik_ozet(sg) if sg else _ek_yok("saglik.json"), sg["durum"] if sg else ""), "s1"),
         _p("Zirveden düşüş", _dusus_grafigi(ds) if ds is not None else yok("dusus_serisi"), f_yuzde(oz["zirveden_dusus"])),
         _p("Günlük K/Z", _kz_grafigi(kz) if kz is not None else yok("gunluk_kz"), f_para(kz[-1]["pnl"], True) if kz else ""),
         _p("İçgörüler", _icgoruler(ic))]
    g.append(_p("Takvim (günlük K/Z ısı haritası)", _takvim(kz, isl, _ajan_haritasi(st), oz.get("gun_kesimi")) if kz is not None else yok("gunluk_kz"), "gün seç: işlemler", "g3"))
    kapali = lambda ad, ic_: f'<details class="ince"><summary>{ad} — göster</summary>{ic_}</details>'          # noqa: E731
    g.append(_p("Kıyas (aynı dönem)", kapali("Kıyas", _kiyas_html(ky) if ky is not None else _bekleyen("kiyas.json", "BTC, S&P 500 al-tut ve mevduat serileri")), "motor hesaplar", "g3"))
    g.append(_p("Dönemsel getiri (gün × grup)", kapali("Dönemsel getiri", _donemsel(oz)), "motor yazar", "g3", duz=oz.get("gunluk_kz_ajan") is not None))
    g.append(_p("Beklenti aralığına göre konum", kapali("Beklenti konumu", _beklenti_tablosu(st) if st else _veri_yok("stratejiler.json")), "SET (tüm stratejiler)", "g3", duz=bool(st)))
    if st and st.get("aralik_karnesi") is not None:
        g.insert(1, _p("Aralık karnesi", _aralik_karnesi_html(st["aralik_karnesi"]), "motor hesaplar · geçti / kaldı / bilinmiyor", "g3", duz=True))
    return _ig("".join(g))


@_guvenli
def _icgoruler(ic) -> str:
    if ic is None:
        return _ek_yok("icgoruler.json")
    c = ic["cumleler"]
    return '<div class="ic">' + ("".join(f"<div>{esc(x)}</div>" for x in c) if c else '<div class="alt">İçgörü yok.</div>') + "</div>"


@_guvenli
def _maliyet_toplam(ml: dict) -> str:
    def satir(ad, b):
        return [esc(ad), esc(f_para(b["ucret"])), esc(f_para(b["kayma"])), esc(f_para(b["funding"], True)), f"<b>{esc(f_para(b['toplam']))}</b>"]
    t = ml["toplam"]
    g = [_tablo(["", "Ücret", "Varsayılan kayma", "Funding", "Toplam"], [satir("Son 24 sa", t["son24s"]), satir("Tüm dönem", t["tum"])], sag=(1, 2, 3, 4))]
    # TradFi funding (kullanıcı kararı 2026-11-09): ayrı satır; tutarlar motor JSON'undan (pano hesap yapmaz)
    tf = ml.get("funding_tradfi")
    if tf is None:
        g.append('<div class="alt" style="padding:8px 11px">TradFi funding ayrımı: henüz veri yok.</div>')
    else:
        g.append(_tablo(["TradFi funding", "Son 24 sa", "Açık poz.", "Kapanan", "Tüm dönem"],
                        [["Binance TradFi perp", esc(f_para(tf["son24s"], True)), esc(f_para(tf["acik"], True)), esc(f_para(tf["kapanan"], True)),
                          f"<b>{esc(f_para(tf['toplam'], True))}</b>"]], sag=(1, 2, 3, 4)))
        g.append('<div class="alt" style="padding:8px 11px">TradFi funding yukarıdaki Funding sütununa dahildir; backtest beklentisi '
                 'kıyaslarında (Dersler, Karne, Koç) hariç tutulur.'
                 + (f' Sınıflanamayan eski kayıt: {esc(str(tf["belirsiz_adet"]))} adet, {esc(f_para(tf["belirsiz_tutar"], True))}.'
                    if tf.get("belirsiz_adet") else "") + '</div>')
    return "".join(g)


@_guvenli
def _reddedilen_son(rd: dict) -> str:
    son = sorted(rd.get("son") or [], key=lambda r: r["zaman"], reverse=True)
    g = []
    if son:
        g.append(_tablo(["Zaman (TSİ)", "Tür", "Neden", "Strateji", "Sembol"],
                        [[esc(tsi(r["zaman"])), esc(r["tur"]), esc(r["neden"]), esc(_ad_goster(r["kimlik"])), esc(ha.coin_adi(r["sembol"]))] for r in son], sinif="kay"))
    else:
        g.append('<div class="alt" style="padding:8px 11px">Son reddedilen / küçültülen kayıt yok.</div>')
    if rd.get("not"):
        g.append(f'<div class="alt" style="padding:8px 11px">{esc(rd["not"])}</div>')
    return "".join(g)


ISLEM_GOSTER = 200                                    # sayfaya gömülen en yeni kapanan işlem sayısı (tamamı islemler.jsonl'dedir)


@_guvenli
def _olaylar_html(ol: list) -> str:
    son = sorted(ol, key=lambda o: o["zaman"], reverse=True)[:50]
    if not son:
        return '<div class="kart alt">Kayıtlı risk olayı yok.</div>'
    return _tablo(["Zaman (TSİ)", "Tür", "Mesaj"], [[f"<b>{esc(tsi(o['zaman']))}</b>", f'<span class="cip">{esc(o["tur"])}</span>', f'<span style="white-space:normal">{esc(o["mesaj"])}</span>']
                                                     for o in son], sinif="kay")


def _sekme_risk(oz, kr=None, yg=None) -> str:
    if not oz:
        return _veri_yok("ozet.json")
    r = oz["risk"]
    gk, kl, ks, ar = r["gunluk_kayip"], r["kaldirac"], r["kill_switch"], r["acik_stop_riski"]
    kartlar = ('<div class="izgara c4">'
               + _kullanim_cubugu("Günlük kayıp", gk["deger"], f_yuzde(gk["limit"], ondalik=0), gk["kullanim"], f_yuzde(gk["deger"]))
               + _kullanim_cubugu("Kaldıraç", kl["deger"], f_sayi(kl["limit"], 1) + "x", kl["kullanim"], f_sayi(kl["deger"]) + ("x" if kl["deger"] is not None else ""))
               + _kullanim_cubugu("Açık zarar-kes riski", ar["deger"], f_yuzde(ar["limit"], ondalik=0), ar["kullanim"], f_yuzde(ar["deger"]))
               + _kullanim_cubugu("Kill switch (zirveden düşüş)", ks["dusus"], f_yuzde(ks["limit"], ondalik=0), None, f_yuzde(ks["dusus"]),
                                  alt_metin=f"mesafe {f_yuzde(ks['mesafe'])}")
               + "</div>")
    notlar = [_sat("Durdurma sınırına kalan", f_yuzde(ks["mesafe"]) + (" — TETİKLENDİ" if ks["tetiklendi"] else ""), "kotu" if ks["tetiklendi"] else "")]
    if kl.get("not"):
        notlar.append(f'<div class="alt" style="margin-top:6px">{esc(kl["not"])}</div>')
    for n in oz["notlar"]:
        notlar.append(f'<div class="alt" style="margin-top:6px">{esc(n)}</div>')
    return _ig(_p("Risk limitleri", kartlar, "toplam, limit değil: limitler her hesapta ayrı", "g3")
               + _p("Kill switch ve notlar", "".join(notlar))
               + (_p("Strateji korelasyonu", _korelasyon_html(kr), "günlük getiri", "g3", duz=True) if kr is not None else "")
               + (_p("Yoğunlaşma (sınıf / sembol)", _yogunlasma_html(yg), "bilgi", "g3", duz=True) if yg is not None else ""))


GUVEN_KAYNAK_ADI = {"binance_perp": "Binance perp", "dukascopy": "Dukascopy", "yahoo": "Yahoo", "spot_vekil": "Binance spot (vekil)"}


@_guvenli
def _veri_guveni_html(vg: dict) -> str:
    """veri_guveni.json (motor yazar): sembol başına son mum, bayatlık, son N günde eksik mum/boşluk, kaynak."""
    oz = vg["ozet"]
    ust = ('<div class="izgara oto">' + _kutu("Veri serisi", str(oz["seri_sayisi"])) + _kutu("Bayat", str(oz["bayat_sayisi"]), "kotu" if oz["bayat_sayisi"] else "iyi")
           + _kutu(f"Eksik mum (son {vg['pencere_gun']} gün)", "—" if oz["eksik_mum_toplam"] is None else str(oz["eksik_mum_toplam"]),
                   "kotu" if oz["eksik_mum_toplam"] else "", f"{oz['olculmeyen_seri']} seri ölçülemedi" if oz["olculmeyen_seri"] else "")
           + _kutu("Boşluk sayısı", "—" if oz["bosluk_toplam"] is None else str(oz["bosluk_toplam"]), "kotu" if oz["bosluk_toplam"] else "") + "</div>")
    satir, notlar = [], []
    for x in vg["semboller"]:
        kay = GUVEN_KAYNAK_ADI.get(x["kaynak"], x["kaynak"]) + (" + spot vekil" if x.get("spot_vekil") else "")
        satir.append([f"<b>{esc(x['sembol'])}</b> <span class='alt'>{esc(x['tf'])}</span>", esc(tsi(x["son_mum_acilis"])), esc(tsi(x["son_mum_kapanis"])),
                      _h(f"{x['bayatlik_dk']} dk" + (" · BAYAT" if x["bayat"] else ""), "kotu" if x["bayat"] else ""),
                      _h("—" if x["eksik_mum"] is None else str(x["eksik_mum"]), "kotu" if x["eksik_mum"] else ""),
                      esc("—" if x["bosluk_sayisi"] is None else f"{x['bosluk_sayisi']} (en uzun {x['en_uzun_bosluk_mum']})"), esc(kay)])
        if x.get("eksik_neden"):
            notlar.append(x["eksik_neden"])
        if x.get("spot_vekil_neden"):
            notlar.append(f"{x['sembol']}: {x['spot_vekil_neden']}")
    tab = _tablo(["Sembol", "Son mum açılış (TSİ)", "Son mum kapanış (TSİ)", "Bayatlık", "Eksik mum", "Boşluk", "Kaynak"], satir, sag=(3, 4, 5), sinif="kay")
    return ust + tab


def _kalp_atisi_kutulari(sg: dict) -> str:
    k = sg.get("kalp_atisi")
    if not k:
        return ""
    kes = k.get("son_kesinti_sn")
    return (_kutu("Son kalp atışı (TSİ)", tsi(k["son"]), "", f"her ≤ {k['aralik_sn']} sn")
            + _kutu("Süreç başlangıcı (TSİ)", tsi(k["baslangic"]) if k.get("baslangic") else "—")
            + _kutu("Son yeniden başlatma kesintisi", "—" if kes is None else f"{_tr(kes, 0)} sn", "", "" if kes is not None else (k.get("son_kesinti_neden") or "")))


def _oran(x: Optional[float]) -> str:
    return f_yuzde(x, ondalik=0)


def _p_metni(t: Optional[dict]) -> str:
    return "—" if not t or t.get("p_deger") is None else ("p<0,001" if t["p_deger"] < 0.001 else f"p={_tr(t['p_deger'], 3)}")


# ----------------------------------------------------------------------------------------------- Karne (radar) ve Koç (motor yazar: karne.json, koc.json)
ESIK_ETIKET = {"gecti": ("eşik geçti", "iyi"), "kaldi": ("eşik kaldı", "kotu"), "esik_yok": ("eşik yok", ""), None: ("ölçülmedi", "")}
SEVIYE_SINIF = {"beklenti_disi": "kotu", "incele": "uyari", "izle": ""}


def _radar_svg(eksenler: list) -> str:
    """6 eksenli radar. Yalnız ölçekleme/çizim: puan (0-100) -> yarıçap. Ölçülmeyen (null) eksen çizilmez, etiketi sönük kalır."""
    cx, cy, R = 130.0, 112.0, 74.0
    n = len(eksenler)
    nokta = lambda i, r: (cx + r * math.cos(-math.pi / 2 + 2 * math.pi * i / n), cy + r * math.sin(-math.pi / 2 + 2 * math.pi * i / n))      # noqa: E731
    halka = "".join('<polygon class="rdr-h" points="' + " ".join("%.1f,%.1f" % nokta(i, R * k / 4) for i in range(n)) + '"/>' for k in (1, 2, 3, 4))
    kol = "".join('<line class="rdr-k" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>' % ((cx, cy) + nokta(i, R)) for i in range(n))
    var = [(i, e) for i, e in enumerate(eksenler) if e["puan"] is not None]
    pts = ["%.1f,%.1f" % nokta(i, R * e["puan"] / 100.0) for i, e in var]
    sekil = (f'<polygon class="rdr-s" points="{" ".join(pts)}"/>' if len(pts) >= 3 else (f'<polyline class="rdr-s" points="{" ".join(pts)}"/>' if len(pts) == 2 else ""))
    dots = "".join('<circle class="rdr-n" cx="%.1f" cy="%.1f" r="3"/>' % nokta(i, R * e["puan"] / 100.0) for i, e in var)
    etik = ""
    for i, e in enumerate(eksenler):
        x, y = nokta(i, R + 16)
        hiza = "middle" if abs(x - cx) < 8 else ("start" if x > cx else "end")
        etik += (f'<text class="rdr-t{"" if e["puan"] is not None else " yok"}" x="{x:.1f}" y="{y + 3:.1f}" text-anchor="{hiza}">{esc(e["ad"])}'
                 + (f' {e["puan"]:.0f}' if e["puan"] is not None else " —") + "</text>")
    return f'<svg class="rdr" viewBox="0 0 260 224" role="img" aria-label="Karne radarı">{halka}{kol}{sekil}{dots}{etik}</svg>'


@_guvenli
def _karne_kart(k: dict, set_strateji: Optional[int] = None) -> str:
    sat = ""
    for e in k["eksenler"]:
        et, sn = ESIK_ETIKET[e["esik_durumu"]]
        sat += (f'<div class="kz2"><b>{esc(e["ad"])}</b> '
                + (f'<b>{e["puan"]:.0f}</b> <span class="cip {sn}">{esc(et)}</span><div class="alt">{esc(e["ozet"] or "")}</div>' if e["puan"] is not None
                   else f'<span class="alt">ölçülmedi</span><div class="alt">{esc(e["neden"] or "")}</div>') + "</div>")
        if e.get("kontroller"):
            sat += '<div class="alt kz2k">' + " · ".join(
                f'{esc(c["ad"])}: ' + ("geçti" if c["gecti"] else ("KALDI" if c["gecti"] is False else f'ölçülemedi ({esc(c.get("neden") or "—")})')) for c in e["kontroller"]) + "</div>"
    if k["tur"] == "set":                               # strateji sayısı karne.json'daki strateji kayıtlarından (sabit sayı yok)
        baslik = f"SET ({set_strateji} strateji birlikte)" if set_strateji is not None else "SET (strateji sayısı bilinmiyor)"
    else:
        baslik = kisa_kimlik(k["kimlik"])
    return (f'<div class="kart karne"><div class="e">{esc(baslik)}</div><div class="alt">{k["islem"]} kapanan işlem · {k["olculen_eksen"]}/6 eksen ölçüldü</div>'
            f'{_radar_svg(k["eksenler"])}{sat}</div>')


@_guvenli
def _karne_html(kr: dict) -> str:
    kartlar = _karne_kart(kr["set"], len(kr["stratejiler"]) if isinstance(kr.get("stratejiler"), list) else None) + "".join(_karne_kart(x) for x in kr["stratejiler"])
    tan = _tablo(["Eksen", "Formül", "Eşik", "Eşik kaynağı", "Asgari örnek"],
                 [[f"<b>{esc(e['ad'])}</b>", f'<span style="white-space:normal">{esc(e["formul"])}</span>', f'<span style="white-space:normal">{esc(e["esik"])}</span>',
                   f'<span style="white-space:normal">{esc(e["esik_kaynagi"])}</span>', f'<span style="white-space:normal">{esc(e["min_ornek"])}</span>'] for e in kr["eksen_tanimlari"]], sinif="kay")
    return ('<div class="izgara oto karneg">' + kartlar + "</div>"
            + f'<details class="ince ip"><summary>Eksen formülleri ve eşik kaynakları</summary>{tan}</details>'
            + f'<div class="alt ip">{esc(kr["yontem"])} {esc(kr["genel_puan_neden"])}</div>'
            + (f'<div class="alt ip">{esc(kr["kaynak_not"])}</div>' if kr.get("kaynak_not") else ""))


def _dayanak_metni(dy: dict) -> str:
    parca = []
    for k, v in dy.items():
        if k == "kova":
            continue
        parca.append(f"{k}={v:.4g}".replace(".", ",") if isinstance(v, float) else (f"{k}={', '.join(map(str, v))}" if isinstance(v, list) else f"{k}={v}"))
    return " · ".join(parca)


@_guvenli
def _koc_html(kc: dict) -> str:
    sy = kc["sayim"]
    ust = ('<div class="izgara oto">' + _kutu("Beklenti dışı", str(sy["beklenti_disi"]), "kotu" if sy["beklenti_disi"] else "") + _kutu("İncele", str(sy["incele"]), "uyarir" if sy["incele"] else "")
           + _kutu("İzle", str(sy["izle"])) + _kutu("Atlanan (örnek az)", str(len(kc["atlanan"]))) + "</div>")
    b = ""
    for x in kc["bulgular"]:
        i = x["istatistik"]
        b += (f'<div class="koc {SEVIYE_SINIF[x["seviye"]]}"><div class="sat"><span><b>{esc(x["baslik"])}</b> <span class="alt">{esc(kisa_kimlik(x["kapsam"]))}</span></span>'
              f'<b class="{SEVIYE_SINIF[x["seviye"]]}">{esc(x["seviye_etiket"])}</b></div><div>{esc(x["metin"])}</div>'
              f'<div class="alt">Dayanak: {esc(_dayanak_metni(x["dayanak"]))}</div>'
              + (f'<div class="alt">İstatistik: {esc(i["test"])} · p {_tr(i["p_ham"], 4)} · {i["test_sayisi"]} test · düzeltilmiş p {_tr(i["p_duzeltilmis"], 4)} ({esc(i["duzeltme"])}) · referans: {esc(x["referans"])}</div>'
                 if i.get("p_ham") is not None and i.get("p_duzeltilmis") is not None else
                 f'<div class="alt">İstatistik: {esc(i["test"])} · p — ({esc(i.get("neden") or "test yapılmadı")}) · referans: {esc(x["referans"])}</div>')
              + f'<div class="alt">{esc(x["oneri"])}</div></div>')
    if not kc["bulgular"]:
        b = '<div class="kart alt">Şu an kural eşiğini geçen bulgu yok (ya da örnek henüz yetersiz: aşağıdaki atlanan listesine bak).</div>'
    atl = ("".join(f'<div class="alt">Atlandı — {esc(kisa_kimlik(a["kapsam"]))}: {esc(a["neden"])}</div>' for a in kc["atlanan"])) if kc["atlanan"] else ""
    kural = "".join(f'<div class="alt">{esc(k["ad"])} — referans: {esc(k["referans"])}; {esc(k["kaynak"])}</div>' for k in kc["kurallar"])
    return (ust + '<div class="kocl">' + b + "</div>" + f'<div class="ip">{atl}</div>' + f'<details class="ince ip"><summary>Kurallar ve yöntem</summary>{kural}</details>'
            + f'<div class="alt ip">{esc(kc["yontem"])}</div><div class="alt ip">{esc(kc["uyari"])}</div>'
            + (f'<div class="alt ip">{esc(kc["kaynak_not"])}</div>' if kc.get("kaynak_not") else ""))


# ----------------------------------------------------------------------------------------------- İşlem açıklama çekmecesi (islemler.jsonl alanları; motor yazar)
CIKIS_ACIKLAMA = {
    "stop": "Fiyat stop seviyesine değdi; planlanan zarar. Tek başına hata değildir.",
    "stop_gap": "Mum stopun ötesinde AÇILDI; dolum açılış fiyatından (boşluk). Planlanan zarardan büyük olabilir.",
    "hedef": "Fiyat hedef seviyesine ulaştı.",
    "sinyal": "Stratejinin çıkış sinyali geldi (karar mumunun kapanışında; dolum sonraki açılışta).",
    "zaman": "Azami tutma süresi doldu (zaman çıkışı).",
    "kismi": "Kısmi kâr alma seviyesi.",
    "kismi_tam": "Kalan miktar minimum lot altına düştüğü için kısmi çıkış pozisyonu tamamen kapattı.",
    "hedef_sifir": "Portföy stratejisinin hedef ağırlığı sıfıra indi; pozisyon kapandı.",
    "yon_degisim": "Portföy stratejisi yön değiştirdi; eski yön kapandı.",
    "kucultme": "Hedef ağırlık küçüldü; kalan miktar kapandı.",
    "kaldirac_azalt": "Brüt kaldıraç sert tavana yaklaştığı için pozisyon orantılı küçültüldü.",
    "kill_switch": "Kill switch (zirveden {kill} düşüş) tetiklendi; tüm pozisyonlar kapandı.",
    "gunluk_limit": "Günlük kayıp limiti ({gunluk}) tetiklendi; pozisyonlar kapandı.",
    "veri_sonu": "Tekrar/backtest verisinin sonunda açık pozisyon kapatıldı.",
}


LIMIT_BILINMIYOR = {"kill": "bilinmiyor", "gunluk": "bilinmiyor", "kaldirac": "bilinmiyor"}


def _yuzde_metni(oran) -> str:
    return f"%{float(oran) * 100:g}".replace(".", ",")


def limit_metinleri(veri: dict) -> dict:
    """Limit METİNLERİ (hesap değil): motorun yazdığı değerlerden. Öncelik ozet.json risk.*.limit (oran; motorun uyguladığı), yoksa
    butunluk.json sanal 'sert_limitler' ayrıntısı (yüzde birimi; motor/risk/limitler.py). Hiçbiri yoksa 'bilinmiyor' (sabit sayı yazılmaz)."""
    out = dict(LIMIT_BILINMIYOR)
    sanal = (veri.get("butunluk") or {}).get("sanal") if isinstance(veri.get("butunluk"), dict) else None
    sl = next(((x.get("ayrinti") or {}) for x in (sanal or []) if isinstance(x, dict) and x.get("id") == "sert_limitler"), {})
    r = (veri.get("ozet") or {}).get("risk") if isinstance(veri.get("ozet"), dict) else None
    r = r if isinstance(r, dict) else {}
    for ad, blok, sl_ad, yuzde in (("kill", "kill_switch", "kill_switch_dusus_yuzde", True), ("gunluk", "gunluk_kayip", "gunluk_max_kayip_yuzde", True),
                                   ("kaldirac", "kaldirac", "max_kaldirac", False)):
        v = r[blok].get("limit") if isinstance(r.get(blok), dict) else None
        if v is None and isinstance(sl.get(sl_ad), (int, float)):
            v = sl[sl_ad] / 100.0 if yuzde else sl[sl_ad]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[ad] = _yuzde_metni(v) if yuzde else f"{float(v):g}x".replace(".", ",")
    return out


def cikis_aciklama(neden: str, lim: Optional[dict] = None) -> str:
    return CIKIS_ACIKLAMA.get(neden, "Bu çıkış nedeni için açıklama sözlüğünde kayıt yok.").format(**(lim or LIMIT_BILINMIYOR))


def sozluk(lim: Optional[dict] = None) -> list:
    return [(k, v.format(**(lim or LIMIT_BILINMIYOR))) for k, v in SOZLUK]


# ----------------------------------------------------------------------------------------------- YENİ PANO: 6 sekme (ÖZET · AÇIK · KAPANAN · K/Z · ÖĞRENME · TEKNİK)
# Yalnız gösterim: toplamlar/sayımlar durum dosyalarındaki değerlerden biçimlendirme için toplanır; risk hesabı/limit yok (limitler motor/risk/limitler.py).
SEKMELER = (("t1", "ÖZET"), ("t2", "AÇIK"), ("t3", "KAPANAN"), ("t4", "K/Z"), ("t5", "ÖĞRENME"), ("t6", "TEKNİK"))
DIGER_TOPLU = "Diğer hesaplar"
KONSENSUS_AD = ha.hesap_adi("ct_konsensus")          # Telegram ile aynı ad (tek kaynak: hesap_adlari.py)
RISK_YAKIN_ORAN = 0.7                      # günlük kayıp limitinin >= %70'i kullanıldıysa sarı (kullanıcı kararı)
NEDEN_TR = {"stop": "stop", "hedef": "hedef", "kismi": "kısmi çıkış", "kismi_tam": "kısmi çıkış", "veri_sonu": "veri sonu", "sinyal": "sinyal",
            "hedef_sifir": "sinyal", "yon_degisim": "yön değişti", "kucultme": "küçültme", "kill_switch": "kill switch", "gunluk_limit": "günlük limit",
            "gunluk_kayip_limiti": "günlük limit", "isinma": "ısınma"}


def _dec(x) -> Optional[Decimal]:
    try:
        return None if x is None else Decimal(str(x))
    except Exception:  # noqa: BLE001
        return None


def _usd(x, isaretli: bool = False) -> str:
    v = _dec(x)
    return "—" if v is None else _tr(v, 2, isaretli) + " $"


def _fiyat(x) -> str:
    v = _dec(x)
    if v is None:
        return "—"
    if abs(v) >= 1:
        return _tr(v, 2)
    if abs(v) >= Decimal("0.01"):
        return _tr(v, 3)
    g = f"{abs(v):.3g}"
    if "e" in g:
        g = f"{abs(v):.8f}".rstrip("0") or "0"
    return ("−" if v < 0 else "") + g.replace(".", ",")


def _kisa_saat(z) -> str:
    """UTC zaman metni -> 'GG.AA SS:DD' (TSİ)."""
    t = tsi(z)
    return t[:5] + t[10:] if len(t) >= 16 and t[2] == "." else t


def _sure(z0, z1: datetime) -> str:
    try:
        sn = int((z1 - d.zaman_oku(z0)).total_seconds())
    except (TypeError, ValueError):
        return "—"
    if sn < 0:
        return "—"
    if sn < 3600:
        return f"{sn // 60} dk"
    if sn < 86400:
        return f"{sn // 3600} sa {(sn % 3600) // 60} dk"
    return f"{sn // 86400} g {(sn % 86400) // 3600} sa"


def _yon_html(y: str) -> str:
    return _h(y, "iyi" if y == "long" else "kotu")


def _bos(ne: str = HENUZ_YOK) -> str:
    return f'<div class="kart alt" data-bos>{esc(ne)}</div>'


def _bos_mu(h: str) -> bool:
    """Gövde yalnızca 'henüz veri yok / veri birikiyor' ise True (bölüm gizlenir)."""
    return "data-bos" in h and len(re.sub(r"<[^>]+>", "", h).strip()) < 60


def _topla(degerler) -> Decimal:
    t = Decimal(0)
    for v in degerler:
        x = _dec(v)
        if x is not None:
            t += x
    return t


# ---- hesap ve işlem listeleri
def _acik_liste(veri: dict) -> list:
    mr, st = veri.get("maruziyet"), veri.get("stratejiler")
    if mr and isinstance(mr.get("pozisyonlar"), list):
        ana = [p for p in mr["pozisyonlar"] if isinstance(p, dict) and "sembol" in p]
    elif st:
        ana = [{**p, "kimlik": p.get("kimlik") or x["kimlik"]} for x in st["stratejiler"] for p in (x.get("acik_pozisyonlar") or []) if isinstance(p, dict) and "sembol" in p]
    else:
        ana = []
    ct = (veri.get("ct_hesap") or {}).get("pozisyonlar") or []
    return sorted(ana + list(ct), key=lambda p: str(p.get("giris_zamani") or ""), reverse=True)


def _kapanan_liste(veri: dict) -> list:
    isl = list(veri.get("islemler") or []) + list((veri.get("ct_hesap") or {}).get("islemler") or [])
    return sorted(isl, key=lambda x: x["zaman"], reverse=True)


def _liste_basligi(c1: str, c2: str, c3: str, c4: str) -> str:
    return f'<div class="lh"><span>{esc(c1)}</span><span>{esc(c2)}</span><span>{esc(c3)}</span><span>{esc(c4)}</span></div>'


def _acik_satiri(p: dict, simdi: datetime) -> str:
    kz = p.get("kz")
    oran = f_yuzde(p.get("kz_oran"), True) if p.get("kz_oran") is not None else "—"
    hesap = _ad_goster(p.get("kimlik", ""), bool(p.get("ct")))
    ayr = [_sat("Hesap", hesap), _sat("Zarar-kes", _fiyat(p.get("stop")))]
    if p.get("hedef") is not None:
        ayr.append(_sat("Hedef", _fiyat(p["hedef"])))
    if p.get("nominal") is not None:
        ayr.append(_sat("Büyüklük", _usd(p["nominal"]) + (f" (kasanın {f_yuzde(p['kasaya_orani'])})" if p.get("kasaya_orani") is not None else "")))
    if p.get("kaldirac") is not None:
        ayr.append(_sat("Kaldıraç", f"{_tr(float(p['kaldirac']))}x"))
    g = p.get("giris_gerekcesi")
    neden = g.get("metin") if isinstance(g, dict) else (g if isinstance(g, str) else None)
    if neden:
        ayr.append(_sat("Açılış nedeni", str(neden)))
    return (f'<details class="sr"><summary><span class="c"><b>{esc(ha.coin_adi(p["sembol"]))} {_yon_html(p["yon"])}</b><span class="alt">{esc(hesap)}</span></span>'
            f'<span class="c">{esc(_fiyat(p.get("giris_fiyati")))}<br>→ {esc(_fiyat(p.get("mark_fiyat")))}</span>'
            f'<span class="c"><b class="{_isaret_sinifi(kz)}">{esc(_usd(kz, True))}</b><span class="alt">{esc(oran)}</span></span>'
            f'<span class="c">{esc(_sure(p.get("giris_zamani"), simdi))}</span></summary><div class="ayr">{"".join(ayr)}</div></details>')


def _kapanan_satiri(x: dict) -> str:
    net = _dec(x["net_pnl_yerel"]) or Decimal(0)
    tutar = (_dec(x.get("giris_fiyati")) or Decimal(0)) * (_dec(x.get("miktar")) or Decimal(0))
    oran = f_yuzde(float(net / tutar), True) if tutar else "—"
    hesap = _ad_goster(x["kimlik"], bool(x.get("ct")))
    try:
        zc = d.zaman_oku(x["zaman"])
        epoch = int(zc.timestamp())
    except (TypeError, ValueError):
        zc, epoch = None, 0
    ayr = [_sat("Hesap", hesap), _sat("Giriş", f"{_fiyat(x.get('giris_fiyati'))} · {_kisa_saat(x.get('giris_zamani'))}"),
           _sat("Çıkış", f"{_fiyat(x.get('cikis_fiyati'))} · {_kisa_saat(x['zaman'])}"), _sat("Süre", _sure(x.get("giris_zamani"), zc) if zc else "—")]
    if x.get("ucret") not in (None, ""):
        ayr.append(_sat("Komisyon", _usd(x["ucret"])))
    if x.get("ders") not in (None, ""):
        ayr.append(_sat("Ders", str(x["ders"])))
    g = x.get("giris_gerekcesi")
    if isinstance(g, dict) and g.get("metin"):
        ayr.append(_sat("Açılış nedeni", str(g["metin"])))
    neden = NEDEN_TR.get(x["cikis_nedeni"], x["cikis_nedeni"])
    return (f'<details class="sr" data-t="{epoch}" data-gun="{esc(_tsi_makine(x["zaman"])[:10])}" data-net="{esc(str(net))}">'
            f'<summary><span class="c"><b>{esc(ha.coin_adi(x["sembol"]))} {_yon_html(x["yon"])}</b><span class="alt">{esc(hesap)}</span></span>'
            f'<span class="c">{esc(_kisa_saat(x["zaman"]))}</span>'
            f'<span class="c"><b class="{_isaret_sinifi(net)}">{esc(_usd(net, True))}</b><span class="alt">{esc(oran)}</span></span>'
            f'<span class="c">{esc(neden)}</span></summary><div class="ayr">{"".join(ayr)}</div></details>')


def _liste_kutusu(satirlar: list, bas: tuple, kimlik: str = "") -> str:
    if not satirlar:
        return _bos("Henüz kayıt yok")
    return (f'<div class="lst"{(" id=" + kimlik) if kimlik else ""}>{_liste_basligi(*bas)}{"".join(satirlar)}</div>'
            '<div class="bos" hidden>Bu dönemde kayıt yok</div><button type="button" class="daha">Daha fazla göster</button>')


# ---- şerit / risk / ne yapmalıyım
def risk_durumu(oz: dict) -> dict:
    """Risk durumu kutusu. Limitler motor/risk/limitler.py'den (kopya yok); değerler durum dosyasındaki risk bloğundan. Yalnız gösterim."""
    r = oz.get("risk") or {}
    gk, ks = r.get("gunluk_kayip") or {}, r.get("kill_switch") or {}
    g_lim = SERT_LIMITLER.gunluk_max_kayip_yuzde / 100.0
    k_lim = SERT_LIMITLER.kill_switch_dusus_yuzde / 100.0
    deger, dusus = gk.get("deger"), ks.get("dusus")
    kul = None if deger is None else float(deger) / g_lim
    kill = bool(ks.get("tetiklendi"))
    limit_doldu = bool(gk.get("tetiklendi")) or (kul is not None and kul >= 1.0)
    if kill or limit_doldu:
        seviye, ad, sinif = "durdu", "Durdu", "kotu"
    elif kul is not None and kul >= RISK_YAKIN_ORAN:
        seviye, ad, sinif = "yakin", "Limite yakın", "uyarir"
    elif kul is None:
        seviye, ad, sinif = "bilinmiyor", "—", ""
    else:
        seviye, ad, sinif = "guvenli", "Güvenli", "iyi"
    kalan = None
    e = _dec(oz.get("ozsermaye"))
    if deger is not None and e is not None and float(deger) < 1:
        kalan = max(Decimal(0), e * Decimal(str(g_lim - float(deger))) / Decimal(str(1 - float(deger))))   # günlük limite inmeden önce kaybedilebilecek tutar
    mesafe = (k_lim - float(dusus)) if dusus is not None else ks.get("mesafe")
    z = _dec(oz.get("zirve_ozsermaye"))
    kill_usd = max(Decimal(0), e - z * Decimal(str(1 - k_lim))) if (e is not None and z is not None) else None
    return {"seviye": seviye, "ad": ad, "sinif": sinif, "kill": kill, "limit_doldu": limit_doldu, "kalan_usd": kalan, "mesafe": mesafe, "mesafe_usd": kill_usd}


def _risk_kutusu(oz: dict, dikkat: bool = False) -> str:
    rd = risk_durumu(oz)
    if dikkat and rd["seviye"] in ("guvenli", "bilinmiyor"):          # alarm ya da karantina varken kutu yeşil kalmaz
        rd = {**rd, "seviye": "dikkat", "ad": "Dikkat", "sinif": "uyarir"}
    alt = [f"günlük kalan {_usd(rd['kalan_usd'])}" if rd["kalan_usd"] is not None else "",
           f"durdurma sınırına kalan {f_yuzde(rd['mesafe'])}" if rd["mesafe"] is not None else ""]
    return _kutu("Risk durumu", rd["ad"], rd["sinif"], alt, f' data-risk="{rd["seviye"]}"')


def _acik_sayi_metni(oz: dict, veri: dict) -> str:
    """Açık pozisyon sayısı: ana hesaplar + (varsa) konsensüs hesabı: '1 + 1 konsensüs' (sekme rozeti ve Açık listesiyle aynı sayı)."""
    n = oz["sayaclar"]["acik_pozisyon"]
    k = len((veri.get("ct_hesap") or {}).get("pozisyonlar") or [])
    return f"{n} + {k} konsensüs" if k else str(n)


def _dikkat_var(veri: dict, simdi: Optional[datetime]) -> bool:
    """Performans uyarısı (beklenti alarmı) ya da karantina var mı (risk kutusunun renği için)."""
    kq = ((veri.get("saglik") or {}).get("karantina")) or {}
    if kq.get("gorunur") or kq.get("gizli"):
        return True
    if simdi is None or not veri.get("ozet"):
        return False
    return any(m.startswith("BEKLENTİ") for _, m in uyarilar(veri, [], simdi))


def _serit(oz: dict, mr, veri: Optional[dict] = None, simdi: Optional[datetime] = None) -> str:
    """Sabit üst şerit (her sekmede): 6 kutu. Büyük rakam $, alt yazı %. Tüm paper hesaplarının toplamı."""
    veri = veri or {}
    bas = oz.get("baslangictan_pnl", oz["toplam_pnl"])
    brut = f"brüt {_usd(mr['toplam_brut_nominal'])}" if mr and mr.get("toplam_brut_nominal") is not None else ""
    e, z = _dec(oz["ozsermaye"]), _dec(oz["zirve_ozsermaye"])
    dusus_usd = _usd(e - z, True) if e is not None and z is not None else "—"
    kutular = ('<div class="izgara serit">'
               + _kutu("Kasa", _usd(oz["ozsermaye"]), "", f"başlangıç {_usd(oz['baslangic_ozsermaye'])}")
               + _kutu("Bugün K/Z", _usd(oz["gun_pnl"], True), _isaret_sinifi(oz["gun_pnl"]), [f_yuzde(oz["gun_getiri"], True), "TSİ günü" if oz.get("gun_kesimi") == "Europe/Istanbul" else ""])
               + _kutu("Toplam K/Z", _usd(bas, True), _isaret_sinifi(bas), f_yuzde(oz["toplam_getiri"], True))
               + _kutu("Açık poz.", _acik_sayi_metni(oz, veri), "", brut)
               + _kutu("Zirveden düşüş", dusus_usd, "kotu" if oz["zirveden_dusus"] else "", f_yuzde(oz["zirveden_dusus"]))
               + _risk_kutusu(oz, _dikkat_var(veri, simdi)) + "</div>")
    ct = (veri.get("kurulumlar") or {}).get("ct")
    if ct:
        dahil = f"{KONSENSUS_AD} ayrı kasa: {_usd(ct['ozsermaye'])} ({_usd(ct['toplam_pnl'], True)}), toplama dahil değil."
    else:
        dahil = ""
    uretim = f' data-uretim="{esc(d.zaman_str(simdi))}"' if simdi else ""
    return kutular + f'<div class="alt serit-not">{esc(dahil)} <span id="gunc"{uretim}></span></div>'


def ne_yapmali(veri: dict, sorunlar: list, simdi: datetime) -> tuple:
    """-> (sınıf, tek cümle). Kullanıcı kararı/işi gerektiren durum yoksa varsayılan metin."""
    oz, sg = veri.get("ozet"), veri.get("saglik")
    if sorunlar or not oz:
        return "gerek", "Durum verisi okunamıyor: sunucuyu kontrol edin."
    canli = oz["kaynak"] != "backtest"
    rd = risk_durumu(oz)
    u = uyarilar(veri, sorunlar, simdi)
    if rd["kill"]:
        return "gerek", "Kill switch devrede, tüm işlemler durdu: nedenini inceleyip yeniden başlatma kararını siz verin."
    if rd["limit_doldu"]:
        return "gerek", "Günlük kayıp limiti doldu: bugün yeni işlem açılmaz, yarın kendiliğinden devam eder."
    if canli and (any(m.startswith("VERİ BAYAT") for _, m in u) or (sg and (sg["durum"] != "ok" or sg["servis"]["calisiyor"] is False))):
        return "gerek", "Motor durmuş ya da veri bayat görünüyor: sunucuyu ve servisi kontrol edin."
    kq = (sg or {}).get("karantina") or {}
    if kq.get("gorunur") or kq.get("gizli"):
        return "gerek", "Karantinada strateji var: kod hatasının giderilmesi ya da stratejinin kapatılması için karar verin."
    if any(m.startswith("BEKLENTİ ALARMI") for _, m in u):
        return "gerek", "Beklenti alarmı var: ilgili stratejiyi tutma ya da durdurma kararı için inceleyin."
    if (((veri.get("disk") or {}).get("durum")) or {}).get("alarm"):
        return "gerek", "Sunucu diski dolmak üzere: yer açın."
    return "", "Bir şey yapmanız gerekmiyor."


def _uyari_listesi(veri: dict, sorunlar: list, simdi: datetime) -> str:
    """DURUM kartındaki uyarı ayrıntıları (üst bantta yalnız tek satırlık özet var)."""
    sira = {"kritik": 0, "uyari": 1, "bilgi": 2}
    u = sorted(uyarilar(veri, sorunlar, simdi), key=lambda x: sira.get(x[0], 3))
    return "".join(f'<div class="uyari {s_}" role="{"alert" if s_ == "kritik" else "note"}">{esc(_adsiz(m))}</div>' for s_, m in u)


def _durum_isigi(veri: dict, sorunlar: list, simdi: datetime) -> tuple:
    """-> (kırmızı mı, html). TEKNİK'te sorun varsa kırmızı olur ve ÖZET'in en üstüne çıkar."""
    sg = veri.get("saglik")
    kritik = [m for s, m in uyarilar(veri, sorunlar, simdi) if s == "kritik"]
    sorun = bool(sorunlar or kritik or (sg and (sg["durum"] != "ok" or any(v["bayat"] for v in sg["veri"]))))
    if sorun:
        ilk = _adsiz(kritik[0]) if kritik else "sağlık denetimi başarısız"
        perf = bool(kritik) and all(m.upper().startswith("BEKLENTİ") for m in kritik) and not sorunlar
        if perf:
            return True, '<div class="isik kotu">● Performans uyarısı</div>'
        return True, f'<div class="isik kotu">● Teknik sorun var: {esc(ilk)} <label class="lnk" for="t6">TEKNİK →</label></div>'
    return False, '<div class="isik iyi">● Sistem sağlıklı</div>'


# ---- öğrenme verisi (ders + makine öğrenmesi)
def _ogrenme_ek(dizin) -> dict:
    """Ham öğrenme kayıtları: kapanan adaylar ve alınmayan sinyaller (son satırlar); okunamazsa boş."""
    def satirlar(ad: str, son: int) -> list:
        out = []
        try:
            for ln in (Path(dizin) / ad).read_text(encoding="utf-8").splitlines()[-son:]:
                try:
                    o = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    out.append(o)
        except OSError:
            pass
        return out
    return {"adaylar": satirlar("ogrenme_adaylar.jsonl", 5000), "alinmayan": satirlar("alinmayan_sinyaller.jsonl", 5000)}


def _z(s) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _kurulum_adi(kurulum: str, og: dict, gizli: set) -> str:
    ters = {v: k for k, v in (og.get("esleme") or {}).items()}
    return ha.hesap_adi(ters.get(kurulum, kurulum), gorunur=kurulum not in gizli)


def ders_ozeti(kr: Optional[dict], ek: dict, a_sonuc, simdi: datetime) -> dict:
    og = (kr or {}).get("ana_ogrenme") or {}
    st = og.get("ders")
    if not isinstance(st, dict):
        return {"acik": False}
    gizli = kr.get("gizli_kurulum") or set()
    askida = ((og.get("fren") or {}).get("askida") or {}) if isinstance(og.get("fren"), dict) else {}
    yasayan = [k for k, v in st.items() if isinstance(v, dict) and v.get("status") in ("candidate", "alive") and k not in askida]   # girişi atlatan dersler (ogrenme_adaptor._etkin_dersler ile aynı kural)
    kayit = sorted(((str(v.get("born") or ""), k, v) for k, v in st.items() if isinstance(v, dict)), key=lambda t: t[0], reverse=True)
    esik7 = simdi - timedelta(days=7)
    degisen = len([a for a in (ek.get("alinmayan") or []) if str(a.get("neden") or "").startswith("ders:") and (_z(a.get("zaman")) or esik7) >= esik7])
    katki = pencere = None
    if isinstance(a_sonuc, dict) and isinstance(a_sonuc.get("nedenler"), list):
        sat = [o for o in a_sonuc["nedenler"] if str(o.get("neden") or "").startswith("ders:") and o.get("toplam_r") is not None]
        if sat:
            katki, pencere = -float(_topla(o["toplam_r"] for o in sat)), a_sonuc.get("pencere_gun")
    son = (kayit[0][0], _kurulum_adi(kayit[0][1].partition(":")[2], og, gizli)) if kayit and kayit[0][0] else None
    son5 = [(b, _kurulum_adi(k.partition(":")[2], og, gizli), v.get("status")) for b, k, v in kayit[:5]]
    return {"acik": True, "yasayan": len(yasayan), "son": son, "degisen7": degisen, "katki_r": katki, "pencere": pencere, "son5": son5}


def ml_ozeti(kr: Optional[dict], ek: dict, a_sonuc, simdi: datetime) -> dict:
    og = (kr or {}).get("ana_ogrenme") or {}
    if not og.get("veri_var"):
        return {"acik": False}
    try:
        from motor.canli import ogrenme_adaptor as oa
        min_n = int(getattr(oa, "MIN_EGITIM", 10))
    except Exception:  # noqa: BLE001
        min_n = 10
    egitim = (og.get("durum") or {}).get("egitim") or {}
    modelli = {k for k, v in egitim.items() if isinstance(v, dict) and v.get("model")} | set(og.get("filtre") or [])
    onay = sorted((a for a in (ek.get("adaylar") or []) if a.get("alindi") and a.get("kurulum") in modelli), key=lambda a: str(a.get("ts") or ""), reverse=True)
    sonuclu = [a for a in onay if a.get("r") is not None][:20]
    esik7 = simdi - timedelta(days=7)
    ret = [a for a in (ek.get("alinmayan") or []) if a.get("neden") == "ml_filtre"]
    onay7 = [a for a in onay if (_z(a.get("ts")) or esik7) >= esik7]
    ret7 = [a for a in ret if (_z(a.get("zaman")) or esik7) >= esik7]
    fark = pencere = None
    if isinstance(a_sonuc, dict) and isinstance(a_sonuc.get("nedenler"), list):
        sat = [o for o in a_sonuc["nedenler"] if o.get("neden") == "ml_filtre" and o.get("toplam_r") is not None]
        if sat and any(int(o.get("cozulen") or 0) > 0 for o in sat):         # 0 işlem ölçüldüyse fark yok: "henüz ölçülemedi"
            fark, pencere = -float(_topla(o["toplam_r"] for o in sat)), a_sonuc.get("pencere_gun")
    son_egitim = max(((v.get("zaman"), v.get("n")) for v in egitim.values() if isinstance(v, dict) and v.get("zaman")), default=None, key=lambda t: str(t[0]))
    olaylar = ([(str(a.get("ts") or ""), a.get("enstruman"), "aldı", a.get("r")) for a in onay[:5]]
               + [(str(a.get("zaman") or ""), a.get("sembol"), "ret", None) for a in ret[-5:]])
    olaylar.sort(key=lambda t: t[0], reverse=True)
    sayac: dict = {}
    for a in (ek.get("adaylar") or []):                       # kurulum başına kapanmış (sonucu belli) alınmış işlem: model MIN_EGITIM'e ulaşınca kurulur
        if a.get("alindi") and a.get("r") is not None:
            sayac[a.get("kurulum")] = sayac.get(a.get("kurulum"), 0) + 1
    return {"acik": True, "model_sayisi": len(modelli), "en_cok_islem": max(sayac.values(), default=0), "isabet_n": len(sonuclu), "isabet_w": len([a for a in sonuclu if float(a["r"]) > 0]), "min_n": min_n,
            "onay7": len(onay7), "ret7": len(ret7), "fark_r": fark, "pencere": pencere, "son_egitim": son_egitim, "son5": olaylar[:5]}


def _r_metni(r) -> str:
    return "—" if r is None else f"{_tr(float(r), 2, True)} R"


def _r_usd(veri: dict):
    """Ortalama işlem riski ($): kapanan işlemlerde |net K/Z ÷ R| ortalaması (durum verisinden; veri yoksa None)."""
    v = []
    for x in _kapanan_liste(veri):
        net, r = _dec(x.get("net_pnl_yerel")), x.get("r")
        if net is not None and isinstance(r, (int, float)) and abs(r) >= 0.2:
            v.append(abs(net / Decimal(str(r))))
    return (_topla(v) / len(v)) if v else None


def _r_dipnot(r_usd=None) -> str:
    return '<div class="alt">1 R = bir işlemde göze alınan risk' + (f" (≈ {_usd(r_usd)})" if r_usd is not None else "") + "</div>"


def _ders_karti(o: dict, tam: bool = False, r_usd=None) -> str:
    if not o.get("acik"):
        return _p("Ders öğrenmesi", _sat("Durum", "Kapalı"))
    ok_ = o["yasayan"] > 0
    g = [_sat("Durum", "Açık, işlemleri etkiliyor" if ok_ else "Açık, henüz ders çıkmadı", "iyi" if ok_ else "uyari"),
         _sat("Son öğrendiği", f"{_gun_tr(o['son'][0])} · {o['son'][1]} için yeni ders" if o.get("son") else "Henüz ders yok"),
         _sat("Son 7 günde değiştirdiği işlem", str(o["degisen7"])),
         _sat("Katkı (dersler olmasaydı farkı)", f"{_r_metni(o['katki_r'])} · son {o['pencere']} gün" if o.get("katki_r") is not None else "Henüz ölçülemedi", _isaret_sinifi(o.get("katki_r")))]
    if tam:
        durum_tr = {"alive": "geçerli", "candidate": "aday", "retired": "emekli"}
        g.append('<h4 class="alt">Son 5 ders</h4>' + ("".join(_sat(f"{_gun_tr(b)} · {ad_}", durum_tr.get(s_, "—")) for b, ad_, s_ in o["son5"]) or '<div class="alt">Henüz ders yok</div>'))
    return _p("Ders öğrenmesi", "".join(g) + _r_dipnot(r_usd))


def ml_durum_ifadesi(o: dict) -> tuple:
    """ml_ozeti çıktısı -> (ortak ifade, sınıf). Pano ML kartı ve Telegram strateji verisi aynı fonksiyonu kullanır (kullanıcı kararı 2026-11-20)."""
    if not o.get("acik"):
        return "Kapalı", ""
    if o.get("model_sayisi"):
        return "Açık, işlemleri etkiliyor", "iyi"
    if int(o.get("en_cok_islem") or 0) < int(o.get("min_n") or 10):
        return f"Açık, veri birikiyor ({int(o.get('en_cok_islem') or 0)}/{int(o.get('min_n') or 10)} işlem)", "uyari"
    return "Açık, model bekleniyor", "uyari"


def _ml_karti(o: dict, tam: bool = False, r_usd=None) -> str:
    if not o.get("acik"):
        return _p("Makine öğrenmesi", _sat("Durum", "Kapalı"))
    se = o.get("son_egitim")
    durum = ml_durum_ifadesi(o)
    egitim = f"{tsi(se[0])[:10]} · {se[1]} örnek" if se else ("eğitim tarihi kayıtlı değil" if o["model_sayisi"] else "henüz eğitim yok")
    son7 = f"{o['onay7']} onay · {o['ret7']} ret" if (o["onay7"] or o["ret7"]) else "henüz karar yok"
    fark = (f"{_r_metni(o['fark_r'])} · son {o['pencere']} gün" if o.get("pencere") else _r_metni(o["fark_r"])) if o.get("fark_r") is not None else "henüz ölçülemedi"
    g = [_sat("Durum", *durum), _sat("Son eğitim", egitim), _sat("Son 7 gün", son7),
         _sat("Katkı (ML'li − ML'siz)", fark, _isaret_sinifi(o.get("fark_r")))]
    if tam:
        g.append('<h4 class="alt">Son 5 karar</h4>' + ("".join(_sat(f"{_kisa_saat(z)} · {ha.coin_adi(s_)}", f"{k_} · {_r_metni(r)}" if k_ == "aldı" else k_) for z, s_, k_, r in o["son5"]) or '<div class="alt">Henüz karar yok</div>'))
    return _p("Makine öğrenmesi", "".join(g) + _r_dipnot(r_usd))


def _degisiklikler_karti(veri: dict) -> str:
    """Çıkış karşı-olgusu ve "alınsaydı" otomatik değişiklikleri: her biri tek satır."""
    kanit = veri.get("cikis_kanit") or {}
    satir = []
    ov = kanit.get("override") if isinstance(kanit.get("override"), dict) else {}
    for sk, v in ov.items():
        satir.append(f"{_ad_goster(sk)}: çıkış yöntemi {ALT_AD.get((v or {}).get('alternatif'), 'başka bir yöntem')} oldu")
    yasak = kanit.get("yasak") if isinstance(kanit.get("yasak"), list) else []
    for y in yasak:
        if isinstance(y, (list, tuple)) and len(y) >= 2:
            satir.append(f"{_ad_goster(str(y[0]))}: {ALT_AD.get(y[1], 'bir çıkış yöntemi')} geri alındı")
    gv = veri.get("alinsaydi_gevsetme")
    if isinstance(gv, dict) and any(k in gv for k in ("aktif", "askida", "kara_liste")):      # alinsaydi_gevsetme.json durumu: okunur satırlar (kimlik özetleri gösterilmez)
        from motor.canli.alinsaydi_gevsetme import gorunur_ad
        for neden, v in sorted((gv.get("aktif") or {}).items()) if isinstance(gv.get("aktif"), dict) else []:
            kn = (v or {}).get("kanit") or {} if isinstance(v, dict) else {}
            parca = [f"«{gorunur_ad(str(neden))}» filtresi gevşetildi"]
            if kn.get("cozulen") is not None:
                parca.append(f"{int(kn['cozulen'])} sinyal")
            if kn.get("toplam_r") is not None:
                parca.append(_r_metni(kn["toplam_r"]))
            satir.append(" · ".join(parca))
        for neden in gv.get("kara_liste") if isinstance(gv.get("kara_liste"), list) else []:
            satir.append(f"«{gorunur_ad(str(neden))}» filtresi geri alındı, tekrar gevşetilmeyecek")
        for neden in sorted(gv.get("askida") or {}) if isinstance(gv.get("askida"), dict) else []:
            satir.append(f"«{gorunur_ad(str(neden))}» filtresi askıda")
        gv = None
    kayitlar = gv if isinstance(gv, list) else ([{**(v if isinstance(v, dict) else {"metin": str(v)}), "hesap": k} for k, v in gv.items()] if isinstance(gv, dict) else [])
    for k in kayitlar:
        if isinstance(k, dict):
            metin = k.get("metin") or k.get("aciklama") or k.get("degisiklik") or k.get("ne")
            if metin:
                satir.append((f"{_ad_goster(str(k['hesap']))}: " if k.get("hesap") else "") + str(metin))
        elif isinstance(k, str):
            satir.append(k)
    dr = (((veri.get("kurulumlar") or {}).get("ana_ogrenme") or {}).get("durum") or {}).get("drift")
    if isinstance(dr, dict) and dr:
        satir += [f"Sapma: {_ad_goster(str(k))} {v if isinstance(v, str) else ''}".strip() for k, v in dr.items()]
    elif isinstance(dr, list) and dr:
        satir += [f"Sapma: {_ad_goster(str(k))}" for k in dr]
    elif isinstance(dr, str) and dr:
        satir.append(f"Sapma: {dr}")
    return _p("Otomatik değişiklikler", "".join(f'<div class="is">{esc(s_)}</div>' for s_ in satir) if satir else _sat("Durum", "Henüz değişiklik yok"))


# ---- sekmeler
@_guvenli
def _sekme_ozet(veri: dict, sorunlar: list, simdi: datetime) -> str:
    oz = veri.get("ozet")
    if not oz:
        return _p("Özet", _bos())
    acik, kapanan = _acik_liste(veri), _kapanan_liste(veri)
    sinif, metin = ne_yapmali(veri, sorunlar, simdi)
    kart1 = _p("Ne yapmalıyım?", f'<div class="yapm {sinif}">{esc(metin)}</div>')
    if acik:
        sirali = sorted(acik, key=lambda p: _dec(p.get("kz")) or Decimal(0))
        en_kotu, en_iyi = sirali[0], sirali[-1]
        t = _topla(p.get("kz") for p in acik)
        g2 = (_sat("Açık işlem", str(len(acik))) + _sat("Toplam K/Z", _usd(t, True), _isaret_sinifi(t))
              + _sat("En iyi", f"{ha.coin_adi(en_iyi['sembol'])} {_usd(en_iyi.get('kz'), True)}", _isaret_sinifi(en_iyi.get("kz")))
              + _sat("En kötü", f"{ha.coin_adi(en_kotu['sembol'])} {_usd(en_kotu.get('kz'), True)}", _isaret_sinifi(en_kotu.get("kz"))))
    else:
        g2 = _sat("Açık işlem", "0")
    kart2 = _p("Açık işlemler", g2 + '<div class="alt bag"><label class="lnk" for="t2">tümü →</label></div>')
    son3 = "".join(_sat(f"{_kisa_saat(x['zaman'])} · {ha.coin_adi(x['sembol'])} {x['yon']}", _usd(x["net_pnl_yerel"], True), _isaret_sinifi(x["net_pnl_yerel"])) for x in kapanan[:3])
    kart3 = _p("Son kapanan işlemler", (son3 or _sat("Durum", "Henüz kapanan işlem yok")) + '<div class="alt bag"><label class="lnk" for="t3">tümü →</label></div>')
    kr, ek, a_sonuc = veri.get("kurulumlar"), veri.get("ogrenme_ek") or {}, veri.get("alinmayan_sonuc")
    kart4, kart5 = _ders_karti(ders_ozeti(kr, ek, a_sonuc, simdi), r_usd=_r_usd(veri)), _ml_karti(ml_ozeti(kr, ek, a_sonuc, simdi), r_usd=_r_usd(veri))
    kirmizi, isik = _durum_isigi(veri, sorunlar, simdi)
    kartlar = [kart1, kart2, kart3, kart4, kart5]
    kartlar.insert(0 if kirmizi else len(kartlar), _p("Durum", isik + _uyari_listesi(veri, sorunlar, simdi)))
    return _ig("".join(kartlar))


@_guvenli
def _sekme_acik(veri: dict, simdi: datetime) -> str:
    acik = _acik_liste(veri)
    if not acik:
        return _p("Açık işlemler", _sat("Açık işlem", "0"))
    t = _topla(p.get("kz") for p in acik)
    ust = _sat(f"{len(acik)} açık işlem · toplam K/Z", _usd(t, True), _isaret_sinifi(t))
    return _p("Açık işlemler", ust + _liste_kutusu([_acik_satiri(p, simdi) for p in acik], ("Sembol", "Giriş → şimdi", "K/Z", "Süre")))


@_guvenli
def _sekme_kapanan(veri: dict, simdi: datetime) -> str:
    kap = _kapanan_liste(veri)[:ISLEM_GOSTER]
    if not kap:
        return _p("Kapanan işlemler", _bos("Henüz kapanan işlem yok"))
    kaz = len([x for x in kap if (_dec(x["net_pnl_yerel"]) or 0) > 0])
    net = _topla(x["net_pnl_yerel"] for x in kap)
    don = ('<div class="don" id="don"><button type="button" data-don="gun">Bugün</button><button type="button" data-don="7">7g</button>'
           '<button type="button" data-don="30">30g</button><button type="button" data-don="" class="on">Tümü</button></div>')
    ozet = (f'<div class="kozet"><span><b id="k-n">{len(kap)}</b> işlem</span><span>kazanan <b id="k-w">%{kaz * 100 // len(kap)}</b></span>'
            f'<span>net <b id="k-net" class="{_isaret_sinifi(net)}">{esc(_usd(net, True))}</b></span></div>')
    return _p("Kapanan işlemler", don + ozet + _liste_kutusu([_kapanan_satiri(x) for x in kap], ("Sembol", "Kapanış", "K/Z", "Neden"), "kapanan"))


def _donem_getirisi(gc: Optional[dict], gun: int, simdi_e) -> tuple:
    n = (gc or {}).get("noktalar") or []
    e0 = _dec(n[-1 - gun]["ozsermaye"]) if len(n) > gun else None
    if e0 is None or e0 == 0 or _dec(simdi_e) is None:
        return None, None
    fark = _dec(simdi_e) - e0
    return fark, float(fark / e0)


@_guvenli
def _sekme_kz(veri: dict) -> str:
    oz, gc = veri.get("ozet"), veri.get("gecmis")
    if not oz:
        return _p("K/Z", _bos())
    parcalar = []
    if gc and len(gc.get("noktalar") or []) >= 2:
        parcalar.append(_p("Kasa eğrisi (30 gün)", _egri({**gc, "noktalar": gc["noktalar"][-30:]}, None)))
    bas = oz.get("baslangictan_pnl", oz["toplam_pnl"])
    satir = [("Bugün", _dec(oz["gun_pnl"]), oz["gun_getiri"])]
    for ad_, gun in (("7 gün", 7), ("30 gün", 30)):
        f, o = _donem_getirisi(gc, gun, oz["ozsermaye"])
        satir.append((ad_, f, o))
    satir.append(("Toplam", _dec(bas), oz["toplam_getiri"]))
    parcalar.append(_p("Kâr / zarar", '<div class="izgara c4">' + "".join(
        _kutu(ad_, _usd(f, True) if f is not None else "—", _isaret_sinifi(f) if f is not None else "", f_yuzde(o, True) if o is not None else "geçmiş yetersiz") for ad_, f, o in satir) + "</div>"))
    kap = _kapanan_liste(veri)
    if kap:
        kaz = [_dec(x["net_pnl_yerel"]) for x in kap if (_dec(x["net_pnl_yerel"]) or 0) > 0]
        kay = [_dec(x["net_pnl_yerel"]) for x in kap if (_dec(x["net_pnl_yerel"]) or 0) < 0]
        ort_k = _topla(kaz) / len(kaz) if kaz else None
        ort_z = _topla(kay) / len(kay) if kay else None
        parcalar.append(_p("İşlem kalitesi", _sat("Kazanma oranı", f"%{len(kaz) * 100 // len(kap)} ({len(kap)} işlem)")
                           + _sat("Ortalama kazanç", _usd(ort_k, True) if ort_k is not None else "—", "iyi" if ort_k else "")
                           + _sat("Ortalama kayıp", _usd(ort_z, True) if ort_z is not None else "—", "kotu" if ort_z else "")))
    st = veri.get("stratejiler")
    if st:
        toplu: dict = {}
        diger_n, diger_t = 0, Decimal(0)
        gizli = _gizli_adlar()
        for x in st["stratejiler"]:
            if x["kimlik"].split("|")[0] in gizli:
                diger_n += 1
                diger_t += _dec(x["ozsermaye_katkisi"]) or Decimal(0)
            else:
                ad_ = _ad_goster(x["kimlik"])
                toplu[ad_] = toplu.get(ad_, Decimal(0)) + (_dec(x["ozsermaye_katkisi"]) or Decimal(0))
        satirlar = [_sat(a_, _usd(v, True), _isaret_sinifi(v)) for a_, v in sorted(toplu.items(), key=lambda kv: kv[1], reverse=True)]
        if diger_n:
            satirlar.append(_sat(f"{DIGER_TOPLU} ({diger_n})", _usd(diger_t, True), _isaret_sinifi(diger_t)))
        ct = (veri.get("kurulumlar") or {}).get("ct")
        if ct and ct.get("toplam_pnl") is not None:
            satirlar.append(_sat(KONSENSUS_AD, _usd(ct["toplam_pnl"], True), _isaret_sinifi(ct["toplam_pnl"])))
        parcalar.append(_p("Kaynağa göre K/Z", "".join(satirlar) or _bos()))
    ml = veri.get("maliyet")
    if ml and isinstance(ml.get("toplam"), dict) and ml["toplam"].get("tum"):
        t = ml["toplam"]["tum"]
        parcalar.append(_p("Masraflar", _sat("Komisyon", _usd(t["ucret"])) + _sat("Funding", _usd(t["funding"], True)) + _sat("Kayma (varsayılan)", _usd(t["kayma"])) + _sat("Toplam", _usd(t["toplam"]))))
    return _ig("".join(parcalar))


@_guvenli
def _sekme_ogrenme(veri: dict, simdi: datetime) -> str:
    kr, ek, a_sonuc = veri.get("kurulumlar"), veri.get("ogrenme_ek") or {}, veri.get("alinmayan_sonuc")
    return _ig(_ders_karti(ders_ozeti(kr, ek, a_sonuc, simdi), True, _r_usd(veri)) + _ml_karti(ml_ozeti(kr, ek, a_sonuc, simdi), True, _r_usd(veri)) + _degisiklikler_karti(veri))


def _teknik_bolum(baslik: str, govde: str) -> str:
    if not govde or _bos_mu(govde):
        return ""
    return f'<details class="tk"><summary>{esc(baslik)}</summary><div class="tkg2">{govde}</div></details>'


@_guvenli
def _teknik_saglik(sg: dict) -> str:
    sv = sg["servis"]
    motor = ('<div class="izgara oto">' + _kutu("Durum", "sağlıklı" if sg["durum"] == "ok" else sg["durum"], "iyi" if sg["durum"] == "ok" else "kotu")
             + _kutu("Son çalışma", tsi(sg["son_calisma"]))
             + _kutu("Servis", {True: "çalışıyor", False: "ÇALIŞMIYOR", None: "yok (backtest)"}[sv["calisiyor"]], "kotu" if sv["calisiyor"] is False else "")
             + _kalp_atisi_kutulari(sg) + "</div>")
    akis = ('<div class="izgara oto">' + "".join(_kutu(f"{ha.coin_adi(v['sembol'])} {v['tf']} son mum", tsi(v["son_mum_zamani"]), "kotu" if v["bayat"] else "",
                                                     f"{v['bayatlik_dk']} dk" + (" · BAYAT" if v["bayat"] else "")) for v in sg["veri"]) + "</div>") if sg["veri"] else ""
    ed = sg.get("evren_disi") or []
    evren = _tablo(["Sembol", "Durum"], [[f"<b>{esc(ha.coin_adi(x['sembol']))}</b>", esc("beklenen, kalıcı" if x["beklenen"] else "BEKLENMEYEN")] for x in ed], sinif="kay") if ed else ""
    return motor + akis + evren


def _teknik_model(veri: dict, simdi: datetime) -> str:
    kr = veri.get("kurulumlar")
    kartlar = (_ogrenme_karti(kr, simdi), _alinmayan_karti(kr, veri.get("alinmayan_sonuc")), _cikis_karti(veri.get("cikis_kanit"), kr))
    return "".join(k for k in kartlar if not _bos_mu(k))


@_guvenli
def _sekme_teknik(veri: dict, sorunlar: list, simdi: datetime) -> str:
    oz, st, sg = veri.get("ozet"), veri.get("stratejiler"), veri.get("saglik")
    guv = _veri_guveni_html(veri["veri_guveni"]) if veri.get("veri_guveni") is not None else ""
    kalite = guv + "".join(h for h in (_karantina_karti(sg), _disk_karti(veri.get("disk")), _sembol_karti(veri.get("olaylar"))) if not _bos_mu(h))
    kayit = (_olaylar_html(veri["olaylar"]) if veri.get("olaylar") is not None else "") + (_reddedilen_son(veri["reddedilen"]) if veri.get("reddedilen") is not None else "")
    b = [_teknik_bolum("Sağlık", _teknik_saglik(sg) if sg else ""),
         _teknik_bolum("Risk limitleri", _sekme_risk(oz, veri.get("korelasyon"), veri.get("yogunlasma")) if oz else ""),
         _teknik_bolum("Kalite kapıları", kalite),
         _teknik_bolum("Model ayrıntısı", _teknik_model(veri, simdi)),
         _teknik_bolum("Aralık karnesi", _aralik_karnesi_html(st["aralik_karnesi"]) if st and st.get("aralik_karnesi") is not None else ""),
         _teknik_bolum("Kıyas", _kiyas_html(veri["kiyas"]) if veri.get("kiyas") is not None else ""),
         _teknik_bolum("Beklenti konumu", _beklenti_tablosu(st) if st else ""),
         _teknik_bolum("Etiket × sonuç", _etiket_karti(veri.get("etiket_sonuc"))),
         _teknik_bolum("Boşluk riski", _bosluk_karti(veri.get("bosluk"))),
         _teknik_bolum("Kayıtlar", kayit)]
    return '<div class="ig"><div class="p g3"><div class="pi duz">' + "".join(b) + "</div></div></div>"


def _gorunur_duzelt(t: str) -> str:
    """Görünen metin: coin tek tip (USDT eki yok), teknik '_' adı kalmaz."""
    t = re.sub(r"\bDK_", "", t)
    t = re.sub(r"\b([A-Z0-9]{2,12}?)(?:USDT|USDC)\b", r"\1", t)
    return t.replace("_", " ")


def _adsiz(m: str) -> str:
    """Kullanıcıya dosya/alan adı gösterme: '*.json(l)' adları 'veri dosyası' olur."""
    return re.sub(r"\b[\w./\-]+\.jsonl?\b", "veri dosyası", str(m))


def _gorunur_uyarilar(u: list) -> str:
    """Uyarı bantları: en fazla 2 görünür (önem sırasıyla), kalanı <details> içinde '+N uyarı'."""
    sira = {"kritik": 0, "uyari": 1, "bilgi": 2}
    u = sorted(u, key=lambda x: sira.get(x[0], 3))
    if not u:
        return ""
    sev = u[0][0]
    metin = "Dikkat gerektiren bir durum var" if len(u) == 1 else f"Dikkat gerektiren {len(u)} durum var"
    return (f'<div class="uyari {sev}" role="{"alert" if sev == "kritik" else "note"}">{metin} — ayrıntı '
            f'<label class="lnk" for="t1">DURUM kartında →</label></div>')


def html_olustur(veri: dict, sorunlar: list, simdi: datetime) -> str:
    global _GIZLI
    _GIZLI = None
    oz, sg = veri.get("ozet"), veri.get("saglik")
    mr = veri.get("maruziyet")
    u = uyarilar(veri, sorunlar, simdi)
    canli_mi = bool(oz and oz["kaynak"] != "backtest")
    g = []
    if canli_mi and oz.get("yazildi_zaman"):           # tarayıcı tarafı bayatlık bandı: JS yoksa gizli kalır (sunucu tarafı uyarılar yine geçerli)
        g.append(f'<div id="bayat" class="uyari bayat-bant" role="alert" hidden data-zaman="{esc(oz["yazildi_zaman"])}" data-esik-dk="{BAYATLIK_ESIK_DK}">'
                 'VERİ BAYAT: son güncelleme <span id="bayat-dk">?</span> dk önce, sistem durmuş olabilir</div>')
    g.append('<header class="ust"><div class="mk"><span class="lg0">1L</span><h1>1L3A PANO</h1></div><div class="un">'
             + (f'<span class="rozet r-{esc(oz["kaynak"])}">{esc(KAYNAK_ADI[oz["kaynak"]])}</span>' if oz else "")
             + '<button id="yenile" type="button" title="Sayfayı yeniden yükle">Yenile</button><button id="tema" type="button">Tema</button></div></header>')
    g.append(_gorunur_uyarilar(u))
    if not oz:
        g.append(f'<div class="uyari kritik">Hesap bilgisi için {HENUZ_YOK.lower()}; değer uydurulmaz.</div>')
    else:
        g.append(_serit(oz, mr, veri, simdi))
    bugun = _tsi_makine(simdi)[:10]
    rozet = {"t2": str(len(_acik_liste(veri))) if oz else None,
             "t3": str(len([x for x in _kapanan_liste(veri) if _tsi_makine(x["zaman"])[:10] == bugun])) if oz else None}
    g.append('<div class="sekme-kok">')
    g.append("".join(f'<input type="radio" name="t" id="{i}"' + (" checked" if i == "t1" else "") + ' aria-label="' + esc(ad) + '">' for i, ad in SEKMELER))
    g.append('<div class="tabs" role="tablist">' + "".join(
        f'<label for="{i}">{esc(ad)}' + (f' <em>{esc(rozet[i])}</em>' if rozet.get(i) is not None else "")
        + "</label>" for i, ad in SEKMELER) + "</div>")
    icerik = (_sekme_ozet(veri, sorunlar, simdi), _sekme_acik(veri, simdi), _sekme_kapanan(veri, simdi), _sekme_kz(veri), _sekme_ogrenme(veri, simdi),
              _sekme_teknik(veri, sorunlar, simdi))
    g.append('<div class="sekmeler">' + "".join(f'<section class="n{i[1:]}">{c}</section>' for (i, _), c in zip(SEKMELER, icerik)) + "</div></div>")
    govde = re.sub(r">([^<>]*)<", lambda m: ">" + _gorunur_duzelt(m.group(1)) + "<", "".join(g))
    return ('<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="dark light"><meta http-equiv="refresh" content="300"><title>1L3A pano</title>'
            '<script>try{if(window.self!==window.top)document.documentElement.className+=" ifr"}catch(e){document.documentElement.className+=" ifr"}</script>'
            '<style>' + CSS + "</style></head><body><main>" + govde + "</main><script>" + JS + "</script></body></html>")


def uret(dizin, cikti=None, simdi: Optional[datetime] = None) -> tuple:
    """Durumu okur, HTML'i atomik yazar. -> (html_yolu, terminal metni, sorunlar, uyarılar)."""
    simdi = simdi or datetime.now(timezone.utc)
    veri, sorunlar = yukle(dizin)
    yol = Path(cikti) if cikti else Path(dizin) / "pano.html"
    d.atomik_yaz_metin(yol, html_olustur(veri, sorunlar, simdi))
    return yol, terminal_ozet(veri, sorunlar, simdi), sorunlar, uyarilar(veri, sorunlar, simdi)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Durum dosyalarından statik HTML pano + terminal özeti")
    ap.add_argument("--durum", default=str(d.DURUM_DIZINI))
    ap.add_argument("--cikti", default=None, help="HTML yolu (varsayılan: <durum>/pano.html)")
    ap.add_argument("--simdi", default=None, help="test için sabit zaman (YYYY-MM-DDTHH:MM:SSZ)")
    ap.add_argument("--telegram", action="store_true", help="Telegram kısa metnini de yazdır (göndermez)")
    a = ap.parse_args(argv)
    simdi = d.zaman_oku(a.simdi) if a.simdi else None
    yol, metin, sorunlar, u = uret(a.durum, a.cikti, simdi)
    print(metin)
    print(f"\nHTML: {yol}")
    if a.telegram:
        veri, s = yukle(a.durum)
        print("\n--- Telegram metni ---\n" + telegram_metni(veri, s, simdi or datetime.now(timezone.utc)))
    return 1 if sorunlar else (2 if any(s == "kritik" for s, _ in u) else 0)


if __name__ == "__main__":
    sys.exit(main())
