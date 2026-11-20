"""Ortak günlük özet (şema `ortak.gunluk_ozet.v1`) + haftalık Telegram özeti. İKİSİ AYNI veri toplama fonksiyonunu (`topla`) kullanır.

`topla(durum_dizini, simdi)`: SAF; yalnız durum dosyalarını OKUR (hesap yapmaz, uydurmaz; ölçülemeyen alan `null`, alan atlanmaz).
`yaz(...)`: `topla` çıktısını durum dizinine `gunluk_ozet_v1.json` olarak atomik yazar ve `gunluk_ozet_gecmis.jsonl`'e günde BİR satır
ekler/günceller (haftalık özet bu tarihçeyi toplar). `paper_kancasi(...)`: paper tur döngüsünün tek çağrısı (saatlik güncelleme,
21:00 TSİ günlük özetiyle aynı anda yazım, Pazar 21:10 TSİ haftalık Telegram özeti).

1L3A kuralları: "kasa" = 10 sanal paper hesabının toplamı (ct_konsensus HARİÇ). "hesaplar": 6 GÖRÜNÜR hesap kendi kısa adıyla, 4 GİZLİ hesap
tek satır toplu ("gizli_hesaplar (4)"; kullanıcı kararı: gizli hesaplar adıyla görünmez), ct_konsensus ayrı satır. Para USD ondalık (sayı),
zaman ISO-8601 UTC. Anahtar / e-posta / hesap numarası YAZILMAZ. `hesaplar[].islem` = hesabın toplam kapanan işlem sayısı.
Gün = TSİ günü (Europe/Istanbul).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from motor.canli import etiket_sonuc
from motor.canli import hesap_adlari as hg

log = logging.getLogger("gunluk_ozet")
SEMA = "ortak.gunluk_ozet.v1"
DOSYA = "gunluk_ozet_v1.json"
GECMIS = "gunluk_ozet_gecmis.jsonl"
GECMIS_EN_COK = 400                          # tarihçede tutulan en çok gün
SAATLIK_SN = 3600
HAFTALIK_SAAT_TSI = (21, 10)                 # Pazar 21:10 TSİ
CT_VARSAYILAN = "/var/lib/1l3a-ct-paper/durum/ct_konsensus"
GIZLI_AD = hg.DIGER_HESAPLAR                # "Diğer hesaplar" (gizli hesap adı hiçbir yerde yazılmaz)
SEMA_ALANLARI = ("sema", "proje", "uretim", "gun", "mod", "kasa", "islem", "hesaplar", "ogrenme", "rejim", "drift_uyari", "limitler", "saglik", "notlar", "bosluk_riski")


# ----------------------------------------------------------------------------------------------- okuma yardımcıları
def _json(yol: Path):
    try:
        return json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _jsonl(yol: Path) -> list:
    out: list = []
    try:
        with open(yol, encoding="utf-8") as f:
            for s in f:
                s = s.strip()
                if not s:
                    continue
                try:
                    v = json.loads(s)
                except ValueError:
                    continue
                if isinstance(v, dict):
                    out.append(v)
    except OSError:
        return []
    return out


def _dec(x) -> Optional[Decimal]:
    try:
        return None if x is None else Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def _usd(x) -> Optional[float]:
    v = _dec(x)
    return None if v is None else float(round(v, 2))


def _tsi_gun(t) -> Optional[str]:
    from motor.canli import durum_ek as ek
    try:
        return ek.tsi_gun(t)
    except Exception:  # noqa: BLE001
        return None


def _iso(t) -> str:
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def kisa_ad(kimlik: str) -> str:
    """Görünür hesabın kısa adı (pano ve Telegram aynı fonksiyon: motor/canli/hesap_adlari.py)."""
    return hg.hesap_adi(kimlik)          # Telegram/özet/pano: okunur ad (hg.kisa_ad yalnız iç kullanım)


def diger_hesaplar(durum_dizini) -> Optional[tuple]:
    """Günlük özet dosyasından ("Diğer hesaplar (N)") -> (N, toplam K/Z Decimal) ya da None. Yalnız okur; gizli ad yok."""
    o = _json(Path(durum_dizini) / DOSYA)
    if not isinstance(o, dict):
        return None
    for h in o.get("hesaplar") or []:
        ad = str(h.get("ad", ""))
        if ad.startswith(GIZLI_AD + " ("):
            try:
                return int(ad[len(GIZLI_AD) + 2:].rstrip(")")), _dec(h.get("toplam_pnl"))
            except ValueError:
                return None
    return None


# ----------------------------------------------------------------------------------------------- hesap okuma
def _hesap_oku(dizin: Path, gun: str) -> Optional[dict]:
    """Bir hesabın durum dizininden (ozet.json, islemler.jsonl, stratejiler.json) sayılar; ozet.json yoksa None."""
    oz = _json(Path(dizin) / "ozet.json")
    if not isinstance(oz, dict):
        return None
    sayac = oz.get("sayaclar") or {}
    islemler = _jsonl(Path(dizin) / "islemler.jsonl")
    kapanan = [x for x in islemler if _tsi_gun(x.get("cikis_zamani") or x.get("zaman")) == gun]
    acilan = sum(1 for x in islemler if _tsi_gun(x.get("giris_zamani")) == gun)          # kapanmış (aynı gün açılıp kapanan dahil) + aşağıda açıklar
    st = _json(Path(dizin) / "stratejiler.json") or {}
    acik_liste = [a for s in (st.get("stratejiler") or []) for a in (s.get("acik_pozisyonlar") or []) if isinstance(a, dict)]
    acilan += sum(1 for a in acik_liste if _tsi_gun(a.get("giris_zamani")) == gun)
    kz = [_dec(x.get("net_pnl_yerel")) for x in kapanan]
    gecmis = _json(Path(dizin) / "ozsermaye_gecmisi.json") or {}
    return {"ozsermaye": _dec(oz.get("ozsermaye")), "baslangic": _dec(oz.get("baslangic_ozsermaye")), "gun_pnl": _dec(oz.get("gun_pnl")),
            "toplam_pnl": _dec(oz.get("toplam_pnl")), "zirve": _dec(oz.get("zirve_ozsermaye")),
            "islem_toplam": sayac.get("kapanan_islem"), "acik": sayac.get("acik_pozisyon", len(acik_liste)),
            "gun_acilan": acilan, "gun_kapanan": len(kapanan),
            "kazanan": sum(1 for v in kz if v is not None and v > 0), "kaybeden": sum(1 for v in kz if v is not None and v < 0),
            "seri": {n.get("gun"): _dec(n.get("ozsermaye")) for n in (gecmis.get("noktalar") or []) if isinstance(n, dict)}}


def _topla_hesaplar(rows: list):
    """Hesap satırlarının toplamı (None'ları atlar; hiç değer yoksa None)."""
    def t(alan):
        v = [r[alan] for r in rows if r.get(alan) is not None]
        return sum(v, Decimal(0)) if v else None
    return t


def _satir(ad: str, rows: list) -> dict:
    t = _topla_hesaplar(rows)
    isl = [r["islem_toplam"] for r in rows if isinstance(r.get("islem_toplam"), int)]
    return {"ad": ad, "gun_pnl": _usd(t("gun_pnl")), "toplam_pnl": _usd(t("toplam_pnl")), "islem": sum(isl) if isl else None}


def _set_kayitlari(set_yolu: Optional[Path]) -> Optional[list]:
    from motor.canli import paper_v2 as v2
    s = _json(set_yolu or v2.SET_YOLU)
    if not isinstance(s, dict) or not isinstance(s.get("stratejiler"), list):
        return None
    return [(v2.hesap_adi(k), v2.hesap_dizin_adi(v2.hesap_adi(k)), v2.gorunur_mu(k)) for k in s["stratejiler"]]


def _kasa_dusus(rows: list, simdi_toplam: Optional[Decimal], baslangic_toplam: Optional[Decimal]) -> Optional[float]:
    """Zirveden düşüş (yüzde, pozitif). Zirve: hesapların günlük özsermaye serilerinin gün gün toplamının en yükseği (seri yoksa hesap zirvelerinin toplamı)."""
    if simdi_toplam is None:
        return None
    gunler = None
    for r in rows:
        k = {g for g, v in r["seri"].items() if v is not None}
        gunler = k if gunler is None else gunler & k
    zirve = max([sum((r["seri"][g] for r in rows), Decimal(0)) for g in (gunler or ())] + [simdi_toplam] + ([baslangic_toplam] if baslangic_toplam else []))
    if not gunler:
        z = [r["zirve"] for r in rows]
        if all(v is not None for v in z):
            zirve = max(sum(z, Decimal(0)), simdi_toplam)
    return float(round((zirve - simdi_toplam) / zirve * 100, 2)) if zirve > 0 else None


# ----------------------------------------------------------------------------------------------- topla
def topla(durum_dizini, simdi, ct_dizin=None, set_yolu=None, env=None) -> dict:
    """Ortak günlük özet sözlüğü (şema `ortak.gunluk_ozet.v1`). Saf: yalnız `durum_dizini` (ve ct dizini) dosyalarını okur."""
    from motor.canli import kalp_atisi
    from motor.canli import paper as pp
    from motor.canli.borsa.canli_limitler import CANLI_LIMITLER
    from motor.canli.paper_v2 import SORUN_OLAY_TURLERI
    from motor.risk.limitler import SERT_LIMITLER
    env = os.environ if env is None else env
    dizin = Path(durum_dizini)
    simdi = pd.Timestamp(simdi)
    gun = _tsi_gun(simdi)
    notlar: list = []

    # --- hesaplar ve kasa
    kayitlar = _set_kayitlari(set_yolu)
    gorunur_rows, gizli_rows, gorunur_ad = [], [], []
    gizli_adet = 0
    if kayitlar is not None:
        for kimlik, klasor, gorunur in kayitlar:
            r = _hesap_oku(dizin / "hesaplar" / klasor, gun)
            if not gorunur:
                gizli_adet += 1
            if r is None:
                continue
            (gorunur_rows if gorunur else gizli_rows).append(r)
            if gorunur:
                r["ad"] = kisa_ad(kimlik)
    tum = gorunur_rows + gizli_rows
    if not tum:                                              # hesap klasörleri yok (eski/tek hesaplı durum): üst düzey özet
        ust = _hesap_oku(dizin, gun)
        tum = [ust] if ust else []
        gorunur_rows, gizli_rows, gizli_adet = [], [], 0
        if ust:
            notlar.append("hesap klasörleri yok: kasa üst düzey özetten")
    t = _topla_hesaplar(tum)
    kasa = {"baslangic": _usd(t("baslangic")), "simdi": _usd(t("ozsermaye")), "gun_pnl": _usd(t("gun_pnl")), "toplam_pnl": _usd(t("toplam_pnl")),
            "zirveden_dusus_yuzde": _kasa_dusus(tum, t("ozsermaye"), t("baslangic")) if tum else None}
    hesaplar = [dict(_satir(r["ad"], [r])) for r in gorunur_rows]
    if gizli_adet:
        hesaplar.append(_satir(f"{GIZLI_AD} ({gizli_adet})", gizli_rows))
    ct = Path(ct_dizin) if ct_dizin is not None else Path(env.get("L3A_CT_DURUM") or CT_VARSAYILAN)
    ct_r = _hesap_oku(ct, gun) if ct.is_dir() else None
    if ct_r:
        hesaplar.append(_satir(hg.CT_HESABI, [ct_r]))

    # --- işlem
    alinmayan = sum(1 for x in _jsonl(dizin / "alinmayan_sinyaller.jsonl") if _tsi_gun(x.get("zaman")) == gun) if (dizin / "alinmayan_sinyaller.jsonl").exists() else None
    islem = {"gun_acilan": sum(r["gun_acilan"] for r in tum) if tum else None, "gun_kapanan": sum(r["gun_kapanan"] for r in tum) if tum else None,
             "kazanan": sum(r["kazanan"] for r in tum) if tum else None, "kaybeden": sum(r["kaybeden"] for r in tum) if tum else None,
             "acik_pozisyon": sum(int(r["acik"]) for r in tum if r["acik"] is not None) if tum else None, "alinmayan_sinyal": alinmayan}

    # --- öğrenme (ogrenme_adaptor.py durum dosyaları)
    from motor.canli import ogrenme_adaptor as oa
    ders = _json(dizin / oa.DERS_DOSYASI)
    odurum = _json(dizin / oa.DURUM_DOSYASI)
    modeller = dizin / oa.MODEL_DIZINI
    ders_d = {k: v for k, v in ders.items() if isinstance(v, dict)} if isinstance(ders, dict) else None
    ogrenme = {"aktif_ders": None if ders_d is None else sum(1 for v in ders_d.values() if v.get("status") in ("candidate", "alive")),
               "yeni_ders": None if ders_d is None else sum(1 for v in ders_d.values() if v.get("born") == gun),
               "emekli_ders": None if ders_d is None else sum(1 for v in ders_d.values() if v.get("status") == "retired"),
               "filtre_aktif": (any(modeller.glob("*.json")) if modeller.is_dir() else (False if odurum is not None else None))}
    drift = bool(odurum.get("drift_uyari")) if isinstance(odurum, dict) else False

    # --- rejim (ML rejim, BTC 1d etiketi; kayit_etiketleri okuyucusu; ortam tanımlı değilse null)
    rejim = None
    try:
        from motor.canli.kayit_etiketleri import Kayit
        r = Kayit(dizin, rejim_dosya=env.get("L3A_REJIM_DOSYA"), rejim_url=env.get("L3A_REJIM_URL"),
                 rejim_kapali=env.get("L3A_REJIM_KAPALI") == "1").rejim("BTCUSDT", simdi)
        rejim = r.get("rejim_ml_1d") if isinstance(r, dict) else None
    except Exception:  # noqa: BLE001
        log.exception("rejim okunamadı")

    # --- limitler ve sağlık
    durdu = pp.durdur_dosyasi(env).exists()
    try:
        nabiz = (kalp_atisi.oku(dizin) or {}).get("zaman")
    except Exception:  # noqa: BLE001
        nabiz = None
    olaylar = dizin / "olaylar.jsonl"
    hata = sum(1 for e in _jsonl(olaylar) if e.get("tur") in SORUN_OLAY_TURLERI and _tsi_gun(e.get("zaman")) == gun) if olaylar.exists() else None
    if durdu:
        notlar.append("yeni girişler durduruldu (DURDUR bayrağı)")
    if drift:
        notlar.append("öğrenme: drift uyarısı var")
    if kasa["gun_pnl"] is not None and kasa["baslangic"]:
        notlar.append(f"gün K/Z {kasa['gun_pnl']:+.2f} USD")
    asn = _json(dizin / "alinmayan_sonuc.json")                    # gece "alınsaydı" özeti (cikis_karsi_olgu.py); yoksa not yok
    if isinstance(asn, dict) and asn.get("ozet_satiri"):
        notlar.append(str(asn["ozet_satiri"]))
    return {"sema": SEMA, "proje": "1L3A", "uretim": _iso(simdi), "gun": gun, "mod": "kagit", "kasa": kasa, "islem": islem, "hesaplar": hesaplar,
            "ogrenme": ogrenme, "rejim": rejim, "drift_uyari": drift,
            "limitler": {"gunluk_kayip_yuzde": SERT_LIMITLER.gunluk_max_kayip_yuzde, "kaldirac_tavan": max(CANLI_LIMITLER.izinli_kaldiraclar), "durdu_mu": durdu},
            "saglik": {"son_nabiz": nabiz, "hata_sayisi_gun": hata}, "notlar": notlar[:5], "bosluk_riski": _bosluk(dizin)}


def gunluk_metin(o: dict) -> str:
    """Telegram /rapor metni (düz metin, ≤3500 karakter) ve `topla` çıktısından; hesap adları yalnız görünür hesaplar + "gizli_hesaplar (N)" + ct_konsensus."""
    from motor.canli import telegram as tg
    def sayi(x):
        return "—" if x is None else str(int(x))
    k, i, og = o.get("kasa") or {}, o.get("islem") or {}, o.get("ogrenme") or {}
    filtre = {True: "aktif", False: "pasif", None: "—"}[og.get("filtre_aktif")]
    s = [f"Günlük rapor · {o.get('gun')}",
         f"Kasa: {tg.usd(k.get('simdi'))} · bugün {tg.usd(k.get('gun_pnl'), True)} · toplam {tg.usd(k.get('toplam_pnl'), True)}"
         + (f" · zirveden düşüş %{k['zirveden_dusus_yuzde']:.2f}" if k.get("zirveden_dusus_yuzde") is not None else ""),
         f"İşlem: açılan {sayi(i.get('gun_acilan'))} · kapanan {sayi(i.get('gun_kapanan'))} (kazanan {sayi(i.get('kazanan'))}, kaybeden {sayi(i.get('kaybeden'))}) · "
         f"açık pozisyon {sayi(i.get('acik_pozisyon'))} · alınmayan sinyal {sayi(i.get('alinmayan_sinyal'))}"]
    for h in o.get("hesaplar") or []:
        s.append(f"• {h.get('ad')}: bugün {tg.usd(h.get('gun_pnl'), True)} · toplam {tg.usd(h.get('toplam_pnl'), True)} · işlem {sayi(h.get('islem'))}")
    s.append(f"Öğrenme: aktif ders {sayi(og.get('aktif_ders'))}, emekli {sayi(og.get('emekli_ders'))} · filtre {filtre} · drift {'UYARI' if o.get('drift_uyari') else 'yok'}")
    lim = o.get("limitler") or {}
    s.append(f"Yeni giriş: {'DURDURULDU' if lim.get('durdu_mu') else 'açık'}")
    for n in o.get("notlar") or []:
        s.append(f"Not: {n}")
    return tg.kirp("\n".join(s))


# ----------------------------------------------------------------------------------------------- yaz
def _atomik(yol: Path, metin: str) -> None:
    from motor.canli.durum import atomik_yaz_metin
    atomik_yaz_metin(yol, metin)


def yaz(durum_dizini, simdi, ct_dizin=None, set_yolu=None, env=None) -> dict:
    """`topla` -> durum dizinine `gunluk_ozet_v1.json` (atomik) + tarihçeye (`gunluk_ozet_gecmis.jsonl`) o günün satırı (günde bir satır:
    aynı gün yeniden yazılınca satır güncellenir). -> yazılan sözlük."""
    dizin = Path(durum_dizini)
    o = topla(dizin, simdi, ct_dizin=ct_dizin, set_yolu=set_yolu, env=env)
    _atomik(dizin / DOSYA, json.dumps(o, ensure_ascii=False, indent=1, allow_nan=False) + "\n")
    eski = [x for x in _jsonl(dizin / GECMIS) if x.get("gun") != o["gun"]]
    satirlar = (eski + [o])[-GECMIS_EN_COK:]
    _atomik(dizin / GECMIS, "".join(json.dumps(x, ensure_ascii=False, allow_nan=False) + "\n" for x in satirlar))
    return o


def gecmis_oku(durum_dizini) -> list:
    return sorted(_jsonl(Path(durum_dizini) / GECMIS), key=lambda x: str(x.get("gun")))


# ----------------------------------------------------------------------------------------------- haftalık özet
def haftalik_ozet(satirlar: list, gun: str) -> dict:
    """`gun` (TSİ) dahil son 7 günün tarihçe satırlarından haftalık toplam (aynı `topla` çıktısı). Gizli hesaplar tek satır kalır ve en iyi/en kötü seçimine girmez."""
    bas = str((pd.Timestamp(gun) - pd.Timedelta(days=6)).date())
    hafta = [x for x in satirlar if bas <= str(x.get("gun")) <= gun]

    def topla_alan(f):
        v = [f(x) for x in hafta]
        v = [a for a in v if a is not None]
        return round(sum(v), 2) if v else None
    hes: dict = {}
    for x in hafta:
        for h in x.get("hesaplar") or []:
            if h.get("gun_pnl") is not None and not str(h.get("ad")).startswith((GIZLI_AD, hg.CT_HESABI)):
                hes[h["ad"]] = round(hes.get(h["ad"], 0.0) + h["gun_pnl"], 2)
    son = hafta[-1] if hafta else {}
    return {"gun_sayisi": len(hafta), "kz": topla_alan(lambda x: (x.get("kasa") or {}).get("gun_pnl")),
            "acilan": topla_alan(lambda x: (x.get("islem") or {}).get("gun_acilan")), "kapanan": topla_alan(lambda x: (x.get("islem") or {}).get("gun_kapanan")),
            "kazanan": topla_alan(lambda x: (x.get("islem") or {}).get("kazanan")), "kaybeden": topla_alan(lambda x: (x.get("islem") or {}).get("kaybeden")),
            "alinmayan": topla_alan(lambda x: (x.get("islem") or {}).get("alinmayan_sinyal")),
            "en_iyi": max(hes.items(), key=lambda kv: kv[1]) if hes else None, "en_kotu": min(hes.items(), key=lambda kv: kv[1]) if hes else None,
            "kasa": (son.get("kasa") or {}).get("simdi"), "ogrenme": son.get("ogrenme") or {}, "drift_uyari": any(bool(x.get("drift_uyari")) for x in hafta)}


def haftalik_metin(h: dict, etiket: Optional[str] = None) -> str:
    """Telegram metni ("[1L3A] ..." sessiz, en çok 12 satır). Hesap adları yalnız görünür hesaplardır; gizli hesaplar adıyla yazılmaz.
    `etiket`: etiket × sonuç kartının tek satırı (etiket_sonuc.haftalik_satir); yoksa satır eklenmez."""
    from motor.canli import telegram as tg
    def sayi(x):
        return "—" if x is None else str(int(x))
    og = h.get("ogrenme") or {}
    filtre = {True: "aktif", False: "pasif", None: "—"}[og.get("filtre_aktif")]
    s = [f"{tg.ust('INFO')} 📆 <b>Haftalık özet</b> ({h['gun_sayisi']} gün)",
         f"💰 Haftalık K/Z: <b>{tg.usd(h['kz'], True)}</b>" + (f" · kasa {tg.usd(h['kasa'])}" if h.get("kasa") is not None else ""),
         f"🔁 İşlem: {sayi(h['kapanan'])} kapanan ({sayi(h['acilan'])} açılan) · kazanan {sayi(h['kazanan'])} · kaybeden {sayi(h['kaybeden'])}"]
    if h.get("en_iyi"):
        s.append(f"🏆 En iyi hesap: {tg.e(h['en_iyi'][0])} {tg.usd(h['en_iyi'][1], True)}")
        s.append(f"📉 En kötü hesap: {tg.e(h['en_kotu'][0])} {tg.usd(h['en_kotu'][1], True)}")
    s.append(f"🚫 Alınmayan sinyal: {sayi(h['alinmayan'])}")
    s.append(f"🧠 Ders: aktif {sayi(og.get('aktif_ders'))}, emekli {sayi(og.get('emekli_ders'))} · filtre: {filtre} · drift: {'UYARI' if h.get('drift_uyari') else 'yok'}")
    if etiket:
        s.append(etiket)
    return tg.kirp("\n".join(s))


# ----------------------------------------------------------------------------------------------- paper kancası
def haftalik_zamani(son_haftalik: Optional[str], simdi) -> bool:
    """Pazar (TSİ) saat >= 21:10 ve bu hafta sonu (bugünün TSİ günü) henüz gönderilmedi."""
    from motor.canli import durum_ek as ek
    yer = pd.Timestamp(simdi).tz_convert(ek.TSI)
    return yer.weekday() == 6 and (yer.hour, yer.minute) >= HAFTALIK_SAAT_TSI and son_haftalik != str(yer.date())


def _taze_mi(durum_dizini: Path, simdi) -> bool:
    o = _json(Path(durum_dizini) / DOSYA)
    try:
        return isinstance(o, dict) and (pd.Timestamp(simdi) - pd.Timestamp(o["uretim"])).total_seconds() < SAATLIK_SN
    except Exception:  # noqa: BLE001
        return False


def _bosluk(dizin) -> Optional[dict]:
    try:
        from motor.canli import bosluk_maruziyet
        return bosluk_maruziyet.ozet_alani(dizin)
    except Exception:  # noqa: BLE001
        return None


def _onceki_gunu_kapat(durum_dizini, simdi, ct_dizin=None, set_yolu=None, env=None) -> None:
    """TSİ gün sınırı geçildiyse (son yazılan özet önceki günün): önceki günün satırı, günün son dakikasındaki durumla SON KEZ yazılır
    (saatlik yazım 23:00 sonrası durabildiği için günün son saati tarihçeden kaybolmasın). Hata yutulur."""
    try:
        o = _json(Path(durum_dizini) / DOSYA)
        gun = _tsi_gun(simdi)
        if not isinstance(o, dict) or not o.get("gun") or not gun or str(o["gun"]) >= gun:
            return
        from motor.canli import durum_ek as ek
        sinir = pd.Timestamp(gun, tz=ek.TSI)                 # yeni günün TSİ 00:00'ı
        yaz(durum_dizini, sinir - pd.Timedelta(minutes=1), ct_dizin=ct_dizin, set_yolu=set_yolu, env=env)
    except Exception:  # noqa: BLE001
        log.exception("önceki günün son özeti yazılamadı")


def paper_kancasi(p, durum_dizini, simdi, gunluk_zamani: bool, gonder: Callable[[str], bool], ct_dizin=None, set_yolu=None, env=None) -> bool:
    """Paper tur döngüsünün tek çağrısı. Yazım: günlük özet anında (`gunluk_zamani`), haftalık özet anında ya da dosya 1 saatten eskiyse.
    Pazar 21:10 TSİ'den sonra haftalık Telegram özeti BİR kez (`p.son_haftalik`; çağıran `p.kaydet()` eder). Hata paper'ı durdurmaz. -> haftalık gönderildi mi."""
    gonderildi = False
    try:
        hafta = haftalik_zamani(getattr(p, "son_haftalik", None), simdi)
        if gunluk_zamani or hafta or not _taze_mi(Path(durum_dizini), simdi):
            _onceki_gunu_kapat(durum_dizini, simdi, ct_dizin, set_yolu, env)
            o = yaz(durum_dizini, simdi, ct_dizin=ct_dizin, set_yolu=set_yolu, env=env)
            e = etiket_sonuc.yaz(durum_dizini, simdi, set_yolu=set_yolu)      # etiket × sonuç kartı (yalnız okur; hata yutulur)
            if hafta:
                gonder(haftalik_metin(haftalik_ozet(gecmis_oku(durum_dizini), o["gun"]), etiket=etiket_sonuc.haftalik_satir(e)))
                p.son_haftalik = o["gun"]                  # gönderim başarısız olsa da işaretlenir (sel olmasın)
                gonderildi = True
    except Exception:  # noqa: BLE001
        log.exception("günlük/haftalık özet başarısız (paper sürer)")
    return gonderildi
