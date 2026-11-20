"""300 USD hesap, CANLI limitlerle olay sıralı yeniden oynatma (plan: sonuclar/canli_oynatma_300/PLAN.md).

Boyutlandırma gerçek koddan gelir: motor.canli.borsa.kurallar.boyutlandir (-> canli_limitler.miktar_hesapla/limit_ihlalleri);
günlük/kill durumu canli_limitler.gunluk_kill_guncelle. Borsa filtreleri depoda yok: kaba varsayım (FILTRE_* sabitleri).
Kullanım: python araclar/canli_oynatma_300.py
"""
from __future__ import annotations

import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from motor.canli.borsa import canli_limitler as cl  # noqa: E402
from motor.canli.borsa.kurallar import SembolKurali, boyutlandir  # noqa: E402

D = Decimal
BAS, BIT = pd.Timestamp("2020-01-01"), pd.Timestamp("2025-11-07")
YIL = (BIT - BAS).days / 365.25
TAHSIS = D(300)
STOP_KAYMA, TAKER = D("0.0005"), D("0.0005")           # yürütücü varsayılanı (canli_yurutucu.py)
# Varsayım (exchangeInfo görüntüsü depoda yok): min tutar USD ve adım
MIN_TUTAR = {"BTCUSDT": D(100), "ETHUSDT": D(20)}
MIN_TUTAR_VARSAYILAN = D(5)
ADIM = {"BTCUSDT": D("0.001"), "ETHUSDT": D("0.001"), "BNBUSDT": D("0.01"), "SOLUSDT": D("0.01"), "ZECUSDT": D("0.01"),
        "LINKUSDT": D("0.01"), "BCHUSDT": D("0.001"), "HYPEUSDT": D("0.01")}
ADIM_VARSAYILAN = D("1")                                # ADA, XRP, XLM, TRX, DOGE
ADIM_DK = D("0.01")                                      # DK_* (hisse/emtia): kesirli kabul

STRATEJILER = {
    "gauss": "dis__gauss-stoch-eth", "hma": "dis__hma-atr-rider", "664": "kap_HAM_X005_664_v1", "705": "kap_HAM_X005_705",
    "ewo": "dis__ewo-ema-ofset", "e0v1en": "dis__e0v1en", "670": "kap_HAM_B001_670_v1", "574": "kap_HAM_B001_574_v1",
}
BIRLESIK = ["ewo", "e0v1en", "gauss", "hma", "664"]
NEDENLER = ["stop_cok_uzak", "toplam_risk", "brut_nominal", "min_tutar_gercek", "gunluk_stop", "kill", "diger"]
BUTCE = {"toplam_risk": "toplam_risk", "brut": "brut_nominal"}   # miktarı sınırlayan (baglayan) bütçe kuralı -> neden etiketi


def neden_etiketi(b) -> str:
    """Canlı boyutlandırmanın `neden` + `baglayan` alanından atlama etiketi. min_tutar_alti, bütçe (toplam risk / brüt) kırıntısı bıraktığında
    canlı kod bunu yine de `min_tutar_alti` diye işler (yanıltıcı); burada gerçek bağlayan kurala göre ayrılır."""
    if b.neden == "stop_cok_uzak":
        return "stop_cok_uzak"
    if b.neden in ("risk_butcesi_dolu", "min_tutar_alti") and b.baglayan in BUTCE:
        return BUTCE[b.baglayan]
    if b.neden == "min_tutar_alti":
        return "min_tutar_gercek"                       # bağlayan: kayıp / nominal / marj (diğer pozisyonlardan bağımsız)
    return "diger"


def kural(sembol: str) -> SembolKurali:
    if sembol.startswith("DK_"):
        adim, mt = ADIM_DK, MIN_TUTAR_VARSAYILAN
    else:
        adim, mt = ADIM.get(sembol, ADIM_VARSAYILAN), MIN_TUTAR.get(sembol, MIN_TUTAR_VARSAYILAN)
    return SembolKurali(sembol, D("0.0001"), adim, adim, D("1e12"), adim, adim, D("1e12"), mt)


def _naif(x) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo is not None else t


def oynat(islem: pd.DataFrame, risk: float, sermaye: float = 300.0, bas=BAS, bit=BIT, tahsis=None) -> dict:
    """islem: giris_zamani, cikis_zamani, yon, r, sf, stop_mesafe, sembol. -> sonuç sözlüğü (olaylar = [(zaman, özsermaye)])."""
    bas, bit = _naif(bas), _naif(bit)
    df = islem.copy()
    df["g"] = df["giris_zamani"].map(_naif)
    df["c"] = df["cikis_zamani"].map(_naif)
    df = df[(df["g"] >= bas) & (df["c"] < bit + pd.Timedelta(days=1))].reset_index(drop=True)   # zorunlu kapanışlar hariç
    ev = []
    for i, t in df.iterrows():
        ev.append((t["g"], 1, i))
        ev.append((t["c"], 0, i))
    ev.sort(key=lambda x: (x[0], x[1], x[2]))
    E = D(str(sermaye))
    durum, acik = {}, {}                                  # acik: i -> (sembol, qty, giris, stop_mesafe)
    neden, tam, kisa, olaylar = Counter(), 0, 0, [(bas, float(E))]
    ayrinti = Counter()
    ir = D(str(risk))
    tahsis = D(str(sermaye)) if tahsis is None else D(str(tahsis))
    ayrinti_b = Counter()
    for t, tur, i in ev:
        gun = t.strftime("%Y-%m-%d")
        if tur == 0:
            if i not in acik:
                continue
            _, qty, _, sm = acik.pop(i)
            pnl = qty * D(str(float(sm))) * D(str(float(df.at[i, "r"])))
            E = max(E + pnl, D(0))
            cl.gunluk_kill_guncelle(durum, min(E, tahsis), gun)   # canlı: kasa = min(özsermaye, tahsis)
            olaylar.append((t, float(E)))
            continue
        cl.gunluk_kill_guncelle(durum, min(E, tahsis), gun)   # canlı: kasa = min(özsermaye, tahsis)
        row = df.loc[i]
        if durum.get("kill"):
            neden["kill"] += 1
            continue
        if durum.get("gun_blok"):
            neden["gunluk_stop"] += 1
            continue
        sm, sf, yon, sem = float(row["stop_mesafe"]), float(row["sf"]), int(row["yon"]), row["sembol"]
        if E <= 0 or sf <= 0 or sm <= 0:
            neden["diger"] += 1
            ayrinti["kasa_veya_veri"] += 1
            continue
        if any(a[0] == sem for a in acik.values()):
            neden["diger"] += 1
            ayrinti["ayni_sembol_acik"] += 1
            continue
        giris = D(str(sm / sf))
        stop = giris - yon * D(str(sm))
        k = kural(sem)
        brut = sum((a[1] * a[2] for a in acik.values()), D(0))
        # Canlı _risk_ozeti de açık riski MALİYETSİZ sayar: (mark - stop) x qty (mark ile; replay'de fiyat yolu yok, giriş fiyatı/stop mesafesi). Yeni işlem ise maliyetle boyutlanır: canlıyla aynı tutarsızlık, bilerek korundu.
        rsk = sum((a[1] * a[3] for a in acik.values()), D(0))
        ortak = dict(ozsermaye=E, tahsis=tahsis, islem_risk=ir, yon=yon, giris=giris, stop=stop, kural=k, stop_kayma=STOP_KAYMA, taker=TAKER)
        b = boyutlandir(diger_brut=brut, diger_stop_riski=rsk, **ortak)
        if b.neden is not None:
            n = neden_etiketi(b)
            neden[n] += 1
            ayrinti_b[f"{b.neden}/{b.baglayan}"] += 1
            if n == "diger":
                ayrinti[b.neden] += 1
            continue
        solo = boyutlandir(**ortak)
        if solo.qty > 0 and b.qty < solo.qty:
            kisa += 1
        else:
            tam += 1
        acik[i] = (sem, b.qty, giris, D(str(sm)))
    toplam = len(df)
    eq = np.array([e for _, e in olaylar])
    tepe = np.maximum.accumulate(eq)
    dd = float(((eq - tepe) / tepe).min()) if len(eq) else 0.0
    son = float(eq[-1])
    return {"sinyal": toplam, "tam": tam, "kisaltilmis": kisa, "neden": {n: neden.get(n, 0) for n in NEDENLER},
            "diger_ayrinti": dict(ayrinti), "ham_neden": dict(ayrinti_b), "alinan": tam + kisa, "alinan_pay": (tam + kisa) / toplam if toplam else 0.0,
            "cagr": (son / sermaye) ** (1 / YIL) - 1 if son > 0 else -1.0, "max_dd": dd, "son": son,
            "kill": bool(durum.get("kill")), "olaylar": olaylar}


def birlestir(sonuclar: list, sermaye_her: float = 300.0) -> dict:
    """Her strateji kendi hesabıyla; olay zamanlarında özsermaye toplamı (ileri doldurma). Hesap kill (-%20) uygulanmaz, yalnız bakılır."""
    ser = []
    for s in sonuclar:
        t, e = zip(*s["olaylar"])
        ser.append(pd.Series(e, index=pd.DatetimeIndex(t)).groupby(level=0).last())
    idx = sorted(set().union(*[set(x.index) for x in ser]))
    tab = pd.concat([x.reindex(idx).ffill().fillna(sermaye_her) for x in ser], axis=1)
    top = tab.sum(axis=1).to_numpy()
    tepe = np.maximum.accumulate(top)
    dd = float(((top - tepe) / tepe).min())
    bas = sermaye_her * len(sonuclar)
    return {"sinyal": sum(s["sinyal"] for s in sonuclar), "alinan": sum(s["alinan"] for s in sonuclar), "kisaltilmis": sum(s["kisaltilmis"] for s in sonuclar),
            "son": float(top[-1]), "cagr": (top[-1] / bas) ** (1 / YIL) - 1, "max_dd": dd,
            "hesap_kill_tetiklenirdi": bool(dd <= -cl.CANLI_LIMITLER.hesap_kill_oran + 1e-9),
            "strateji_kill": sum(s["kill"] for s in sonuclar)}


def yukle(kimlik: str, carpan: int) -> pd.DataFrame:
    return pd.read_parquet(KOK / "sonuclar" / "risk_senaryo" / "islemler" / f"{kimlik}__x{carpan}.parquet")


def main():
    cikti = KOK / "sonuclar" / "canli_oynatma_300"
    cikti.mkdir(parents=True, exist_ok=True)
    satir, sonuc = [], {}
    for carpan in (1, 2):
        for ad, kim in STRATEJILER.items():
            df = yukle(kim, carpan)
            for risk in (0.005, 0.010, 0.015):
                o = oynat(df, risk)
                sonuc[(ad, carpan, risk)] = o
                satir.append({"strateji": ad, "kimlik": kim, "maliyet": f"x{carpan}", "risk": risk, "sinyal": o["sinyal"], "tam": o["tam"],
                              "kisaltilmis": o["kisaltilmis"], **{f"atla_{n}": o["neden"][n] for n in NEDENLER}, "alinan_pay": round(o["alinan_pay"] * 100, 1),
                              "cagr_pct": round(o["cagr"] * 100, 1), "max_dd_pct": round(o["max_dd"] * 100, 1), "son_ozsermaye": round(o["son"], 1),
                              "kill": "e" if o["kill"] else "h", "diger_ayrinti": str(o["diger_ayrinti"])})
        for risk in (0.005, 0.010, 0.015):
            b = birlestir([sonuc[(a, carpan, risk)] for a in BIRLESIK])
            satir.append({"strateji": "BIRLESIK(" + "+".join(BIRLESIK) + ")", "kimlik": "", "maliyet": f"x{carpan}", "risk": risk, "sinyal": b["sinyal"],
                          "tam": b["alinan"] - b["kisaltilmis"], "kisaltilmis": b["kisaltilmis"], "alinan_pay": round(100 * b["alinan"] / b["sinyal"], 1),
                          "cagr_pct": round(b["cagr"] * 100, 1), "max_dd_pct": round(b["max_dd"] * 100, 1), "son_ozsermaye": round(b["son"], 1),
                          **{f"atla_{n}": sum(sonuc[(a, carpan, risk)]["neden"][n] for a in BIRLESIK) for n in NEDENLER},
                          "kill": f"strateji_kill={b['strateji_kill']}", "diger_ayrinti": f"hesap_kill_tetiklenirdi={b['hesap_kill_tetiklenirdi']}"})
    pd.DataFrame(satir).to_csv(cikti / "ozet.csv", index=False)
    # hesap büyüklüğü duyarlılığı (x1, %1,5): GERÇEK min tutar atlamaları
    hs = []
    for ad in ("gauss", "hma", "664", "705", "ewo", "e0v1en"):
        df = yukle(STRATEJILER[ad], 1)
        for boy in (300, 600, 1000, 1500):
            o = oynat(df, 0.015, sermaye=boy)
            hs.append({"strateji": ad, "hesap_usd": boy, "sinyal": o["sinyal"], "alinan_pay": round(100 * o["alinan_pay"], 1), "kisaltilmis": o["kisaltilmis"],
                       **{f"atla_{n}": o["neden"][n] for n in NEDENLER}, "cagr_pct": round(o["cagr"] * 100, 1), "max_dd_pct": round(o["max_dd"] * 100, 1)})
    pd.DataFrame(hs).to_csv(cikti / "ozet_hassasiyet.csv", index=False)
    print(pd.DataFrame(hs).to_string())
    print(pd.DataFrame(satir).drop(columns=["kimlik", "diger_ayrinti"]).to_string())


if __name__ == "__main__":
    main()
