"""İşlem mutabakatı: motor kaydı = pano = Telegram mı? (kâğıt hesap; CT konsensüs ve aday hesaplar dahil).

Üç kaynak AYNI işlem için karşılaştırılır:
  1. MOTOR: `paper_state.json` (motorun ham kaydı: yön 1/-1, net_pnl float) varsa ham kayıt; yoksa durum dosyaları (`islemler.jsonl`, `maruziyet.json`).
  2. PANO: pano'nun AÇIK / KAPANAN satırlarını üreten aynı fonksiyonlar (`pano._acik_liste/_kapanan_liste/_acik_satiri/_kapanan_satiri`);
     üretilen HTML satırı ayrıştırılır (coin, yön, hesap adı, K/Z) ve motor kaydıyla karşılaştırılır.
  3. TELEGRAM: Telegram GEÇMİŞİNE ERİŞİM YOK; paper.py'nin mesaj üretim yolu yeniden üretilir (`tg.islem_acildi_metni`, `tg.islem_kapandi_metni`;
     paper.py ~satır 915-930: açık pozisyon -> açıldı, kapanan işlem satırı -> kapandı) ve metindeki yön/coin/hesap/K-Z karşılaştırılır.
     Gönderim kaydı (`telegram_gonderim.jsonl`, telegram.gonder yazar) varsa kayıttan sonrası için gerçek gönderimle de karşılaştırılır.
Gizli hesap adı/kimliği HİÇBİR çıktıda yer almaz ("Diğer hesap").

CLI: python -m araclar.islem_mutabakat --durum DIZIN [--ct DIZIN] [--aday DIZIN] [--cikti mutabakat_v1.json] [--md mutabakat_v1.md]
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from motor.canli import durum as d
from motor.canli.gunluk_ozet import _dec, _json, _jsonl
from motor.canli import hesap_adlari as ha
from motor.canli import pano
from motor.canli import telegram as tg

SEMA = "1l3a.mutabakat.v1"
TELEGRAM_NOTU = "Telegram geçmişine erişim yok; motorun mesaj üretim yolu yeniden üretildi"
KASA_TOL = Decimal("0.01")
YON_ESIK = Decimal("0.01")          # fiyat hareketi giriş tutarının %1'inden büyükse ve net işareti ters ise işaret uyuşmazlığı (komisyon/fonlama payı)
TSI_FMT = "%Y-%m-%d %H:%M"


def _tsi(z) -> str:
    try:
        return datetime.strptime(str(z), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(tg.TSI).strftime(TSI_FMT)
    except ValueError:
        return str(z)


def _iso(t) -> Optional[str]:
    try:
        import pandas as pd
        return d.zaman_str(pd.Timestamp(t).tz_convert("UTC") if getattr(pd.Timestamp(t), "tzinfo", None) else pd.Timestamp(t, tz="UTC"))
    except Exception:  # noqa: BLE001
        return None


def _usd_ayristir(metin: str) -> Optional[Decimal]:
    """'+1,234.50 $' (pano) ya da '−12,40 $' / '+1.234,50 $' (Telegram, TR) -> Decimal."""
    m = metin.replace("−", "-").replace("$", "").strip()
    if re.search(r",\d{1,2}$", m):                       # TR biçimi
        m = m.replace(".", "").replace(",", ".")
    else:
        m = m.replace(",", "")
    try:
        return Decimal(m.replace(" ", ""))
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------------------------- ham motor kaydı
def _ham_bul(x, anahtar: str, out: list) -> None:
    if isinstance(x, dict):
        for k, v in x.items():
            if k == anahtar:
                out.append(v)
            else:
                _ham_bul(v, anahtar, out)
    elif isinstance(x, list):
        for v in x:
            _ham_bul(v, anahtar, out)


def ham_motor(dizin: Path, gizli: Optional[set] = None) -> Optional[dict]:
    """paper_state.json -> {"islemler": [...], "acik": [...], "acik_gorunur_sayi": int}. Dosya yoksa None.
    `acik_gorunur_sayi`: v2 kaydında ("hesaplar" var) yalnız GÖRÜNÜR hesapların motor.acik bloklarındaki pozisyon sayısı (gizli hesaplar hariç;
    askıdaki pozisyonlar aynı bloktadır, çağıran askıda adedini düşer); tek hesaplı kayıtta (ct/aday) tüm acik blokları."""
    s = _json(Path(dizin) / "paper_state.json")
    if s is None:
        return None
    from motor.canli.paper_motor import _dec as dec_motor
    s = dec_motor(s)
    ist, acik = [], []
    bloklar: list = []
    if isinstance(s.get("hesaplar"), dict) and gizli is not None:      # v2: kapanan işlemler yalnız GÖRÜNÜR hesaplardan (gizli hesap kapanışı sahte uyuşmazlık/iz üretmez)
        for kim, h in s["hesaplar"].items():
            if _pano_gorunur(str(kim), gizli):
                _ham_bul(h, "islemler", bloklar)
    else:
        _ham_bul(s, "islemler", bloklar)
    for liste in bloklar:
        for x in liste if isinstance(liste, list) else []:
            if isinstance(x, dict) and "net_pnl" in x and "yon" in x:
                ist.append({"sembol": x.get("sembol"), "yon": int(x["yon"]), "giris": _iso(x.get("giris_zamani")), "cikis": _iso(x.get("cikis_zamani")),
                            "net": _dec(x["net_pnl"]), "miktar": _dec(x.get("miktar"))})
    acik_bloklar: list = []
    _ham_bul(s, "acik", acik_bloklar)
    for blok in acik_bloklar:
        for q in (blok.values() if isinstance(blok, dict) else []):
            if isinstance(q, dict) and "yon" in q and "giris" in q:
                acik.append({"sembol": q.get("sembol"), "yon": int(q["yon"]), "giris": _iso(q.get("zaman")), "miktar": _dec(q.get("miktar"))})
    sayi = len(acik)
    if isinstance(s.get("hesaplar"), dict):
        sayi = 0
        for kim, h in s["hesaplar"].items():
            if gizli is not None and not _pano_gorunur(str(kim), gizli):
                continue
            bl: list = []
            _ham_bul(h, "acik", bl)
            sayi += sum(1 for b in bl for q in (b.values() if isinstance(b, dict) else []) if isinstance(q, dict) and "yon" in q and "giris" in q)
    return {"islemler": ist, "acik": acik, "acik_gorunur_sayi": sayi}


# ----------------------------------------------------------------------------------------------- pano ve Telegram çözümleyicileri
def _etiketsiz(h: str) -> str:
    return re.sub(r"<[^>]+>", "", h).strip()


def pano_kapanan_ayristir(x: dict) -> dict:
    h = pano._kapanan_satiri(x)
    m = re.search(r'<summary><span class="c"><b>(.*?)</b><span class="alt">(.*?)</span></span>', h, re.S)
    k = re.search(r'<b class="[^"]*">([^<]*)</b><span class="alt">', h)
    coin_yon = _etiketsiz(m.group(1)).split() if m else []
    return {"coin": coin_yon[0] if coin_yon else None, "yon": coin_yon[1] if len(coin_yon) > 1 else None,
            "hesap": _etiketsiz(m.group(2)) if m else None, "net": _usd_ayristir(k.group(1)) if k else None}


def pano_acik_ayristir(p: dict, simdi) -> dict:
    h = pano._acik_satiri(p, simdi)
    m = re.search(r'<summary><span class="c"><b>(.*?)</b><span class="alt">(.*?)</span></span>', h, re.S)
    k = re.search(r'<b class="[^"]*">([^<]*)</b><span class="alt">', h)
    coin_yon = _etiketsiz(m.group(1)).split() if m else []
    return {"coin": coin_yon[0] if coin_yon else None, "yon": coin_yon[1] if len(coin_yon) > 1 else None,
            "hesap": _etiketsiz(m.group(2)) if m else None, "net": _usd_ayristir(k.group(1)) if k else None}


_MSG = re.compile(r"^\[1L3A\]\s*(?:\S+\s+)?(?P<coin>\S+)\s+(?P<yon>long|short)\s+(?P<olay>açıldı|kapandı)\s+·\s+(?P<hesap>.+)$")


def mesaj_ayristir(metin: str) -> dict:
    ilk, _, kalan = str(metin).partition("\n")
    m = _MSG.match(ilk.strip())
    if not m:
        return {}
    ikinci = kalan.split("\n", 1)[0]
    kz = re.match(r"\s*([+−-][\d.,]+ \$)", ikinci)
    em = re.match(r"^\[1L3A\]\s*(\S+)", ilk)
    return {"coin": m["coin"], "yon": m["yon"], "olay": m["olay"], "hesap": m["hesap"].strip(), "net": _usd_ayristir(kz.group(1)) if kz else None,
            "emoji": em.group(1) if em else None}


def _gizli() -> set:
    try:
        return pano._gizli_adlar()                     # okunamazsa pano "hepsi gizli" kümesi döner (kapalı-başarısız)
    except Exception:  # noqa: BLE001
        return pano._HepsiGizli()


def _pano_gorunur(kimlik: str, gizli: set) -> bool:
    return kimlik.split("|")[0] not in gizli          # pano._ad_goster ile aynı kural


def _tg_gorunur(kimlik: str, gizli: set) -> bool:
    return kimlik not in gizli                         # paper._gorunur_hesap (kimlik in p.gorunur_adlar) ile aynı kural


# ----------------------------------------------------------------------------------------------- hesap grupları
def _hesap_gruplari(durum: Path, ct: Optional[Path], aday: Optional[Path]) -> list:
    """-> [{"tur": ana|ct|aday, "dizin": Path, "etiket": ...}]; yalnız var olan dizinler. Ana dizin üst düzey (toplam) kayıttır."""
    g = [{"tur": "ana", "dizin": Path(durum)}]
    if ct and Path(ct).is_dir():
        g.append({"tur": "ct", "dizin": Path(ct)})
    if aday and Path(aday).is_dir():
        for alt in sorted(p for p in Path(aday).iterdir() if p.is_dir()):
            g.append({"tur": "aday", "dizin": alt})
    return g


def _kimlikler(dizin: Path, isl: list) -> Optional[str]:
    st = _json(dizin / "stratejiler.json") or {}
    for s in st.get("stratejiler") or []:
        if isinstance(s, dict) and s.get("kimlik"):
            return str(s["kimlik"])
    return isl[0]["kimlik"] if isl else None


def _yon_isaret_sorunu(yon: str, giris, cikis, net, miktar) -> bool:
    """Fiyat hareketi (yöne göre brüt) giriş tutarının %1'inden büyükse ve net işareti TERS ise True."""
    g, c, n, m = _dec(giris), _dec(cikis), _dec(net), _dec(miktar)
    if None in (g, c, n, m) or not g or not m:
        return False
    brut = (c - g) * m * (1 if yon == "long" else -1)
    esik = YON_ESIK * g * m
    return (brut > esik and n < 0) or (brut < -esik and n > 0)


def _acik_isaret_sorunu(yon: str, giris, mark, kz) -> bool:
    g, mk, k = _dec(giris), _dec(mark), _dec(kz)
    if None in (g, mk, k) or not g:
        return False
    hareket = (mk - g) * (1 if yon == "long" else -1)
    esik = YON_ESIK * g
    return (hareket > esik and k < 0) or (hareket < -esik and k > 0)


def hesapla(durum, ct=None, aday=None, simdi: Optional[datetime] = None) -> dict:
    simdi = simdi or datetime.now(timezone.utc)
    gizli = _gizli()
    gizli_dizin = {"".join(c if (c.isalnum() or c in "._-") else "_" for c in k) for k in gizli}
    satirlar: list = []
    uyus: list = []
    hesap_ozetleri: list = []
    kasa_kontrol: list = []
    n_sort = 0

    def sorun(satir_no, hesap, mesaj, tur, **ek):
        """ek: yapısal alanlar (beklenen, kayit, fark, birim) — Telegram özeti sade metin için kullanır."""
        uyus.append({"islem_no": satir_no, "hesap": hesap, "tur": tur, "mesaj": mesaj, **ek})

    grup = _hesap_gruplari(durum, ct, aday)
    # pano veri: ana (üst düzey) + ct (pano'nun kendi okuyucusu)
    veri = {"islemler": [], "maruziyet": _json(Path(durum) / "maruziyet.json"), "stratejiler": _json(Path(durum) / "stratejiler.json"), "ct_hesap": None}
    try:
        veri["islemler"] = d.oku_islemler(durum)
    except d.DurumHatasi as e:
        uyus.append({"islem_no": None, "hesap": "Ana", "tur": "pano_okuma", "mesaj": f"islemler.jsonl okunamadı: {e}"})
    if ct and Path(ct).is_dir():
        veri["ct_hesap"] = pano._hesap_oku(ct, kimlik_sart=True)
    pano_acik = pano._acik_liste(veri)
    pano_kapanan_hepsi = pano._kapanan_liste(veri)
    pano_gorunen = {id(x) for x in pano_kapanan_hepsi[:pano.ISLEM_GOSTER]}
    pano_acik_idler = {id(x) for x in pano_acik}

    tg_log = []
    dizinler = [Path(durum)]
    try:
        gd = tg.gonderim_dizini()
        if gd is not None and gd not in dizinler:
            dizinler.append(gd)
    except Exception:  # noqa: BLE001
        pass
    for dz_ in dizinler:
        for ad_ in (tg.GONDERIM_DOSYA + ".1", tg.GONDERIM_DOSYA):
            tg_log += _jsonl(dz_ / ad_)

    beklenen_tg: list = []                 # (olay, coin, hesap, yon, zaman_iso, satir_no, zorunlu)
    for g in grup:
        dz = g["dizin"]
        if g["tur"] == "ana":
            isl = [x for x in veri["islemler"]]
            poz = [p for p in pano_acik if not p.get("ct")]
            pano_isl_idler = {id(x) for x in isl}
        elif g["tur"] == "ct":
            h = veri["ct_hesap"] or {"pozisyonlar": [], "islemler": []}
            isl, poz = h["islemler"], h["pozisyonlar"]
            pano_isl_idler = {id(x) for x in isl}
        else:
            h = pano._hesap_oku(dz) or {"pozisyonlar": [], "islemler": []}
            isl, poz = h["islemler"], h["pozisyonlar"]
            pano_isl_idler = set()
        ham = ham_motor(dz, gizli if g["tur"] == "ana" else None)
        ham_eslesen: set = set()
        for x in sorted(isl, key=lambda r: r["zaman"]):
            n_sort += 1
            no = n_sort
            kimlik = x["kimlik"]
            if g["tur"] == "ct":
                hesap_goster, tg_gorunur = ha.CT_HESABI, True
            elif g["tur"] == "aday":
                hesap_goster, tg_gorunur = ha.hesap_adi(kimlik) + " · Aday hesabı", True
            else:
                hesap_goster = pano._ad_goster(kimlik)
                tg_gorunur = _tg_gorunur(kimlik, gizli)
            pano_ad = pano._ad_goster(kimlik, g["tur"] == "ct")
            motor_yon = x["yon"]
            sat = {"islem_no": no, "durum": "kapali", "hesap": hesap_goster, "coin": ha.coin_adi(x["sembol"]), "yon": motor_yon,
                   "acilis_tsi": _tsi(x.get("giris_zamani")), "kapanis_tsi": _tsi(x.get("cikis_zamani") or x["zaman"]),
                   "giris_fiyati": x.get("giris_fiyati"), "cikis_fiyati": x.get("cikis_fiyati"), "net_kz": x["net_pnl_yerel"], "sorunlar": []}
            net = _dec(x["net_pnl_yerel"])
            # --- ham motor
            if ham is not None:
                esl = next((r for r in ham["islemler"] if id(r) not in ham_eslesen and r["sembol"] == x["sembol"] and r["giris"] == x.get("giris_zamani")
                            and r["cikis"] == x.get("cikis_zamani")), None)
                if esl is None:
                    sat["sorunlar"].append("ham motor kaydında yok")
                else:
                    ham_eslesen.add(id(esl))
                    ham_yon = "long" if esl["yon"] == 1 else "short"
                    sat["motor_ham_yon"] = ham_yon
                    if ham_yon != motor_yon:
                        sat["sorunlar"].append(f"ham motor yönü {ham_yon}, durum dosyası {motor_yon}")
                    if esl["net"] is not None and net is not None and abs(esl["net"] - net) > KASA_TOL:
                        sat["sorunlar"].append(f"ham motor net K/Z {esl['net']}, durum dosyası {net}")
            # --- pano
            if g["tur"] in ("ana", "ct"):
                if id(x) in pano_gorunen:
                    pr = pano_kapanan_ayristir(x)
                    sat["pano"] = {"var": True, "yon": pr["yon"], "hesap": pr["hesap"], "net": None if pr["net"] is None else str(pr["net"]), "ayni": True}
                    if pr["yon"] != motor_yon:
                        sat["pano"]["ayni"] = False
                        sat["sorunlar"].append(f"pano yönü {pr['yon']}, motor {motor_yon}")
                    if pr["coin"] != sat["coin"]:
                        sat["pano"]["ayni"] = False
                        sat["sorunlar"].append(f"pano coin {pr['coin']}, motor {sat['coin']}")
                    if pr["hesap"] != pano_ad:
                        sat["pano"]["ayni"] = False
                        sat["sorunlar"].append(f"pano hesap adı {pr['hesap']}, beklenen {pano_ad}")
                    if pr["net"] is None or net is None or abs(pr["net"] - net) > KASA_TOL:
                        sat["pano"]["ayni"] = False
                        sat["sorunlar"].append(f"pano K/Z {pr['net']}, motor {net}")
                else:
                    sat["pano"] = {"var": False, "not": f"pano yalnız en yeni {pano.ISLEM_GOSTER} kapanan işlemi gösterir (sınır dışı)"}
            else:
                sat["pano"] = {"var": None, "not": "aday hesaplar pano tablolarında değil, aday kartındadır (aynı okuyucu: pano._hesap_oku)"}
            # --- Telegram (yeniden üretim)
            satir_tg = {**x, "kimlik": kimlik}
            kap = tg.islem_kapandi_metni(satir_tg, gorunur=tg_gorunur)
            ac = tg.islem_acildi_metni({"kimlik": kimlik, "sembol": x["sembol"], "yon": motor_yon, "giris_fiyati": x.get("giris_fiyati"),
                                        "nominal": None, "stop": None}, gorunur=tg_gorunur)
            tr = {}
            for ad, metin, olay in (("acildi", ac, "açıldı"), ("kapandi", kap, "kapandı")):
                pm = mesaj_ayristir(metin)
                if g["tur"] == "ct":
                    pm_ek = tg_ct_etiket(metin)
                    pm = mesaj_ayristir(pm_ek)
                elif g["tur"] == "aday":
                    pm = mesaj_ayristir(tg_aday_etiket(metin, kimlik))
                ok = True
                if not pm or pm.get("olay") != olay:
                    ok = False
                    sat["sorunlar"].append(f"Telegram {olay} mesajı ayrıştırılamadı")
                else:
                    if pm["yon"] != motor_yon:
                        ok = False
                        sat["sorunlar"].append(f"Telegram {olay} yönü {pm['yon']}, motor {motor_yon}")
                    if pm["coin"] != sat["coin"]:
                        ok = False
                        sat["sorunlar"].append(f"Telegram {olay} coin {pm['coin']}, motor {sat['coin']}")
                    if not pm["hesap"].startswith(hesap_goster):
                        ok = False
                        sat["sorunlar"].append(f"Telegram {olay} hesap adı {pm['hesap']}, beklenen {hesap_goster}")
                    if ad == "acildi" and pm.get("emoji") != ("🟢" if motor_yon == "long" else "🟠"):
                        ok = False
                        sat["sorunlar"].append(f"Telegram açıldı işareti {pm.get('emoji')} yönle ({motor_yon}) uyuşmuyor")
                    if ad == "kapandi" and (pm["net"] is None or net is None or abs(pm["net"] - net) > KASA_TOL):
                        ok = False
                        sat["sorunlar"].append(f"Telegram kapandı K/Z {pm['net']}, motor {net}")
                tr[ad] = {"metin_ilk_satir": metin.split("\n", 1)[0], "uyumlu": ok, "yon": (pm or {}).get("yon")}
                beklenen_tg.append((olay, sat["coin"], hesap_goster, (pm or {}).get("yon"), x.get("cikis_zamani") if olay == "kapandı" else x.get("giris_zamani"),
                                    no, olay == "kapandı", motor_yon))
            sat["telegram"] = tr
            # --- short işaret kontrolü
            if _yon_isaret_sorunu(motor_yon, x.get("giris_fiyati"), x.get("cikis_fiyati"), net, x.get("miktar")):
                sat["isaret_uyusmazligi"] = True
                sat["sorunlar"].append("fiyat hareketi ile K/Z işareti ters (yön ya da fiyat hatası şüphesi)")
            satirlar.append(sat)
            for m in sat["sorunlar"]:
                sorun(no, hesap_goster, m, "kapanan")
        # ham motorda olup durum dosyasında olmayan işlemler
        if ham is not None:
            for r in ham["islemler"]:
                if id(r) not in ham_eslesen:
                    sorun(None, "—", f"ham motor işlemi durum dosyasında yok: {ha.coin_adi(str(r['sembol']))} {r['giris']}", "kapanan")
        # --- açık pozisyonlar
        for p in sorted(poz, key=lambda r: str(r.get("giris_zamani"))):
            n_sort += 1
            no = n_sort
            kimlik = p.get("kimlik", "")
            if g["tur"] == "ct":
                hesap_goster, tg_gorunur = ha.CT_HESABI, True
            elif g["tur"] == "aday":
                hesap_goster, tg_gorunur = ha.hesap_adi(kimlik) + " · Aday hesabı", True
            else:
                hesap_goster, tg_gorunur = pano._ad_goster(kimlik), _tg_gorunur(kimlik, gizli)
            pano_ad = pano._ad_goster(kimlik, g["tur"] == "ct")
            sat = {"islem_no": no, "durum": "acik", "hesap": hesap_goster, "coin": ha.coin_adi(p["sembol"]), "yon": p["yon"],
                   "acilis_tsi": _tsi(p.get("giris_zamani")), "kapanis_tsi": None, "giris_fiyati": p.get("giris_fiyati"), "cikis_fiyati": None,
                   "net_kz": p.get("kz"), "sorunlar": []}
            if ham is not None:
                esl = next((r for r in ham["acik"] if r["sembol"] == p["sembol"] and r["giris"] == p.get("giris_zamani")), None)
                if esl is None:
                    sat["sorunlar"].append("ham motor açık kaydında yok")
                else:
                    ham_yon = "long" if esl["yon"] == 1 else "short"
                    sat["motor_ham_yon"] = ham_yon
                    if ham_yon != p["yon"]:
                        sat["sorunlar"].append(f"ham motor yönü {ham_yon}, durum dosyası {p['yon']}")
            if g["tur"] in ("ana", "ct"):
                if id(p) in pano_acik_idler:
                    pr = pano_acik_ayristir(p, simdi)
                    sat["pano"] = {"var": True, "yon": pr["yon"], "hesap": pr["hesap"], "net": None if pr["net"] is None else str(pr["net"]), "ayni": True}
                    kz = _dec(p.get("kz"))
                    for ad, a, b in (("yönü", pr["yon"], p["yon"]), ("coin", pr["coin"], sat["coin"]), ("hesap adı", pr["hesap"], pano_ad)):
                        if a != b:
                            sat["pano"]["ayni"] = False
                            sat["sorunlar"].append(f"pano {ad} {a}, motor {b}")
                    if pr["net"] is None or kz is None or abs(pr["net"] - kz) > KASA_TOL:
                        sat["pano"]["ayni"] = False
                        sat["sorunlar"].append(f"pano K/Z {pr['net']}, motor {kz}")
                else:
                    sat["pano"] = {"var": False}
                    sat["sorunlar"].append("açık pozisyon pano listesinde yok")
            else:
                sat["pano"] = {"var": None, "not": "aday hesaplar pano tablolarında değil, aday kartındadır"}
            acil = {"kimlik": kimlik, "sembol": p["sembol"], "yon": p["yon"], "giris_fiyati": p.get("giris_fiyati"), "nominal": p.get("nominal"), "stop": p.get("stop")}
            metin = tg.islem_acildi_metni(acil, gorunur=tg_gorunur)
            if g["tur"] == "ct":
                metin = tg_ct_etiket(metin)
            elif g["tur"] == "aday":
                metin = tg_aday_etiket(metin, kimlik)
            pm = mesaj_ayristir(metin)
            ok = bool(pm) and pm["olay"] == "açıldı" and pm["yon"] == p["yon"] and pm["coin"] == sat["coin"] and pm["hesap"].startswith(hesap_goster) \
                and pm.get("emoji") == ("🟢" if p["yon"] == "long" else "🟠")
            if not ok:
                sat["sorunlar"].append(f"Telegram açıldı mesajı motorla uyuşmuyor: {metin.split(chr(10), 1)[0]}")
            sat["telegram"] = {"acildi": {"metin_ilk_satir": metin.split("\n", 1)[0], "uyumlu": ok, "yon": (pm or {}).get("yon")}}
            beklenen_tg.append(("açıldı", sat["coin"], hesap_goster, (pm or {}).get("yon"), p.get("giris_zamani"), no, True, p["yon"]))
            if _acik_isaret_sorunu(p["yon"], p.get("giris_fiyati"), p.get("mark_fiyat"), p.get("kz_brut", p.get("kz"))):
                sat["isaret_uyusmazligi"] = True
                sat["sorunlar"].append("fiyat hareketi ile K/Z işareti ters (yön ya da fiyat hatası şüphesi)")
            satirlar.append(sat)
            for m in sat["sorunlar"]:
                sorun(no, hesap_goster, m, "acik")
        # --- hesap kasa kontrolü (ozet.json)
        oz = _json(dz / "ozet.json")
        ad_goster = {"ana": "Toplam (görünür hesaplar)", "ct": ha.CT_HESABI, "aday": "Aday hesabı"}[g["tur"]]
        if isinstance(oz, dict) and oz.get("ozsermaye") is not None and oz.get("baslangic_ozsermaye") is not None:
            def toplam(kapsam_gorunur: bool) -> Decimal:
                t = Decimal(0)
                for x in isl:
                    if g["tur"] == "ana" and kapsam_gorunur and not _pano_gorunur(x["kimlik"], gizli):
                        continue
                    t += _dec(x["net_pnl_yerel"]) or Decimal(0)
                for p in poz:
                    if g["tur"] == "ana" and kapsam_gorunur and not _pano_gorunur(p.get("kimlik", ""), gizli):
                        continue
                    t += _dec(p.get("kz")) or Decimal(0)        # NET açık K/Z (komisyon+fonlama+kısmi brüt dahil); kasadan bunlar zaten işlendi
                a = oz.get("askida") if isinstance(oz.get("askida"), dict) else {}
                t += (_dec(a.get("kapanis_net")) or Decimal(0)) + (_dec(a.get("acik_net")) or Decimal(0))     # askıdaki pozisyonlar (durum yazımı)
                return t
            bas, kasa = _dec(oz["baslangic_ozsermaye"]), _dec(oz["ozsermaye"])
            tol = KASA_TOL + Decimal("0.005") * Decimal(len(isl) + len(poz)) ** Decimal("0.5")
            sonuc = None
            for gorunur in (True, False):
                beklenen = bas + toplam(gorunur)
                fark = kasa - beklenen
                if abs(fark) <= tol or sonuc is None:
                    sonuc = {"kapsam": "görünür hesaplar" if gorunur else "tüm hesaplar", "beklenen": str(beklenen.quantize(Decimal("0.01"))), "fark": str(fark.quantize(Decimal("0.01")))}
                if abs(fark) <= tol:
                    break
            ok = abs(Decimal(sonuc["fark"])) <= tol
            eski = any(p.get("kz_brut") is None for p in poz)
            kasa_kontrol.append({"hesap": ad_goster, "ozsermaye": str(kasa), "baslangic": str(bas), **sonuc, "tolerans": str(tol.quantize(Decimal("0.001"))), "tamam": ok,
                                 **({"not": "eski kayıt: açık K/Z brüt olabilir (kz_brut alanı yok)"} if eski and poz else {})})
            if not ok:
                sorun(None, ad_goster, f"kasa {kasa} ≠ başlangıç {bas} + net K/Z ({sonuc['beklenen']}); fark {sonuc['fark']}", "kasa",
                      beklenen=sonuc["beklenen"], kayit=str(kasa.quantize(Decimal("0.01"))), fark=sonuc["fark"], birim="usd")
            # açık pozisyon sayısı: motor sayacı = pano listesi = (ham)
            sayac = (oz.get("sayaclar") or {}).get("acik_pozisyon")
            n_acik = len(poz)
            if sayac is not None and int(sayac) != n_acik:
                sorun(None, ad_goster, f"açık pozisyon sayısı: motor sayacı {sayac}, pano listesi {n_acik}", "acik_sayisi",
                      beklenen=n_acik, kayit=int(sayac), fark=int(sayac) - n_acik, birim="adet", kaynak="motor sayacı")
            if ham is not None:
                askida_adet = int((oz.get("askida") or {}).get("acik_adet") or 0) if isinstance(oz.get("askida"), dict) else 0
                ham_n = ham["acik_gorunur_sayi"] - askida_adet          # yalnız görünür hesaplar, askıdakiler hariç
                if ham_n != n_acik:
                    sorun(None, ad_goster, f"açık pozisyon sayısı: ham motor {ham_n}, pano listesi {n_acik}", "acik_sayisi",
                          beklenen=n_acik, kayit=ham_n, fark=ham_n - n_acik, birim="adet", kaynak="ham motor")
        hesap_ozetleri.append({"hesap": ad_goster, "tur": g["tur"], "kapanan": len(isl), "acik": len(poz), "ham_motor_kaydi": ham is not None})

    # --- şerit toplamı: üst düzey kasa = görünür hesap klasörlerinin toplamı
    hdir = Path(durum) / "hesaplar"
    ust = _json(Path(durum) / "ozet.json")
    if hdir.is_dir() and isinstance(ust, dict) and ust.get("ozsermaye") is not None:
        t, n = Decimal(0), 0
        for alt in sorted(p for p in hdir.iterdir() if p.is_dir()):
            if alt.name in gizli_dizin:
                continue
            o = _json(alt / "ozet.json")
            if isinstance(o, dict) and o.get("ozsermaye") is not None:
                t += _dec(o["ozsermaye"])
                n += 1
        fark = _dec(ust["ozsermaye"]) - t
        ok = abs(fark) <= KASA_TOL * max(n, 1)
        kasa_kontrol.append({"hesap": "Şerit toplamı = görünür hesapların toplamı", "ozsermaye": str(ust["ozsermaye"]), "beklenen": str(t), "fark": str(fark), "tamam": ok, "hesap_sayisi": n})
        if not ok:
            sorun(None, "Şerit", f"şerit kasası {ust['ozsermaye']} ≠ görünür hesap toplamı {t} (fark {fark})", "serit")

    # --- Telegram gönderim kaydı karşılaştırması (yalnız kayıt başladıktan sonraki olaylar)
    tgs = {"gecmis_notu": TELEGRAM_NOTU, "gonderim_kaydi_satir": len(tg_log), "kayit_baslangici": min((x.get("zaman") for x in tg_log if x.get("zaman")), default=None),
           "eksik": 0, "fazla": 0, "yanlis_yonlu": 0}
    if tg_log:
        bas_z = tgs["kayit_baslangici"]
        gonderilen = []
        for x in tg_log:
            pm = mesaj_ayristir(x.get("ilk_satir", ""))
            if pm:
                gonderilen.append(pm)
        beklenen_kume: dict = {}
        for olay, coin, hesap, yon_tg, z, no, zorunlu, motor_yon in beklenen_tg:
            if z and str(z) >= str(bas_z):
                beklenen_kume.setdefault((olay, coin, hesap, motor_yon), []).append((no, zorunlu))
        for pm in gonderilen:
            anahtar = (pm["olay"], pm["coin"], pm["hesap"], pm["yon"])
            hesap_ad = anahtar[2]
            if beklenen_kume.get(anahtar):
                beklenen_kume[anahtar].pop()
                continue
            diger = [k for k in beklenen_kume if k[:3] == anahtar[:3] and k[3] != anahtar[3] and beklenen_kume[k]]
            if diger:
                tgs["yanlis_yonlu"] += 1
                sorun(None, hesap_ad, f"gönderilen Telegram mesajı yanlış yönlü: {pm['coin']} {pm['yon']} {pm['olay']} (motor {diger[0][3]})", "telegram_gonderim")
            else:
                tgs["fazla"] += 1
        for k, v in beklenen_kume.items():
            for no, zorunlu in v:
                if zorunlu:
                    tgs["eksik"] += 1
                    sorun(no, k[2], f"Telegram {k[0]} mesajı gönderim kaydında yok ({k[1]} {k[3]})", "telegram_gonderim")
    else:
        tgs["not"] = "telegram_gonderim.jsonl yok (kayıt ileriye dönük başlar); mesajlar yeniden üretimle doğrulandı"

    # --- short özeti
    sh = [s for s in satirlar if s["yon"] == "short"]
    short = {"sayi": len(sh), "kapanan": sum(1 for s in sh if s["durum"] == "kapali"), "acik": sum(1 for s in sh if s["durum"] == "acik"),
             "isaret_uyusmazligi": sum(1 for s in sh if s.get("isaret_uyusmazligi")),
             "panoda_long_gorunen": sum(1 for s in sh if (s.get("pano") or {}).get("yon") == "long"),
             "telegramda_long_gorunen": sum(1 for s in sh if any((t or {}).get("yon") == "long" for t in (s.get("telegram") or {}).values())),
             "motor_ham_long_gorunen": sum(1 for s in sh if s.get("motor_ham_yon") == "long")}
    adlar = {(s["hesap"], (s.get("pano") or {}).get("hesap")) for s in satirlar if (s.get("pano") or {}).get("hesap") and s["hesap"] != s["pano"]["hesap"] and s["hesap"] != "Diğer hesap"}
    notlar = [f"Hesap adı farkı: Telegram '{a}' / pano '{b}' (aynı hesap, farklı yazım)" for a, b in sorted(adlar)]
    cikti = {"sema": SEMA, "uretim": simdi.strftime("%Y-%m-%dT%H:%M:%SZ"), "mod": "kagit", "telegram_notu": TELEGRAM_NOTU,
             "ozet": {"islem_sayisi": len(satirlar), "kapanan_islem": sum(1 for s in satirlar if s["durum"] == "kapali"),
                      "acik_pozisyon": sum(1 for s in satirlar if s["durum"] == "acik"), "uyusmazlik_sayisi": len(uyus),
                      "uyusmazliklar": uyus, "notlar": notlar, "short": short, "telegram": tgs, "kasa_kontrolleri": kasa_kontrol, "hesaplar": hesap_ozetleri},
             "satirlar": satirlar}
    return _temizle(cikti, gizli)


def tg_ct_etiket(metin: str) -> str:
    from motor.canli import ct_paper as cp
    return cp.etiket_ekle(metin, cp.BASLIK)


def tg_aday_etiket(metin: str, kimlik: str) -> str:
    from motor.canli import aday_paper as ap
    return ap.cp.etiket_ekle(metin, ap.baslik(kimlik))


def _temizle(cikti: dict, gizli: set) -> dict:
    """Savunma: gizli hesap adı/kimliği çıktıda bir yerde kaldıysa 'Diğer hesap' ile değiştirilir."""
    metin = json.dumps(cikti, ensure_ascii=False)
    for k in sorted((g for g in gizli if g), key=len, reverse=True):
        metin = metin.replace(json.dumps(k, ensure_ascii=False)[1:-1], ha.DIGER_HESAP)
    return json.loads(metin)


def markdown(c: dict) -> str:
    o = c["ozet"]
    s = o["short"]
    L = [f"# İşlem mutabakatı ({c['uretim']})", "", f"> {c['telegram_notu']}.", "",
         f"- İşlem: {o['islem_sayisi']} (kapanan {o['kapanan_islem']}, açık {o['acik_pozisyon']})",
         f"- Uyuşmazlık: **{o['uyusmazlik_sayisi']}**",
         f"- Short: {s['sayi']} (kapanan {s['kapanan']}, açık {s['acik']}); işaret uyuşmazlığı {s['isaret_uyusmazligi']}; "
         f"panoda long görünen short {s['panoda_long_gorunen']}; Telegram'da long görünen short {s['telegramda_long_gorunen']}",
         f"- Telegram gönderim kaydı: {o['telegram']['gonderim_kaydi_satir']} satır; eksik {o['telegram']['eksik']}, fazla {o['telegram']['fazla']}, yanlış yönlü {o['telegram']['yanlis_yonlu']}", ""]
    if o["uyusmazliklar"]:
        L += ["## Uyuşmazlıklar", ""] + [f"- #{u['islem_no']} · {u['hesap']} · {u['tur']}: {u['mesaj']}" for u in o["uyusmazliklar"]] + [""]
    L += ["## Kasa kontrolleri", ""] + [f"- {k['hesap']}: kasa {k['ozsermaye']}, beklenen {k['beklenen']}, fark {k['fark']} ({'tamam' if k['tamam'] else 'UYUŞMUYOR'})" for k in o["kasa_kontrolleri"]]
    L += ["", "## İşlemler", "", "| No | Hesap | Coin | Yön | Açılış (TSİ) | Kapanış (TSİ) | Giriş | Çıkış | Net K/Z | Pano | Telegram | Sorun |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in c["satirlar"]:
        pv = (r.get("pano") or {}).get("var")
        pano_h = "—" if pv is None else ("evet" if pv and r["pano"].get("ayni") else ("sınır dışı" if pv is False and not r["sorunlar"] else "FARKLI"))
        tgh = "evet" if all(t["uyumlu"] for t in (r.get("telegram") or {}).values()) else "FARKLI"
        L.append(f"| {r['islem_no']} | {r['hesap']} | {r['coin']} | {r['yon']} | {r['acilis_tsi']} | {r['kapanis_tsi'] or '—'} | {r['giris_fiyati']} | {r['cikis_fiyati'] or '—'} | "
                 f"{r['net_kz']} | {pano_h} | {tgh} | {'; '.join(r['sorunlar']) or '—'} |")
    return "\n".join(L) + "\n"


def yaz(durum, ct=None, aday=None, cikti=None, md=None) -> dict:
    c = hesapla(durum, ct, aday)
    cikti = Path(cikti or Path(durum) / "mutabakat_v1.json")
    tmp = cikti.with_name(cikti.name + ".tmp")
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(cikti)
    mdyol = Path(md or cikti.with_suffix(".md"))
    mdyol.write_text(markdown(c), encoding="utf-8")
    return c


def main(argv=None) -> int:
    import os
    ap = argparse.ArgumentParser(description="1L3A işlem mutabakatı: motor = pano = Telegram")
    ap.add_argument("--durum", default="/var/lib/1l3a-paper/durum")
    ap.add_argument("--ct", default=os.environ.get("L3A_CT_DURUM"))
    ap.add_argument("--aday", default=os.environ.get("L3A_ADAY_DURUM"))
    ap.add_argument("--cikti", default=None)
    ap.add_argument("--md", default=None)
    a = ap.parse_args(argv)
    c = yaz(Path(a.durum), a.ct, a.aday, a.cikti, a.md)
    print(f"mutabakat: {c['ozet']['islem_sayisi']} işlem, {c['ozet']['uyusmazlik_sayisi']} uyuşmazlık")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
