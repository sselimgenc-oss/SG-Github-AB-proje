"""Risk senaryosu yeniden oynatma (saf son-işleme; sonuclar/risk_senaryo/PLAN.md).

Aynı işlemler, yalnız pozisyon boyutu değişir. İşlem listesi: giris_zamani, cikis_zamani, r (net R), sf (stop mesafesi / giriş fiyatı).
- Sabit risk f:  pnl = f x özsermaye(giriş) x R
- Tam kasa (D):  notional = özsermaye(giriş); pnl = notional x R x sf
Özsermaye yalnız GERÇEKLEŞMİŞ (çıkış anında işlenir; aynı anda çıkış girişten önce). Eşzamanlı işlemler giriş anındaki
özsermayeye göre boyutlanır. Özsermaye 0'ın altına inmez. Kill: zirveden -%30 -> yeni işlem yok (açıklar kendi çıkışına kadar sürer).
Veri sonunda zorunlu kapatılan (bit+1 gün 00:00 çıkışlı) işlemler gerçek çıkış değildir: HARİÇ tutulur (ayrı duyarlılık: dahil.csv).
Kullanım: python araclar/risk_senaryo.py   (sonuclar/risk_senaryo/ altına ozet/yillik/portfoy/dahil csv yazar; RAPOR.md elle yazılır)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parents[1]
BAS = pd.Timestamp("2020-01-01")                 # ana pencere (tz'siz UTC)
BIT = pd.Timestamp("2025-11-07")
SERMAYE = 10_000.0
KILL = 0.30
SENARYOLAR = {"baz_0.5%": 0.005, "A_1.5%": 0.015, "B_3%": 0.03, "C_5%": 0.05, "D_tamkasa": None}


def _naif(x) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo is not None else t


def oynat_islemler(islem: pd.DataFrame, f, kill=True, sermaye: float = SERMAYE, bas=BAS, bit=BIT) -> dict:
    """f: risk oranı (None = tam kasa). kill: False/None = yok; True/"acik" = açık işlemler kendi çıkışına kadar sürer (ön kayıt kuralı);
    "donuk" = kill anındaki özsermaye dondurulur (duyarlılık). -> dict(olaylar=[(zaman, özsermaye)], kill_tarihi, max_kaldirac, n_alinan, n_atlanan, bitis)."""
    bas, bit = _naif(bas), _naif(bit)
    if len(islem):
        g = islem["giris_zamani"].map(_naif).to_numpy(dtype="datetime64[ns]")
        c = islem["cikis_zamani"].map(_naif).to_numpy(dtype="datetime64[ns]")
        r = islem["r"].to_numpy(dtype=float)
        sf = islem["sf"].to_numpy(dtype=float)
        sec = np.where((g >= bas.to_datetime64()) & (c < bit.to_datetime64() + np.timedelta64(1, "D")))[0]   # veri sonu zorunlu kapanışları (bit+1g 00:00) hariç
    else:
        g = c = r = sf = np.array([])
        sec = np.array([], dtype=int)
    ev = []                                          # (zaman, tur 0=çıkış 1=giriş, islem_no)
    for i in sec:
        ev.append((g[i], 1, int(i)))
        ev.append((c[i], 0, int(i)))
    ev.sort(key=lambda x: (x[0], x[1], x[2]))
    E, tepe, oldu, kill_t = float(sermaye), float(sermaye), False, None
    pnl, notional, acik = {}, {}, set()
    olaylar, maxk, alinan, atlanan = [], 0.0, 0, 0
    for t, tur, i in ev:
        if tur == 1:
            if oldu or E <= 0:
                atlanan += 1
                continue
            if f is None:
                nt = E
                p = nt * r[i] * sf[i]
            else:
                p = f * E * r[i]
                nt = f * E / sf[i]
            p = max(p, -E)                           # tek işlem özsermayeden fazla kaybedemez (tasfiye)
            pnl[i], notional[i] = p, nt
            acik.add(i)
            alinan += 1
            maxk = max(maxk, sum(notional[j] for j in acik) / E)
        else:
            if i not in acik:
                continue
            acik.discard(i)
            if oldu and kill == "donuk":             # donuk: kill sonrası kapanan açık işlemlerin pnl'i yok sayılır (özsermaye dondurulur)
                continue
            E = max(E + pnl[i], 0.0)
            tepe = max(tepe, E)
            olaylar.append((t, E))
            if kill and not oldu and E <= tepe * (1 - KILL):
                oldu, kill_t = True, pd.Timestamp(t)
    return {"olaylar": olaylar, "kill_tarihi": kill_t, "max_kaldirac": maxk, "n_alinan": alinan, "n_atlanan": atlanan}


def oynat_getiri(getiri: pd.Series, s: float, kill=True, sermaye: float = SERMAYE, bas=BAS, bit=BIT) -> dict:
    """Portföy stratejisi: günlük getiri x s (s = f / %1). Çıktı biçimi oynat_islemler ile uyumlu (günlük olaylar)."""
    gi = pd.DatetimeIndex(getiri.index)
    gi = gi.tz_convert("UTC").tz_localize(None) if gi.tz is not None else gi
    g = pd.Series(getiri.to_numpy(dtype=float), index=gi)
    g = g[(g.index >= _naif(bas)) & (g.index <= _naif(bit))]
    E, tepe, oldu, kill_t, olaylar = float(sermaye), float(sermaye), False, None, []
    for t, x in g.items():
        if not oldu:
            E = max(E * (1 + s * x), 0.0)
            tepe = max(tepe, E)
            olaylar.append((t.to_datetime64(), E))
            if kill and E <= tepe * (1 - KILL):
                oldu, kill_t = True, t
    return {"olaylar": olaylar, "kill_tarihi": kill_t, "max_kaldirac": float("nan"), "n_alinan": len(g), "n_atlanan": 0}


def gunluk_ozsermaye(olaylar, sermaye: float = SERMAYE, bas=BAS, bit=BIT) -> pd.Series:
    """Olay (zaman, özsermaye) listesi -> kesintisiz günlük (gün sonu) özsermaye serisi [bas, bit]."""
    idx = pd.date_range(_naif(bas).normalize(), _naif(bit).normalize(), freq="D")
    if olaylar:
        s = pd.Series([e for _, e in olaylar], index=pd.DatetimeIndex([t for t, _ in olaylar])).groupby(level=0).last()
        s.index = s.index.floor("D")
        s = s.groupby(level=0).last()
        d = s.reindex(idx.union(s.index)).ffill().reindex(idx)
    else:
        d = pd.Series(np.nan, index=idx)
    return d.fillna(sermaye).astype(float)


def metrikler(gun: pd.Series, sermaye: float = SERMAYE) -> dict:
    """Günlük özsermaye serisinden metrikler. Aylar = takvim ayı sonu özsermayesi (son ay kısmi olabilir)."""
    e0 = float(sermaye)
    ay = gun.resample("ME").last()
    onceki = pd.concat([pd.Series([e0]), ay.iloc[:-1]]).to_numpy()
    ar = np.where(onceki > 0, ay.to_numpy() / np.where(onceki > 0, onceki, 1.0) - 1.0, 0.0)   # özsermaye 0 -> ay getirisi 0
    yil = gun.resample("YE").last()
    yonceki = pd.concat([pd.Series([e0]), yil.iloc[:-1]]).to_numpy()
    yr = pd.Series(np.where(yonceki > 0, yil.to_numpy() / np.where(yonceki > 0, yonceki, 1.0) - 1.0, 0.0), index=yil.index.year)
    son = float(gun.iloc[-1])
    gunsay = max((gun.index[-1] - gun.index[0]).days + 1, 1)
    cagr = (son / e0) ** (365.25 / gunsay) - 1 if son > 0 else -1.0
    tepe = np.maximum.accumulate(np.concatenate([[e0], gun.to_numpy()]))[1:]
    dd = float(((gun.to_numpy() - tepe) / tepe).min())
    return {"son": son, "getiri": son / e0 - 1, "cagr": cagr, "ay_ort": float(np.mean(ar)), "ay_medyan": float(np.median(ar)),
            "ay_en_kotu": float(np.min(ar)), "ay_zarar_orani": float(np.mean(ar < 0)), "max_dd": dd, "n_ay": len(ar), "yillik": yr}


def hesap_kos(hesap: dict, kill, carpan: int, f, sermaye: float = SERMAYE, bit=BIT) -> dict | None:
    """hesap: {id, tur, islem(DataFrame) | getiri(Series)}. D'de pf için None."""
    if hesap["tur"] == "pf":
        if f is None:
            return None
        o = oynat_getiri(hesap["getiri"], f / 0.01, kill, sermaye, bit=bit)
    else:
        if f is None and "sf" not in hesap["islem"].columns:
            return None
        o = oynat_islemler(hesap["islem"], f, kill, sermaye, bit=bit)
    gun = gunluk_ozsermaye(o["olaylar"], sermaye, bit=bit)
    return {"gun": gun, "kill_tarihi": o["kill_tarihi"], "max_kaldirac": o["max_kaldirac"], "n_alinan": o["n_alinan"],
            "n_atlanan": o["n_atlanan"], **metrikler(gun, sermaye)}


def yukle(hesaplar: list, carpan: int) -> list:
    out = []
    d = KOK / "sonuclar" / "risk_senaryo" / "islemler"
    for h in hesaplar:
        df = pd.read_parquet(d / f"{h['id']}__x{carpan}.parquet")
        if h["tur"] == "pf":
            out.append({**h, "getiri": pd.Series(df["getiri"].to_numpy(), index=pd.DatetimeIndex(df["gun"]))})
        else:
            out.append({**h, "islem": df})
    return out


def main():
    sys.path.insert(0, str(KOK))
    from araclar import risk_senaryo_kos as ks
    hesaplar = ks.hesap_listesi()
    cikti = KOK / "sonuclar" / "risk_senaryo"
    satirlar, yillik, port, port_yillik = [], [], [], []
    for carpan in (1, 2):
        H = yukle(hesaplar, carpan)
        for kill in (True, "donuk", False):
            for sen, f in SENARYOLAR.items():
                gunler = []
                for h in H:
                    r = hesap_kos(h, kill, carpan, f)
                    if r is None:
                        satirlar.append({"id": h["id"], "etiket": h["etiket"], "carpan": carpan, "kill_kurali": kill, "senaryo": sen, "yok": True})
                        continue
                    gunler.append(r["gun"])
                    satirlar.append({"id": h["id"], "etiket": h["etiket"], "carpan": carpan, "kill_kurali": kill, "senaryo": sen, "yok": False,
                                     **{k: r[k] for k in ("getiri", "cagr", "ay_ort", "ay_medyan", "ay_en_kotu", "ay_zarar_orani", "max_dd",
                                                          "max_kaldirac", "n_alinan", "n_atlanan", "n_ay")},
                                     "kill_oldu": r["kill_tarihi"] is not None,
                                     "kill_tarihi": str(r["kill_tarihi"].date()) if r["kill_tarihi"] is not None else ""})
                    for y, v in r["yillik"].items():
                        yillik.append({"id": h["id"], "carpan": carpan, "kill_kurali": kill, "senaryo": sen, "yil": int(y), "getiri": float(v)})
                toplam = sum(gunler)
                m = metrikler(toplam, SERMAYE * len(gunler))
                port.append({"carpan": carpan, "kill_kurali": kill, "senaryo": sen, "n_hesap": len(gunler),
                             **{k: m[k] for k in ("getiri", "cagr", "ay_ort", "ay_medyan", "ay_en_kotu", "ay_zarar_orani", "max_dd")}})
                for y, v in m["yillik"].items():
                    port_yillik.append({"carpan": carpan, "kill_kurali": kill, "senaryo": sen, "yil": int(y), "getiri": float(v)})
    # duyarlılık: veri sonu zorunlu kapanışları DAHİL (gerçekleşmemiş kâr; bit = 2025-11-08)
    H = yukle(hesaplar, 1)
    zor, dahil = [], []
    for h in H:
        if h["tur"] == "pf":
            continue
        d = h["islem"]
        z = d[(d["cikis_zamani"].map(_naif) >= BIT + pd.Timedelta(days=1)) & (d["giris_zamani"].map(_naif) >= BAS)]
        zor.append({"id": h["id"], "n": len(z), "toplam_r": float(z["r"].sum()), "semboller": ",".join(sorted(z["sembol"].unique()))})
    for kill in (True, False):
        for sen, f in SENARYOLAR.items():
            gunler = [hesap_kos(h, kill, 1, f, bit=BIT + pd.Timedelta(days=1)) for h in H]
            gunler = [g["gun"] for g in gunler if g is not None]
            m = metrikler(sum(gunler), SERMAYE * len(gunler))
            dahil.append({"kill_kurali": kill, "senaryo": sen, "n_hesap": len(gunler), **{k: m[k] for k in ("getiri", "cagr", "max_dd")}})
    pd.DataFrame(zor).to_csv(cikti / "zorunlu_kapanis.csv", index=False)
    pd.DataFrame(dahil).to_csv(cikti / "dahil.csv", index=False)
    pd.DataFrame(satirlar).to_csv(cikti / "ozet.csv", index=False)
    pd.DataFrame(yillik).to_csv(cikti / "yillik.csv", index=False)
    pd.DataFrame(port).to_csv(cikti / "portfoy.csv", index=False)
    pd.DataFrame(port_yillik).to_csv(cikti / "portfoy_yillik.csv", index=False)
    print("yazildi", cikti)


if __name__ == "__main__":
    main()
