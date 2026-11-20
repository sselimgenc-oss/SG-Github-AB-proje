"""Strateji verisi (beyin fırtınası için): kurulumdan sonra Telegram'a TEK SEFERLİK, SESSİZ, YORUMSUZ belge/mesaj.

Yalnız komut servisi çağırır (Telegram anahtarı yalnız onda; token koda girmez, `telegram.yapilandirma` ortamdan okur). Salt okunur: durum dosyalarını okur,
hiçbir şeyi değiştirmez. İçerik yalnız rakam ve etiket (öneri/değerlendirme cümlesi yok).
Kapsam: kâğıt başlangıcından beri, YALNIZ görünür hesaplar (+ CT konsensüs hesabı görünürse). Gizli hesaplar (set kaydında gorunur:false; liste
`pano._gizli_adlar`, okunamazsa hiçbir hesap görünür sayılmaz = güvenli taraf) ne okunur ne yazılır: adları ve toplamları hiçbir yerde geçmez.
Tek seferlik = kod sürümü (git sha) başına bir kez: işaret `strateji_verisi_gonderildi.json` (durum dizini). Gönderim başarısızsa ya da henüz hesap verisi
yoksa işaret konmaz (sonraki turda yeniden denenir). 4096 karakteri aşan metin sessiz .txt belge (sendDocument), aşmayan sessiz mesaj; başlık aynı.
"""
from __future__ import annotations

import json
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from motor.canli import gunluk_ozet as go
from motor.canli import hesap_adlari as ha
from motor.canli import telegram as tg

log = logging.getLogger("paper.strateji_verisi")
BASLIK = "[1L3A] Strateji verisi (beyin fırtınası için)"
BAYRAK_DOSYA = "strateji_verisi_gonderildi.json"
ARALIK_SN = 600
MESAJ_MAKS = 4096
BELGE_ADI = "strateji_verisi.txt"
TSI = ZoneInfo("Europe/Istanbul")
YOK = "veri yok"
TOPLAM_AD = "Toplam (görünür hesaplar)"
REJIM_ALANLARI = ("rejim_ml_1d", "rejim", "rejim_ml_4h")
D0 = Decimal(0)


# ------------------------------------------------------------------------------------------------ okuma
def _rejim(x: dict) -> Optional[str]:
    for a in REJIM_ALANLARI:
        v = x.get(a)
        if isinstance(v, dict):
            v = v.get("rejim")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _hesap_oku(klasor: Path, kimlik: str, ad: str, gun: str, ct: bool = False) -> Optional[dict]:
    """Bir hesabın dizininden ham sayılar; ozet.json yoksa None."""
    r = go._hesap_oku(klasor, gun)
    if r is None:
        return None
    islemler = []
    for x in go._jsonl(klasor / "islemler.jsonl"):
        net = go._dec(x.get("net_pnl_yerel"))
        if net is not None:
            islemler.append({"net": net, "yon": x.get("yon"), "rejim": _rejim(x)})
    mal = None
    m = go._json(klasor / "maliyet.json")
    t = ((m or {}).get("toplam") or {}).get("tum") if isinstance(m, dict) else None
    if isinstance(t, dict):
        v = {k: go._dec(t.get(k)) for k in ("ucret", "funding", "kayma")}
        if all(a is not None for a in v.values()):
            mal = v
    return {"kimlik": kimlik, "ad": ad, "ct": ct, "klasor": klasor, "baslangic": r["baslangic"], "ozsermaye": r["ozsermaye"], "toplam_pnl": r["toplam_pnl"],
            "acik": int(r["acik"] or 0), "islemler": islemler, "maliyet": mal, "gun_oku": r,
            "alinmayan": None, "alinmayan_n": 0}


def _alinmayan_ata(hesaplar: list, durum: Path) -> None:
    """Hesap başına açılmayan sinyal sayısı ve neden sayımı: hesabın kendi dosyası varsa o, yoksa ana dizindeki dosya (hesap alanıyla eşleşen satırlar)."""
    ana = None
    for h in hesaplar:
        yol = h["klasor"] / "alinmayan_sinyaller.jsonl"
        if yol.exists():
            satirlar = go._jsonl(yol)
        else:
            if ana is None:
                ana = go._jsonl(durum / "alinmayan_sinyaller.jsonl")
            anahtarlar = {h["kimlik"], h["kimlik"].split("|")[0], h["klasor"].name}
            satirlar = [s for s in ana if str(s.get("hesap") or s.get("strateji") or "") in anahtarlar]
        h["alinmayan"] = dict(Counter(str(s.get("neden") or "bilinmiyor") for s in satirlar))
        h["alinmayan_n"] = len(satirlar)


def _ders_sayilari(og_listesi: list, kurulumlar: Optional[set]) -> Optional[dict]:
    """{aday, etkin, askida, emekli}: görünür kurulumların dersleri (kurulumlar None: filtre yok, CT'nin kendi dizini). Hiç ders dosyası yoksa None."""
    var, say = False, {"aday": 0, "etkin": 0, "askida": 0, "emekli": 0}
    for og in og_listesi:
        ders = og.get("ders")
        if not isinstance(ders, dict):
            continue
        var = True
        askida = set(((og.get("fren") or {}).get("askida") or {}).keys())
        for k, v in ders.items():
            if not isinstance(v, dict) or (kurulumlar is not None and k.partition(":")[2] not in kurulumlar):
                continue
            st = v.get("status")
            if st == "retired":
                say["emekli"] += 1
            elif st in ("candidate", "alive"):
                say["askida" if k in askida else ("etkin" if st == "alive" else "aday")] += 1
    return say if var else None


def _ml_ifadesi(og: dict, ek: dict, kurulum: Optional[str], simdi: datetime) -> str:
    """Pano ML kartıyla aynı ortak ifade (pano.ml_ozeti + pano.ml_durum_ifadesi); kurulum verilirse yalnız o kurulumun verisiyle."""
    from motor.canli import pano
    if kurulum is not None:
        egitim = ((og.get("durum") or {}).get("egitim") or {})
        og = {**og, "durum": {**(og.get("durum") or {}), "egitim": {kurulum: egitim[kurulum]} if kurulum in egitim else {}},
              "filtre": [kurulum] if kurulum in (og.get("filtre") or []) else []}
        ek = {"adaylar": [a for a in (ek.get("adaylar") or []) if a.get("kurulum") == kurulum], "alinmayan": []}
    return pano.ml_durum_ifadesi(pano.ml_ozeti({"ana_ogrenme": og}, ek, None, simdi))[0]


def topla(durum_dizini, simdi=None, ct_dizin=None, set_yolu=None, gizli: Optional[set] = None, env=None) -> dict:
    """Durum dosyalarından ham veri sözlüğü (yalnız görünür hesaplar). `gizli`: gizli hesap kimlik gövdeleri (None: pano._gizli_adlar; okunamazsa hepsi gizli)."""
    from motor.canli import kurulum_ozeti as ko
    durum = Path(durum_dizini)
    simdi_dt = simdi if isinstance(simdi, datetime) else datetime.now(timezone.utc)
    gun = go._tsi_gun(simdi_dt)
    if gizli is None:
        from motor.canli import pano
        gizli = pano._gizli_adlar()
        if isinstance(gizli, pano._HepsiGizli):                    # gizli liste okunamadı: güvenli taraf, hiçbir şey okunmaz/gönderilmez
            return {"uretim": simdi_dt, "hesaplar": [], "ct": None, "dusus": {"toplam": None, "ct": None}, "ders": None, "ml": []}
    og_ana = ko.ogrenme_oku(durum)
    esl = og_ana.get("esleme") or {}
    hesaplar, gorunur_kurulum = [], {}
    for kimlik, klasor, gorunur in go._set_kayitlari(set_yolu) or []:
        if not gorunur or kimlik.split("|")[0] in gizli:
            continue
        h = _hesap_oku(durum / "hesaplar" / klasor, kimlik, ha.hesap_adi(kimlik, gorunur=True), gun)
        if h is not None:
            hesaplar.append(h)
            gorunur_kurulum[kimlik] = ko.kurulum_adi(esl, kimlik)
    ct = None
    ctd = Path(ct_dizin) if ct_dizin is not None else ko.ct_dizini(env)
    if ctd.is_dir():
        ct = _hesap_oku(ctd, "ct_konsensus", ha.CT_HESABI, gun, ct=True)
    tum = hesaplar + ([ct] if ct else [])
    _alinmayan_ata(tum, durum)

    def dusus(rows):
        try:
            if not rows:
                return None
            t = go._topla_hesaplar([r["gun_oku"] for r in rows])
            return go._kasa_dusus([r["gun_oku"] for r in rows], t("ozsermaye"), t("baslangic"))
        except Exception:  # noqa: BLE001
            return None
    ek = {}
    try:
        from motor.canli import pano
        ek = pano._ogrenme_ek(durum)
    except Exception:  # noqa: BLE001
        ek = {}
    ml = []
    for h in hesaplar:
        k = gorunur_kurulum[h["kimlik"]]
        try:
            ml.append((h["ad"], _ml_ifadesi(og_ana, ek, k, simdi_dt)))
        except Exception:  # noqa: BLE001
            ml.append((h["ad"], None))
    og_ct = ko.ogrenme_oku(ctd) if ct else None
    if ct:
        try:
            ml.append((ct["ad"], _ml_ifadesi(og_ct, {}, None, simdi_dt)))
        except Exception:  # noqa: BLE001
            ml.append((ct["ad"], None))
    ders = _ders_sayilari([og_ana], set(gorunur_kurulum.values()))
    if og_ct is not None:
        d_ct = _ders_sayilari([og_ct], None)
        if d_ct is not None:
            ders = {k: (ders or {}).get(k, 0) + v for k, v in d_ct.items()}
    return {"uretim": simdi_dt, "hesaplar": hesaplar, "ct": ct, "dusus": {"toplam": dusus(hesaplar), "ct": dusus([ct] if ct else [])}, "ders": ders, "ml": ml}


# ------------------------------------------------------------------------------------------------ metin (saf)
def _yuz(x: float, ondalik: int = 1) -> str:
    return "%" + tg.tr_sayi(x, ondalik)


def _ozet_sat(isl: list) -> dict:
    """Kapanan işlem listesi -> {n, net, kazanma, pf, ort_kar, ort_zarar}."""
    n = len(isl)
    kar = [x["net"] for x in isl if x["net"] > 0]
    zr = [x["net"] for x in isl if x["net"] < 0]
    return {"n": n, "net": sum((x["net"] for x in isl), D0), "kazanma": (len(kar) / n * 100) if n else None,
            "pf": (float(sum(kar, D0) / -sum(zr, D0)) if zr and kar else None),
            "ort_kar": (sum(kar, D0) / len(kar)) if kar else None, "ort_zarar": (sum(zr, D0) / len(zr)) if zr else None}


def _kz_sat(ad: str, s: dict) -> str:
    return f"{ad}: {s['n']} işlem · net {tg.usd(s['net'], True)} · kazanma {_yuz(s['kazanma']) if s['kazanma'] is not None else YOK}"


def _bolum_a(ad: str, hesaplar: list, dusus) -> list:
    L = [f"A) {ad}"]
    if not hesaplar:
        return L + [YOK]
    isl = [x for h in hesaplar for x in h["islemler"]]
    s = _ozet_sat(isl)
    bas = [h["baslangic"] for h in hesaplar if h["baslangic"] is not None]
    pnl = [h["toplam_pnl"] for h in hesaplar if h["toplam_pnl"] is not None]
    if pnl:
        net = sum(pnl, D0)
        oran = f" ({tg.yuzde(net / sum(bas, D0))})" if bas and sum(bas, D0) else ""
        L.append(f"Net K/Z (kapanan + açık): {tg.usd(net, True)}{oran}")
    else:
        net = None
        L.append(f"Net K/Z (kapanan + açık): {YOK}")
    L.append(f"İşlem: {s['n']} kapanan / {sum(h['acik'] for h in hesaplar)} açık")
    L.append(f"Kazanma: {_yuz(s['kazanma']) if s['kazanma'] is not None else YOK}")
    L.append(f"Kâr faktörü: {tg.tr_sayi(s['pf']) if s['pf'] is not None else YOK}")
    L.append(f"Ortalama kazanç / ortalama kayıp: {tg.usd(s['ort_kar'], True) if s['ort_kar'] is not None else YOK} / "
             f"{tg.usd(s['ort_zarar'], True) if s['ort_zarar'] is not None else YOK}")
    L.append(f"Zirveden düşüş: {_yuz(dusus, 2) if dusus is not None else YOK}")
    mals = [h["maliyet"] for h in hesaplar]
    if net is not None and mals and all(m is not None for m in mals):
        uc, fo, ka = (sum((m[k] for m in mals), D0) for k in ("ucret", "funding", "kayma"))
        top = uc + fo + ka
        brut = net + top
        oran = f"brüt K/Z'nin {_yuz(float(top / brut * 100))}" if brut > 0 else f"brüt K/Z {tg.usd(brut, True)} (oran yok)"
        L.append(f"Maliyet: komisyon {tg.usd(uc)} + fonlama {tg.usd(fo, True)} + kayma {tg.usd(ka)} = {tg.usd(top)} · {oran}")
    else:
        L.append(f"Maliyet / brüt K/Z: {YOK}")
    if s["n"]:
        en_iyi = sorted((x["net"] for x in isl), reverse=True)[:3]
        L.append(f"En iyi 3 işlem çıkarılınca kapanan net: {tg.usd(s['net'] - sum(en_iyi, D0), True)} (çıkarılan: {tg.usd(sum(en_iyi, D0), True)})")
    else:
        L.append(f"En iyi 3 işlem çıkarılınca net: {YOK}")
    rejimli = [x for x in isl if x["rejim"]]
    if rejimli:
        L.append("Rejime göre (kapanan):")
        gr: dict = {}
        for x in isl:
            gr.setdefault(x["rejim"] or "rejim kaydı yok", []).append(x)
        for r in sorted(gr):
            L.append("  " + _kz_sat(r, _ozet_sat(gr[r])))
    else:
        L.append("Rejime göre: rejim verisi yok")
    for etiket, yon in (("Long", "long"), ("Short", "short")):
        L.append(_kz_sat(etiket, _ozet_sat([x for x in isl if x["yon"] == yon])))
    return L


def _neden_tr(n: str) -> str:
    return tg.NEDEN_TR.get(n, n.replace("_", " "))


def _bolum_b(tum: list) -> list:
    L = ["B) STRATEJİ BAZINDA"]
    if not tum:
        return L + [YOK]
    acan = [h for h in tum if h["islemler"] or h["acik"]]
    uretan = [h for h in tum if h["islemler"] or h["acik"] or h["alinmayan_n"]]
    acmayan = [h for h in tum if h not in acan]
    L.append(f"Toplam strateji: {len(tum)} · sinyal üreten: {len(uretan)} · işlem açan: {len(acan)} · hiç işlem açmayan: {len(acmayan)}")
    for h in tum:
        s = _ozet_sat(h["islemler"])
        sat = f"- {h['ad']}: {s['n']} kapanan" + (f" + {h['acik']} açık" if h["acik"] else "") + (f" · net {tg.usd(h['toplam_pnl'], True)}" if h["toplam_pnl"] is not None else f" · net {YOK}")
        sat += f" · kazanma {_yuz(s['kazanma']) if s['kazanma'] is not None else YOK}"
        if h in acmayan:
            if h["alinmayan"]:
                neden, n = Counter(h["alinmayan"]).most_common(1)[0]
                sat += f" · açmama nedeni: {_neden_tr(neden)} ({n} sinyal)"
            else:
                sat += " · açmama nedeni: sinyal yok"
        L.append(sat)
    return L


def _bolum_c(ders: Optional[dict], ml: list) -> list:
    L = ["C) DERS VE ML DURUMU"]
    L.append(f"Dersler: aday {ders['aday']} · etkin {ders['etkin']} · askıda {ders['askida']} · emekli {ders['emekli']}" if ders else f"Dersler: {YOK}")
    L.append("ML (kurulum başına):" if ml else f"ML: {YOK}")
    for ad, ifade in ml:
        L.append(f"- {ad}: {ifade or YOK}")
    return L


def metin_uret(v: dict) -> str:
    """Ham veri -> belge metni (başlık dahil). Saf fonksiyon; yorum cümlesi yok."""
    u = v["uretim"].astimezone(TSI).strftime("%d.%m.%Y %H:%M") if isinstance(v.get("uretim"), datetime) else YOK
    L = [BASLIK, f"Kâğıt başlangıcından beri · yalnız görünür hesaplar · üretim {u} TSİ", ""]
    L += _bolum_a(TOPLAM_AD, v["hesaplar"], v["dusus"]["toplam"])
    if v.get("ct"):
        L += ["", *_bolum_a(ha.CT_HESABI, [v["ct"]], v["dusus"]["ct"])]
    L += ["", *_bolum_b(v["hesaplar"] + ([v["ct"]] if v.get("ct") else [])), "", *_bolum_c(v.get("ders"), v.get("ml") or [])]
    return "\n".join(L)


# ------------------------------------------------------------------------------------------------ gönderim
def telegram_gonder(metin: str, env=None, oturum=None) -> bool:
    """SESSİZ (disable_notification) gönderim: ≤4096 karakter sendMessage, fazlası sendDocument (.txt, başlık = caption). Düz metin (HTML ayrıştırma yok).
    Başarılı gönderim mevcut gönderim kaydına (`telegram.gonderim_kaydet`) yazılır. Token koda girmez (ortamdan); hata metinleri maskelenir."""
    y = tg.yapilandirma(env)
    if y is None:
        log.info("strateji verisi gönderilmedi: Telegram yapılandırması yok")
        return False
    token, chat = y
    baslik = metin.split("\n", 1)[0]
    try:
        if len(metin) <= MESAJ_MAKS:
            r = tg.api_istek(token, "sendMessage", oturum,
                                              data={"chat_id": chat, "text": metin, "disable_web_page_preview": "true", "disable_notification": "true"}, timeout=20)
        else:
            r = tg.api_istek(token, "sendDocument", oturum,
                                              data={"chat_id": chat, "caption": baslik, "disable_notification": "true"},
                                              files={"document": (BELGE_ADI, metin.encode("utf-8"), "text/plain")}, timeout=30)
    except Exception as e:  # noqa: BLE001  istisna metni URL (token) taşıyabilir: yalnız tür adı + maskeli metin
        log.error("strateji verisi gönderim ağ hatası: %s: %s", type(e).__name__, tg.maskele(str(e), token))
        return False
    if r.status_code != 200:
        log.error("strateji verisi gönderimi başarısız: HTTP %s %s", r.status_code, tg.maskele(r.text[:200], token))
        return False
    tg.gonderim_kaydet(baslik, "INFO", env)
    return True


def _gonderilenler(yol: Path) -> list:
    try:
        c = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    s = c.get("surumler") if isinstance(c, dict) else None
    return [str(x) for x in s] if isinstance(s, list) else []


def tick(durum_dizin, surum: Optional[str], gonder: Callable[[str], bool] = None, simdi: Optional[float] = None, **topla_kw) -> bool:
    """Bu kod sürümü için henüz gönderilmediyse verilerden belgeyi üretip gönderir -> gönderildi mi. Hiçbir hata dışarı çıkmaz.
    Hesap verisi henüz yoksa ya da gönderim başarısızsa işaret konmaz (sonraki turda yeniden denenir)."""
    try:
        gonder = gonder or telegram_gonder
        surum = str(surum or "bilinmiyor")
        yol = Path(durum_dizin) / BAYRAK_DOSYA
        onceki = _gonderilenler(yol)
        if surum in onceki:
            return False
        zaman = time.time() if simdi is None else simdi
        v = topla(durum_dizin, simdi=datetime.fromtimestamp(zaman, timezone.utc), **topla_kw)
        if not v["hesaplar"] and not v["ct"]:
            return False
        if not gonder(metin_uret(v)):
            return False
        try:
            yol.write_text(json.dumps({"surumler": (onceki + [surum])[-50:], "zaman": zaman}), encoding="utf-8")
        except OSError:
            log.warning("strateji verisi işareti yazılamadı")
        return True
    except Exception as e:  # noqa: BLE001  komut dinlemeyi asla etkilemesin
        log.warning("strateji verisi atlandı: %s", type(e).__name__)
        return False
