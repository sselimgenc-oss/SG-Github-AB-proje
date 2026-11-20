"""Tarihsel fiyat boşluğu (gap) dağılımı + seans bazlı mum aralığı göstergesi. YALNIZ ÖLÇÜM: limit, çarpan, strateji DEĞİŞMEZ.

Boşluk = |açılış / önceki kapanış - 1|.  Sınıflar:
  hisse (ABD, NYSE seansı; 5m verisi yalnız normal seans): seans kapanışı -> sonraki seans açılışı.
     gece = ardışık iki işlem günü; hafta sonu = Cuma -> Pazartesi; tatil = aradaki başka kapalı gün(ler) (tatil/köprü).
     Beklenen işlem günü (NYSE takvimi) verisi eksikse olay atlanır (veri boşluğu).
  emtia (CME benzeri 5m verisi): ardışık iki mum arasındaki zaman aralığına göre:
     gece = 50 dk-2,5 sa (günlük mola 17:00-18:00 NY); hafta sonu = Cuma kapanışı -> Pazar açılışı (40-60 sa);
     tatil = >= 20 sa'lik diğer kapanışlar (Pazar-Cuma dışı) ve >60 sa; 2,5-20 sa arası = veri boşluğu, atlanır.
  kripto: 1 saatlik ve 1 günlük (UTC) kapanıştan kapanışa mutlak hareket (karşılaştırma).
Mum aralığı: (high-low)/close, 5m mumlar, seans dilimine (normal / genişletilmiş / kapalı) göre.
Kullanım: PYTHONPATH=. python araclar/bosluk_olcum.py [--cikti sonuclar/olcum/bosluk_seans] [--ek-stres]
Veri: yalnız geliştirme dönemi (holdout kilidi veri yükleyicidedir; v2.ham.veri_oku HoldoutSizintisi fırlatır).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CIKTI = KOK / "sonuclar" / "olcum" / "bosluk_seans"
VERI_ADAYLARI = (KOK / "veri" / "mumlar", KOK.parents[2] / "veri" / "mumlar")
ESIKLER = (0.05, 0.10, 0.15, 0.20, 0.25)
SPLIT_ESIGI = 0.40               # bu üstü boşluk hisse bölünmesi (split) kalıntısı sayılıp dışlanır ve ayrı raporlanır
BOSLUK_TURLERI = ("gece", "hafta_sonu", "tatil")


def veri_dizini() -> Path:
    for d in VERI_ADAYLARI:
        if (d / "BTCUSDT").exists():
            return d
    raise FileNotFoundError("veri/mumlar bulunamadı")


def mum_oku(sembol: str, tf: str) -> pd.DataFrame:
    from motor.arastirma import wf_evren as we
    from motor.arastirma.v2 import ham, sabit
    we.veri_ayarla(veri_dizini(), sabit.DONEM)
    return ham.veri_oku(sembol, tf)[0]


def mum_oku_oto(sembol: str) -> tuple:
    """5m varsa 5m, yoksa 1h. -> (mumlar, tf, adim_dk)."""
    try:
        return mum_oku(sembol, "5m"), "5m", 5
    except ValueError:
        return mum_oku(sembol, "1h"), "1h", 60


# ------------------------------------------------------------------ istatistik
def istatistik(olaylar: list) -> dict:
    """olaylar: [(boşluk, sembol, tarih_str), ...] -> dağılım sözlüğü."""
    if not olaylar:
        return {"n": 0}
    g = np.array([o[0] for o in olaylar], dtype=float)
    en_kotu = sorted(olaylar, key=lambda o: -o[0])[:5]
    return {"n": int(len(g)), "ortalama": float(g.mean()), "p50": float(np.percentile(g, 50)), "p90": float(np.percentile(g, 90)),
            "p99": float(np.percentile(g, 99)), "maks": float(g.max()),
            "en_kotu5": [{"sembol": s, "tarih": t, "bosluk": float(b)} for b, s, t in en_kotu],
            "frekans": {f"{int(round(e*100))}": float((g > e).mean()) for e in ESIKLER},
            "adet": {f"{int(round(e*100))}": int((g > e).sum()) for e in ESIKLER}}


# ------------------------------------------------------------------ hisse
def hisse_olaylari(sembol: str, m: pd.DataFrame) -> tuple:
    """-> (olaylar{tur: [(boşluk, sembol, tarih)]}, atlanan_veri_boslugu, split_kalintisi[liste])."""
    from motor.canli.paper_takvim import NY, _hisse_acik_dk_araligi
    ny = m.index.tz_convert(NY)
    d = pd.DataFrame({"acilis": m["acilis"].to_numpy(float), "kapanis": m["kapanis"].to_numpy(float), "gun": ny.date}, index=m.index)
    g = d.groupby("gun").agg(acilis=("acilis", "first"), kapanis=("kapanis", "last"))
    gunler = list(g.index)
    out = {t: [] for t in BOSLUK_TURLERI}
    atlanan, split = 0, []
    for a, b in zip(gunler[:-1], gunler[1:]):
        ara = [a + pd.Timedelta(days=i).to_pytimedelta() for i in range(1, (b - a).days)]
        eksik = [x for x in ara if _hisse_acik_dk_araligi(x) is not None]
        if eksik:                                                    # beklenen işlem günü veride yok -> veri boşluğu
            atlanan += 1
            continue
        fark = (b - a).days
        tur = "gece" if fark == 1 else ("hafta_sonu" if fark == 3 and a.weekday() == 4 else "tatil")
        bos = abs(g.loc[b, "acilis"] / g.loc[a, "kapanis"] - 1)
        if bos > SPLIT_ESIGI:
            split.append({"sembol": sembol, "tarih": str(b), "bosluk": float(bos)})
            continue
        out[tur].append((float(bos), sembol, str(b)))
    return out, atlanan, split


# ------------------------------------------------------------------ emtia
def emtia_olaylari(sembol: str, m: pd.DataFrame, adim: int = 5) -> tuple:
    """Ardışık mumlar arası zaman aralığına göre. -> (olaylar, atlanan_veri_boslugu)."""
    from motor.canli.paper_takvim import NY
    idx = m.index
    dt = np.diff(idx.as_unit("ns").asi8) / 6e10                                  # dakika (açılış-açılış)
    kap = m["kapanis"].to_numpy(float)
    ac = m["acilis"].to_numpy(float)
    ara = dt - float(adim)                                                 # kapanıştan sonraki boş süre (5m mum)
    out = {t: [] for t in BOSLUK_TURLERI}
    atlanan = 0
    ny_gun = idx.tz_convert(NY).weekday.to_numpy()
    for i in np.where(ara > 30)[0]:
        sa = ara[i] / 60
        if 50 / 60 <= sa <= 2.5:
            tur = "gece"
        elif 40 <= sa <= 60 and ny_gun[i] == 4 and ny_gun[i + 1] == 6:
            tur = "hafta_sonu"
        elif sa >= 20:
            tur = "tatil"
        else:
            atlanan += 1
            continue
        out[tur].append((float(abs(ac[i + 1] / kap[i] - 1)), sembol, str(idx[i + 1].date())))
    return out, atlanan


# ------------------------------------------------------------------ kripto
def kripto_hareketleri(sembol: str, m: pd.DataFrame) -> dict:
    s = m["kapanis"].astype(float)
    sa = s.resample("1h").last().dropna()
    gn = s.resample("1D").last().dropna()
    h1 = (sa / sa.shift(1) - 1).abs().dropna()
    d1 = (gn / gn.shift(1) - 1).abs().dropna()
    return {"1sa": [(float(v), sembol, str(t)) for t, v in h1.items()], "1gun": [(float(v), sembol, str(t.date())) for t, v in d1.items()]}


# ------------------------------------------------------------------ seans dilimine göre mum aralığı
def dilim_etiketle(sembol: str, index: pd.DatetimeIndex) -> np.ndarray:
    from motor.canli.paper_takvim import seans_dilimi, seans_maskesi, tur
    ac = seans_maskesi(sembol, index)
    out = np.where(ac, "normal", "kapali").astype(object)
    if tur(sembol) == "hisse":                                     # normal dışı mumlar için genişletilmiş/kapalı ayrımı (az sayıda)
        for i in np.where(~ac)[0]:
            out[i] = seans_dilimi(sembol, index[i])
    return out


def aralik_dilim(sembol: str, m: pd.DataFrame) -> dict:
    r = ((m["yuksek"] - m["dusuk"]) / m["kapanis"]).to_numpy(float)
    d = dilim_etiketle(sembol, m.index)
    out = {}
    for k in ("normal", "genisletilmis", "kapali"):
        x = r[d == k]
        out[k] = {"n": int(len(x)), "toplam": float(x.sum())}
    return out


def aralik_saat(m: pd.DataFrame) -> dict:
    """Dolaylı gösterge: NY saatine göre ort. aralık (emtia: Asya gecesi vs ABD gündüzü; hisse: açılış 15 dk vs gün ortası)."""
    from motor.canli.paper_takvim import NY
    r = ((m["yuksek"] - m["dusuk"]) / m["kapanis"]).to_numpy(float)
    ny = m.index.tz_convert(NY)
    h = (ny.hour * 60 + ny.minute).to_numpy()
    kov = {"asya_gece_19_03": (h >= 19 * 60) | (h < 3 * 60), "avrupa_03_08": (h >= 180) & (h < 480),
           "abd_08_30_16": (h >= 510) & (h < 960), "abd_acilis_ilk_15dk": (h >= 570) & (h < 585),
           "abd_gun_ortasi_11_14": (h >= 660) & (h < 840), "abd_son_30dk": (h >= 930) & (h < 960)}
    return {k: {"n": int(v.sum()), "toplam": float(r[v].sum())} for k, v in kov.items()}


def _topla(parcalar: list) -> dict:
    out = {}
    for p in parcalar:
        for k, v in p.items():
            o = out.setdefault(k, {"n": 0, "toplam": 0.0})
            o["n"] += v["n"]
            o["toplam"] += v["toplam"]
    return {k: {"n": v["n"], "ort_aralik_yuzde": (v["toplam"] / v["n"] * 100) if v["n"] else None} for k, v in out.items()}


def ek_stres(ham_yolu: Path, bosluklar=(0.20, 0.25)) -> dict:
    """%20/%25 boşluk satırları: araclar/kaldirac_stres.py::ek_bosluk_stresi (mevcut ham_sayilar.json'dan, backtest yeniden koşulmaz)."""
    from araclar.kaldirac_stres import ek_bosluk_stresi
    return ek_bosluk_stresi(Path(ham_yolu), bosluklar)


# ------------------------------------------------------------------ ana akış
def calistir(sembol_sinirla=None) -> dict:
    from motor.arastirma import wf_evren as we
    from motor.canli.paper_takvim import ABD_HISSELERI, EMTIALAR
    hisse = [s for s in we.HISSE if s in ABD_HISSELERI]
    emtia = [s for s in we.EMTIA if s in EMTIALAR]
    kripto = list(we.KRIPTO)
    if sembol_sinirla:
        hisse, emtia, kripto = hisse[:sembol_sinirla], emtia[:sembol_sinirla], kripto[:sembol_sinirla]
    ham = {"hisse": {t: [] for t in BOSLUK_TURLERI}, "emtia": {t: [] for t in BOSLUK_TURLERI}}
    atlanan = {"hisse": 0, "emtia": 0}
    split, aralik, saat = [], {"hisse": [], "emtia": [], "kripto": []}, {"hisse": [], "emtia": [], "kripto": []}
    veri_ara = {}
    for s in hisse:
        m, tf, adim = mum_oku_oto(s)
        veri_ara[s] = [str(m.index.min().date()), str(m.index.max().date()), tf]
        o, a, sp = hisse_olaylari(s, m)
        for t in BOSLUK_TURLERI:
            ham["hisse"][t] += o[t]
        atlanan["hisse"] += a
        split += sp
        if tf == "5m":
            aralik["hisse"].append(aralik_dilim(s, m))
            saat["hisse"].append(aralik_saat(m))
        print("hisse", s, flush=True)
    for s in emtia:
        m, tf, adim = mum_oku_oto(s)
        veri_ara[s] = [str(m.index.min().date()), str(m.index.max().date()), tf]
        o, a = emtia_olaylari(s, m, adim)
        for t in BOSLUK_TURLERI:
            ham["emtia"][t] += o[t]
        atlanan["emtia"] += a
        if tf == "5m":
            aralik["emtia"].append(aralik_dilim(s, m))
            saat["emtia"].append(aralik_saat(m))
        print("emtia", s, flush=True)
    k1, kg = [], []
    for s in kripto:
        try:
            m = mum_oku(s, "5m")
        except Exception as e:  # noqa: BLE001
            print("kripto atlandı", s, repr(e)[:80])
            continue
        veri_ara[s] = [str(m.index.min().date()), str(m.index.max().date())]
        h = kripto_hareketleri(s, m)
        k1 += h["1sa"]
        kg += h["1gun"]
        aralik["kripto"].append(aralik_dilim(s, m))
        saat["kripto"].append(aralik_saat(m))
        print("kripto", s, flush=True)
    sonuc = {sinif: {t: istatistik(ham[sinif][t]) for t in BOSLUK_TURLERI} for sinif in ("hisse", "emtia")}
    sonuc["kripto"] = {"1sa": istatistik(k1), "1gun": istatistik(kg)}
    return {"bosluk": sonuc, "atlanan_veri_boslugu": atlanan, "split_dislanan": split, "veri_araligi": veri_ara,
            "seans_dilimi_aralik": {k: _topla(v) for k, v in aralik.items()}, "saat_dilimi_aralik": {k: _topla(v) for k, v in saat.items()},
            "esikler": ESIKLER, "split_esigi": SPLIT_ESIGI}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", default=str(CIKTI))
    ap.add_argument("--ek-stres", action="store_true", help="yalnız %20/%25 stres satırlarını kaldirac_stres ham_sayilar.json'dan türetir")
    ap.add_argument("--stres-ham", default=str(KOK / "sonuclar" / "olcum" / "kaldirac_5x_stres" / "ham_sayilar.json"))
    a = ap.parse_args()
    c = Path(a.cikti)
    c.mkdir(parents=True, exist_ok=True)
    if a.ek_stres:
        (c / "ek_stres_ham.json").write_text(json.dumps(ek_stres(Path(a.stres_ham)), ensure_ascii=False, indent=1))
        print("ek stres yazıldı")
        return
    (c / "bosluk_ham.json").write_text(json.dumps(calistir(), ensure_ascii=False, indent=1, default=str))
    print("bitti")


if __name__ == "__main__":
    main()
