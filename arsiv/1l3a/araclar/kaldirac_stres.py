"""Kaldıraç 3x/4x/5x ölçümü + fiyat boşluğu (gap) stres testi. YALNIZ ÖLÇÜM: limit, ayar, strateji, motor kodu DEĞİŞMEZ.

Ne yapar
  1) Paper v2 setini (stratejiler/paper_v2_seti.json, 10 hesap; her biri KENDİ kasasında) `motor/portfoy` birleşik motoruyla
     (birlesik_backtest ile aynı çekirdek `_Motor`) koşar; brüt nominal tavanı K = 3/4/5. Motorun sert limit tavanı (3x) yalnız bu
     araçta, çağrı süresince `motor.portfoy.motor.SERT_LIMITLER` yerine geçici kopya konarak gevşetilir (testlerin de kullandığı
     yöntem); `motor/risk/limitler.py` ve `motor/canli/**` DEĞİŞMEZ. Başka her şey aynı veri ve aynı maliyet tablosu (v2).
  2) İki boyut profili:  "paper"  = paper boyutu (işlem başı %0,5 risk, toplam stop riski %5, günlük %5, kill %20);
                         "canli"  = canlı-benzeri (işlem başı %1,5 risk, toplam stop riski %6, günlük %5, kill %30).
     Tek fark kaldıraç tavanı K'dır. Canlı marj kuralı (işlem başı marj <= %50) motorda YOKTUR; ihlal ölçülür, uygulanmaz.
  3) Boşluk stresi: her açık pozisyon AYNI ANDA g (%5/%10/%15) ters sıçrar (long düşer, short yükselir), stop boşlukla dolar.
     Tek günlük kasa kaybı = brüt nominal / özsermaye x g (her pozisyon mark fiyatından g kadar ters). Uygulandığı an: backtest
     geçmişinin en yüksek brüt maruziyetli barları (hesap başına) ve 10 hesabın gün-içi-tepe toplamı (üst sınır).
Kullanım:  PYTHONPATH=. python araclar/kaldirac_stres.py [--isci 4] [--bas 2020-01-01] [--bit 2025-11-07] [--sadece AD]
           [--profil paper,canli] [--cikti sonuclar/olcum/kaldirac_5x_stres]
Veri: yalnız geliştirme dönemi (<= 2025-11-07; holdout okunmaz, veri_oku HoldoutSizintisi fırlatır).
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import dataclasses
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CIKTI = KOK / "sonuclar" / "olcum" / "kaldirac_5x_stres"
VERI_DIZINI_ADAYLARI = (KOK / "veri" / "mumlar", KOK.parents[2] / "veri" / "mumlar")
KALDIRACLAR = (3, 4, 5)
BOSLUKLAR = (0.05, 0.10, 0.15)
MMR = 0.005                       # varsayım: bakım marjı oranı (Binance USDⓈ-M küçük kademe ~%0,4-0,5)
PROFILLER = {
    "paper": dict(risk_yuzde=0.5, toplam_risk=5.0, kill=20.0, gunluk=5.0),
    "canli": dict(risk_yuzde=1.5, toplam_risk=6.0, kill=30.0, gunluk=5.0),
    # duyarlılık: CANLI_LIMITLER'in izin verdiği EN YÜKSEK işlem başı kayıp (%3); kaldıraç tavanının bağlayıp bağlamadığını görmek için
    "canli3": dict(risk_yuzde=3.0, toplam_risk=6.0, kill=30.0, gunluk=5.0),
}
GUNLUK_ESIK = -5.0


def veri_dizini() -> Path | None:
    for d in VERI_DIZINI_ADAYLARI:
        if (d / "BTCUSDT").exists():
            return d
    raise FileNotFoundError("veri/mumlar bulunamadı")


@contextlib.contextmanager
def limit_gevset(K: float, prof: dict):
    """Ölçüm süresince motor modülündeki sert limit kopyasını değiştirir (dosyadaki SERT_LIMITLER değişmez)."""
    from motor.portfoy import motor as pm
    eski = pm.SERT_LIMITLER
    pm.SERT_LIMITLER = dataclasses.replace(
        eski, max_kaldirac=float(K), islem_basi_max_risk_yuzde=prof["risk_yuzde"],
        portfoy_toplam_risk_yuzde=prof["toplam_risk"], kill_switch_dusus_yuzde=prof["kill"],
        gunluk_max_kayip_yuzde=prof["gunluk"])
    try:
        yield
    finally:
        pm.SERT_LIMITLER = eski


def veri_hazirla(h: dict, bas, bit):
    """-> (veriler, fundingler, maliyet_sembol). Isınma payı için `bas`tan önce veri okunur (yeni pozisyon `bas`a kadar açılmaz)."""
    from motor.arastirma import evren_maliyet
    from motor.arastirma import wf_evren as we
    from motor.arastirma.v2 import ham as hm
    from motor.arastirma.v2 import sabit
    we.veri_ayarla(veri_dizini(), sabit.DONEM)
    on = pd.Timestamp(bas, tz="UTC") - pd.Timedelta(days=(500 if h["tf"] == "1d" else 120))
    son = pd.Timestamp(bit, tz="UTC") + pd.Timedelta(days=1)         # bit dahil
    veriler, fund, ms = {}, {}, {}
    ev = sabit.evren_listesi("kripto" if h["evren"] in ("kripto", "kripto13") else "genel")
    for s in ev:
        try:
            m, f = hm.veri_oku(s, h["tf"])
        except (FileNotFoundError, ValueError):
            continue
        m = m[(m.index >= on) & (m.index < son)]
        if not len(m):
            continue
        veriler[s] = m.drop(columns="eksik") if "eksik" in m.columns else m
        if f is not None and len(f):
            fund[s] = f[(f.index >= on) & (f.index < son)]
        elif s.startswith("DK_"):                                    # TradFi varsayım funding'i (v2 ON_KAYIT 1.2; paper ile aynı)
            idx = pd.date_range(m.index[0].floor("D"), m.index[-1].ceil("D") + pd.Timedelta(days=1), freq="8h", tz="UTC")
            fund[s] = pd.DataFrame({"oran": np.full(len(idx), sabit.FUNDING_LONG_8S_ORAN)}, index=idx)
        ms[s] = evren_maliyet.sembol_maliyeti(s, 1.0, KOK / "sonuclar" / "evren" / "v2" / "maliyet_tablosu_v2.csv")
    return veriler, fund, ms


def kollari_kur(h: dict, veriler: dict):
    """birlesik_backtest ile aynı kol kurulumu (sinyaller bir kez hesaplanır, koşular arasında paylaşılır)."""
    from motor.portfoy import birlesik as bl
    from motor.portfoy.temel import ortak_eksen
    from motor.strateji import funding
    from araclar import risk_senaryo_kos as rk
    st = rk._kur(h)
    eksen = ortak_eksen(veriler)
    kollar = []
    for no, s in enumerate(veriler):
        mumlar = funding.stratejiye_hazirla(st, veriler[s], None, s)
        kollar.append(bl._kol_kur(no, st, s, mumlar, eksen))
    return kollar, eksen


def tek_kos(veriler, fund, ms, kollar, eksen, K, prof, bas):
    from motor.portfoy.motor import PortfoyAyarlari, _Motor
    ay = PortfoyAyarlari(
        baslangic_sermaye=10000.0, risk_yuzde=prof["risk_yuzde"], kaldirac=float(K), limit_modu="uygula",
        toplam_risk_tavani_yuzde=prof["toplam_risk"], maliyet_sembol=ms,
        komisyon_taker_yuzde=max(v[0] for v in ms.values()), komisyon_maker_yuzde=max(v[1] for v in ms.values()),
        kayma_bps=max(v[2] for v in ms.values()), stop_kayma_bps=max(v[3] for v in ms.values()))
    kl = [dataclasses.replace(k) for k in kollar]
    with limit_gevset(K, prof):
        return _Motor(veriler, kl, ay, fund, eksen, pd.Timestamp(bas, tz="UTC")).calistir()


def metrikler(sonuc, K: int, bas) -> tuple:
    """-> (özet sözlüğü, stres için günlük/bar verisi)."""
    oz = sonuc.ozsermaye
    oz = oz[oz.index >= pd.Timestamp(bas, tz="UTC")]
    b0 = sonuc.baslangic_sermaye
    tepe = oz.cummax()
    dd = float(((oz - tepe) / tepe).min())
    gun = sonuc.gunluk_ozsermaye
    gun = gun[gun.index >= pd.Timestamp(bas, tz="UTC").floor("D")]
    gget = gun.pct_change().dropna() * 100
    gget = pd.concat([pd.Series([(gun.iloc[0] / b0 - 1) * 100], index=gun.index[:1]), gget]) if len(gun) else gget
    isl = sonuc.islemler
    kayip_orani, en_kotu_r = None, None
    if len(isl):
        e_giris = oz.reindex(pd.DatetimeIndex(isl["giris_zamani"]), method="ffill").to_numpy()
        e_giris = np.where(np.isnan(e_giris), b0, e_giris)
        oran = isl["net_pnl"].to_numpy(dtype=float) / e_giris * 100
        i = int(np.argmin(oran))
        kayip_orani = {"yuzde": float(oran[i]), "sembol": str(isl.iloc[i]["sembol"]), "zaman": str(isl.iloc[i]["giris_zamani"]),
                       "r": float(isl.iloc[i]["r"]), "cikis_nedeni": str(isl.iloc[i]["cikis_nedeni"])}
        en_kotu_r = float(isl["r"].min())
    ol = sonuc.limit_olaylari
    gun_olay = sorted({str(pd.Timestamp(o["zaman"]).date()) for o in ol if o["tur"] == "gunluk_kayip"})
    kill = [o for o in ol if o["tur"] == "kill_switch"]
    mr = sonuc.maruziyet[sonuc.maruziyet.index >= pd.Timestamp(bas, tz="UTC")]
    ag = sonuc.agirlik_gecmisi.reindex(mr.index).abs()
    tek_max = float(ag.max().max()) if len(ag) else 0.0
    brut_max = float(mr["brut"].max()) if len(mr) else 0.0
    ozet = {
        "K": K, "islem_sayisi": int(len(isl)),
        "toplam_getiri_yuzde": float((oz.iloc[-1] / b0 - 1) * 100) if len(oz) else 0.0,
        "max_dd_yuzde": dd * 100,
        "gunluk_esik_gun_olcum": int((gget <= GUNLUK_ESIK).sum()),         # gün sonu MTM <= -%5 olan UTC günleri
        "gunluk_limit_olayi": len(gun_olay),                               # motorun gün içi limit tetiklenmesi (bar bazlı)
        "kill_tetik": len(kill), "kill_zaman": str(kill[0]["zaman"]) if kill else None,
        "en_kotu_gun_yuzde": float(gget.min()) if len(gget) else 0.0,
        "en_kotu_gun": str(gget.idxmin().date()) if len(gget) else None,
        "en_kotu_islem": kayip_orani, "en_kotu_islem_r": en_kotu_r,
        "brut_max": brut_max, "marj_kullanim_max_yuzde": brut_max / K * 100,
        "tek_poz_nominal_max": tek_max,
        "marj_50_asan_bar_sayisi": int(((ag > 0.5 * K).any(axis=1)).sum()) if len(ag) else 0,
        "marj_50_asan_poz_marj_yuzde_max": tek_max / K * 100,
        "esik_gun_listesi_ilk5": gun_olay[:5], "uyari_sayisi": len(sonuc.uyarilar),
        "uyarilar_ilk3": sonuc.uyarilar[:3],
    }
    # stres verisi: bar bazında brüt/özsermaye; en yüksek 25 bar + gün-içi tepe nominal (10 hesap toplamı için)
    brut = mr["brut"]
    oz_b = sonuc.ozsermaye.reindex(brut.index)
    notl = brut * oz_b
    ust = brut.sort_values(ascending=False).head(25)
    gday = pd.DataFrame({"notl": notl, "oz": oz_b}).groupby(brut.index.floor("D")).agg(notl_max=("notl", "max"), oz_son=("oz", "last"))
    stres = {
        "en_yuksek_brut": [{"zaman": str(t), "brut": float(v), "poz_sayisi": int(mr.loc[t, "pozisyon_sayisi"]),
                            "net": float(mr.loc[t, "net"]), "ozsermaye": float(oz_b.loc[t])} for t, v in ust.items()],
        "gunluk": gday,
    }
    return ozet, stres


def boslukla_kayip(brut: float, g: float) -> float:
    """Tek günlük kasa kaybı (özsermaye %'si): tüm pozisyonlar mark fiyatından g kadar ters."""
    return brut * g * 100


def hesap_kos(arg):
    h, bas, bit, profiller = arg
    t0 = time.time()
    veriler, fund, ms = veri_hazirla(h, bas, bit)
    if not veriler:
        return h["id"], {"hata": "veri yok"}, {}
    kollar, eksen = kollari_kur(h, veriler)
    sonuc, stres = {}, {}
    for pad in profiller:
        for K in KALDIRACLAR:
            r = tek_kos(veriler, fund, ms, kollar, eksen, K, PROFILLER[pad], bas)
            o, s = metrikler(r, K, bas)
            sonuc[f"{pad}|{K}"] = o
            stres[f"{pad}|{K}"] = s
            print(f"{h['id']} {pad} K={K}: getiri {o['toplam_getiri_yuzde']:.1f}% dd {o['max_dd_yuzde']:.1f}% "
                  f"işlem {o['islem_sayisi']} ({time.time()-t0:.0f}s)", flush=True)
    return h["id"], {"sembol_sayisi": len(veriler), "bar": int(len(eksen)), "tf": h["tf"], "sonuc": sonuc, "sure_sn": time.time() - t0}, stres


def stres_derle(stres_hesap: dict, profiller) -> dict:
    """Hesap başına en kötü an + 10 hesap birleşik (gün-içi tepe toplamı) için boşluk x kaldıraç kasa kaybı tablosu."""
    out = {}
    for pad in profiller:
        for K in KALDIRACLAR:
            anahtar = f"{pad}|{K}"
            hesaplar, gunluk = {}, []
            for hid, st in stres_hesap.items():
                if anahtar not in st:
                    continue
                en = st[anahtar]["en_yuksek_brut"]
                tepe = en[0] if en else {"brut": 0.0}
                hesaplar[hid] = {
                    "tepe_brut": tepe["brut"], "tepe_zaman": tepe.get("zaman"), "tepe_poz_sayisi": tepe.get("poz_sayisi"),
                    "kayip_yuzde": {f"{int(g*100)}": boslukla_kayip(tepe["brut"], g) for g in BOSLUKLAR},
                    "likidasyon_boslugu_yuzde": (100.0 / tepe["brut"] - 100 * MMR) if tepe["brut"] > 0 else None,
                    "marj_kullanim_yuzde": tepe["brut"] / K * 100}
                gunluk.append(st[anahtar]["gunluk"])
            if not gunluk:
                continue
            df = pd.concat([g.rename(columns=lambda c, i=i: f"{c}_{i}") for i, g in enumerate(gunluk)], axis=1)
            notl = df[[c for c in df.columns if c.startswith("notl_max")]].sum(axis=1)
            oz = df[[c for c in df.columns if c.startswith("oz_son")]].ffill().sum(axis=1)
            br = (notl / oz).replace([np.inf, -np.inf], np.nan).dropna()
            t = br.idxmax()
            top = br.sort_values(ascending=False).head(5)
            out[anahtar] = {
                "hesaplar": hesaplar,
                "birlesik_en_kotu_gun": str(t.date()), "birlesik_brut": float(br.max()),
                "birlesik_kayip_yuzde": {f"{int(g*100)}": boslukla_kayip(float(br.max()), g) for g in BOSLUKLAR},
                "birlesik_ilk5_gun": {str(k.date()): float(v) for k, v in top.items()},
                "hesap_kayip_max_yuzde": {f"{int(g*100)}": max(v["kayip_yuzde"][f"{int(g*100)}"] for v in hesaplar.values()) for g in BOSLUKLAR},
            }
    return out


def ek_bosluk_stresi(ham_yolu: Path, bosluklar=(0.20, 0.25)) -> dict:
    """kaldirac_stres.py çıktısındaki tepe brüt değerlerinden yeni boşluk satırları (backtest yeniden koşulmaz; kayıp = brüt x g).
    Likidasyon: tek pozisyon izole marj (eşik 1/K - MMR) ve hesap bazında (eşik 1/brüt - MMR)."""
    ham = json.loads(Path(ham_yolu).read_text())
    out = {}
    for anahtar, v in ham["bosluk_stresi"].items():
        pad, K = anahtar.split("|")
        K = int(K)
        hes = {hid: h["tepe_brut"] for hid, h in v["hesaplar"].items()}
        en_kotu_hid = max(hes, key=hes.get)
        satir = {}
        for g in bosluklar:
            hk = boslukla_kayip(hes[en_kotu_hid], g)
            bk = boslukla_kayip(v["birlesik_brut"], g)
            satir[f"{int(round(g*100))}"] = {
                "en_kotu_hesap": en_kotu_hid, "en_kotu_hesap_brut": hes[en_kotu_hid], "en_kotu_hesap_kayip_yuzde": hk,
                "birlesik_brut": v["birlesik_brut"], "birlesik_kayip_yuzde": bk,
                "tek_poz_likidasyon_esigi_yuzde": (1 / K - MMR) * 100, "tek_poz_likide": bool(g > 1 / K - MMR),
                "tek_poz_marj_kaybi_yuzde": g * K * 100,
                "hesap_likidasyon_esigi_yuzde": (1 / hes[en_kotu_hid] - MMR) * 100,
                "hesap_likide_en_kotu": bool(g > 1 / hes[en_kotu_hid] - MMR),
                "hesap_likide_birlesik": bool(g > 1 / v["birlesik_brut"] - MMR),
                "kasa_kaybi_100_asar_en_kotu": bool(hk >= 100)}
        out[anahtar] = satir
    return out


def ozet_tablolari(ham: dict) -> str:
    """ham_sayilar.json -> Türkçe özet tabloları (yalnız sayılar; yorum OZET.md'ye elle eklenir)."""
    hes = ham["hesaplar"]
    satir = []
    for pad in sorted({k.split("|")[0] for h in hes.values() for k in h.get("sonuc", {})}):
        satir += [f"### Profil: {pad} (risk %{PROFILLER[pad]['risk_yuzde']}/işlem)", "",
                  "| K | ort. getiri % | en kötü hesap DD % | ort. DD % | gün-sonu <=-%5 gün (toplam) | gün-içi limit olayı | kill (hesap) "
                  "| en kötü gün % | en kötü işlem % | maks brüt | maks tek poz (x kasa) | tek poz >0,5K olan bar | işlem sayısı |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for K in KALDIRACLAR:
            r = [h["sonuc"][f"{pad}|{K}"] for h in hes.values() if f"{pad}|{K}" in h.get("sonuc", {})]
            if not r:
                continue
            kotu = min((x["en_kotu_islem"]["yuzde"] for x in r if x["en_kotu_islem"]), default=0.0)
            satir.append(f"| {K}x | {np.mean([x['toplam_getiri_yuzde'] for x in r]):.1f} | {min(x['max_dd_yuzde'] for x in r):.1f} "
                         f"| {np.mean([x['max_dd_yuzde'] for x in r]):.1f} | {sum(x['gunluk_esik_gun_olcum'] for x in r)} "
                         f"| {sum(x['gunluk_limit_olayi'] for x in r)} | {sum(x['kill_tetik'] for x in r)}/{len(r)} "
                         f"| {min(x['en_kotu_gun_yuzde'] for x in r):.1f} | {kotu:.1f} | {max(x['brut_max'] for x in r):.2f} "
                         f"| {max(x['tek_poz_nominal_max'] for x in r):.2f} | {sum(x['marj_50_asan_bar_sayisi'] for x in r)} | {sum(x['islem_sayisi'] for x in r)} |")
        satir.append("")
    satir += ["### Boşluk stresi: tek günlük kasa kaybı (% özsermaye), en kötü an", "",
              "| profil | K | boşluk | hesap başına en kötü | 10 hesap birleşik (gün-içi tepe, üst sınır) | birleşik brüt | likidasyon boşluğu % (en kötü hesap) |",
              "|---|---|---|---|---|---|---|"]
    for anahtar, v in ham["bosluk_stresi"].items():
        pad, K = anahtar.split("|")
        lik = min((h["likidasyon_boslugu_yuzde"] for h in v["hesaplar"].values() if h["likidasyon_boslugu_yuzde"]), default=float("nan"))
        for g in ("5", "10", "15"):
            satir.append(f"| {pad} | {K}x | %{g} | {v['hesap_kayip_max_yuzde'][g]:.1f} | {v['birlesik_kayip_yuzde'][g]:.1f} "
                         f"| {v['birlesik_brut']:.2f} | {lik:.1f} |")
    return "\n".join(satir) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ozet-yaz", action="store_true", help="ham_sayilar.json'dan tabloları basar (koşu yapmaz)")
    ap.add_argument("--isci", type=int, default=4)
    ap.add_argument("--bas", default="2020-01-01")
    ap.add_argument("--bit", default="2025-11-07")
    ap.add_argument("--sadece", default="")
    ap.add_argument("--profil", default="paper,canli")
    ap.add_argument("--cikti", default=str(CIKTI))
    ap.add_argument("--ek-bosluk", default="", help="örn. 0.20,0.25: mevcut ham_sayilar.json'dan ek boşluk satırları (koşu yapmaz), ek_bosluk_stresi.json yazar")
    a = ap.parse_args()
    if a.ek_bosluk:
        ek = ek_bosluk_stresi(Path(a.cikti) / "ham_sayilar.json", tuple(float(x) for x in a.ek_bosluk.split(",")))
        (Path(a.cikti) / "ek_bosluk_stresi.json").write_text(json.dumps(ek, ensure_ascii=False, indent=1))
        print(json.dumps(ek, ensure_ascii=False, indent=1))
        return
    if a.ozet_yaz:
        print(ozet_tablolari(json.loads((Path(a.cikti) / "ham_sayilar.json").read_text())))
        return
    from araclar import risk_senaryo_kos as rk
    hes = rk.hesap_listesi()
    if a.sadece:
        hes = [h for h in hes if any(x in h["id"] for x in a.sadece.split(","))]
    profiller = a.profil.split(",")
    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    gor = [(h, a.bas, a.bit, profiller) for h in hes]
    # ağır (kısa tf) hesaplar önce
    gor.sort(key=lambda x: {"5m": 0, "15m": 1}.get(x[0]["tf"], 2))
    sonuc, stres = {}, {}
    t0 = time.time()
    with mp.Pool(min(a.isci, len(gor))) as p:
        for hid, s, st in p.imap_unordered(hesap_kos, gor, chunksize=1):
            sonuc[hid] = s
            stres[hid] = st
            (cikti / "_kismi.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str))
    boslukluk = stres_derle(stres, profiller)
    ham = {"parametreler": {"bas": a.bas, "bit": a.bit, "kaldiraclar": KALDIRACLAR, "bosluklar": BOSLUKLAR, "mmr": MMR,
                            "profiller": PROFILLER, "set_imza": "fffbc6624416634e"},
           "hesaplar": sonuc, "bosluk_stresi": boslukluk, "sure_sn": time.time() - t0}
    (cikti / "ham_sayilar.json").write_text(json.dumps(ham, ensure_ascii=False, indent=1, default=str))
    (cikti / "_kismi.json").unlink(missing_ok=True)
    print("bitti", time.time() - t0)


if __name__ == "__main__":
    main()
