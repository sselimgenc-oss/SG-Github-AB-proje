"""Islem mutabakati (saf; ag/dosya yazimi yok): motor defteri = panel = Telegram, her islem icin. YALNIZ BILGI VERIR; motoru etkilemez.

Girdi: defter islemleri (kapanan + acik; `TradeRecord`), panelin veri katmaninin urettigi satirlar (`panel_pano.closed_view` /
`open_view`), Telegram kaynaklari (gonderim kaydi `islem_gonderildi.jsonl`, outbox `sent` isaretleri, imlec `islem_imleci.json`).
Cikti: satir listesi + kontroller + ozet (`ml.mutabakat.v1`). Net K/Z = defterin `realized_pnl`'u: zaten brut - giris komisyonu -
cikis komisyonu - fonlama (ledger.record_trade_exit); komisyon ve fonlama ayrica gosterilir. Saatler TSI (UTC+3, DST yok).
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from . import panel_pano as PP
from . import tg_sade as TS

SEMA = "ml.mutabakat.v1"
TOL = 0.01                          # $ toleransi (net K/Z, kasa, toplamlar)
BEKLEME_DK = 15                     # bu kadar yeni olay: Telegram'a henuz gitmemis olabilir -> uyusmazlik sayilmaz
TR = timezone(timedelta(hours=3))   # Europe/Istanbul (DST yok)

TG_GONDERILDI = ("gönderildi (kayıt)", "gönderildi (outbox işareti)", "gönderildi (imleç)")
TG_ONCESI = "Telegram öncesi (mesaj sistemi yoktu)"
TG_BEKLEMEDE = "beklemede"
TG_EKSIK = "eksik"
TG_YON = "yanlış yön"
TG_KZ = "yanlış K/Z"
TG_YOK = "—"                        # olay yok (acik islem icin 'kapandi')
TG_SORUN = (TG_EKSIK, TG_YON, TG_KZ)


def tsi_tam(dt: datetime | None) -> str | None:
    return None if dt is None else dt.astimezone(TR).strftime("%Y-%m-%d %H:%M")


def isr(x, nd: int = 2) -> str:
    """Isaretli Turkce para bicimi: -3.5 -> '-3,50', 23.6 -> '+23,60'."""
    return ("-" if float(x) < 0 and round(abs(float(x)), nd) > 0 else "+") + TS.sayi(x, nd)


def usd(x, nd: int = 2) -> str:
    """Turkce para bicimi, isaretsiz: 1021.4 -> '1.021,40'."""
    return TS.sayi(x, nd)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ----------------------------------------------------------------------------------------------- motor
def motor_satirlari(kapali: Sequence, acik: Sequence, kol_fn: Callable[[Any], str]) -> list[dict]:
    """Defter islemleri -> satirlar (islem no artan). `_a`/`_k` ic alanlari (datetime) `temiz()` ile atilir."""
    rows = []
    for t, durum in [(x, "kapalı") for x in kapali] + [(x, "açık") for x in acik]:
        kapal = durum == "kapalı"
        fe, fx = float(t.fee_entry or 0.0), float(t.fee_exit or 0.0) if kapal else 0.0
        rows.append({
            "islem_no": t.trade_id, "kol": kol_fn(t), "coin": TS.coin(t.pair), "yon": TS.yon(t.side), "durum": durum,
            "acilis": tsi_tam(t.entry_ts), "kapanis": tsi_tam(t.exit_ts) if kapal else None,
            "giris": t.entry_price, "cikis": t.exit_price if kapal else None,
            "brut": float(t.gross_pnl) if kapal and t.gross_pnl is not None else None,
            "komisyon": fe + fx, "fonlama": float(t.funding_paid or 0.0) if kapal else 0.0,
            "net": float(t.realized_pnl or 0.0) if kapal else None,
            "_a": _utc(t.entry_ts), "_k": _utc(t.exit_ts) if kapal and t.exit_ts else None,
            "uyusmazlik": []})
    rows.sort(key=lambda r: r["islem_no"])
    return rows


def temiz(rows: Sequence[Mapping]) -> list[dict]:
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


# ----------------------------------------------------------------------------------------------- panel
def _yakin(a, b, tol=TOL) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def panel_karsilastir(rows: list[dict], panel_kapanan: Sequence[Mapping], panel_acik: Sequence[Mapping], panel_siniri: int) -> list[str]:
    """Her motor satirina `panel` durumu yazar; uyusmazlik listesine ekler. Dondurur: panelde fazla (motorda olmayan) satirlar."""
    pk = {r.get("id"): r for r in panel_kapanan}
    pa = {r.get("id"): r for r in panel_acik}
    kapali = sorted((r for r in rows if r["durum"] == "kapalı"), key=lambda r: (r["_k"], r["islem_no"]), reverse=True)
    sira = {r["islem_no"]: i for i, r in enumerate(kapali)}
    for r in rows:
        p = (pk if r["durum"] == "kapalı" else pa).get(r["islem_no"])
        if p is None:
            diger = (pa if r["durum"] == "kapalı" else pk).get(r["islem_no"])
            if r["durum"] == "kapalı" and sira[r["islem_no"]] >= panel_siniri > 0:
                r["panel"] = f"liste sınırı dışı (panel son {panel_siniri} işlemi gösterir)"
                continue
            r["panel"] = "YOK"
            r["uyusmazlik"].append("panelde yok" + (" (diğer listede görünüyor)" if diger else ""))
            continue
        fark, sade = [], []                       # fark: teknik (json/md 'panel' sutunu); sade: Telegram/ozet metni
        if p.get("yon") != r["yon"]:
            fark.append(f"yön panel={p.get('yon')} motor={r['yon']}")
            sade.append("yön farkı")
        if p.get("coin") != r["coin"]:
            fark.append(f"coin panel={p.get('coin')} motor={r['coin']}")
            sade.append("coin farkı")
        if p.get("kol") != r["kol"]:
            fark.append(f"kol panel={p.get('kol')} motor={r['kol']}")
            sade.append("kol farkı")
        if not _yakin(p.get("giris"), r["giris"], 1e-6):
            fark.append(f"giriş fiyatı panel={p.get('giris')} motor={r['giris']}")
            sade.append("giriş fiyatı farkı")
        if p.get("acilis") != PP.tsi_kisa(r["_a"]):
            fark.append(f"açılış saati panel={p.get('acilis')} motor={PP.tsi_kisa(r['_a'])}")
            sade.append("açılış saati farkı")
        if r["durum"] == "kapalı":
            if not _yakin(p.get("kz"), r["net"]):
                fark.append(f"net K/Z panel={_n(p.get('kz'))} motor={_n(r['net'])}")
                try:
                    sade.append(f"K/Z farkı {usd(abs(float(p.get('kz')) - float(r['net'])))} $")
                except (TypeError, ValueError):
                    sade.append("K/Z farkı")
            if not _yakin(p.get("cikis"), r["cikis"], 1e-6):
                fark.append(f"çıkış fiyatı panel={p.get('cikis')} motor={r['cikis']}")
                sade.append("çıkış fiyatı farkı")
            if p.get("kapanis") != PP.tsi_kisa(r["_k"]):
                fark.append(f"kapanış saati panel={p.get('kapanis')} motor={PP.tsi_kisa(r['_k'])}")
                sade.append("kapanış saati farkı")
            if not _yakin(p.get("komisyon"), r["komisyon"]) or not _yakin(p.get("fonlama"), r["fonlama"]):
                fark.append("komisyon/fonlama farklı")
                sade.append("komisyon/fonlama farkı")
        r["panel"] = "aynı" if not fark else "FARK: " + "; ".join(fark)
        r["uyusmazlik"].extend(sade)
    motor_ids = {r["islem_no"] for r in rows}
    return [f"panelde fazla işlem #{i}" for i in list(pk) + list(pa) if i not in motor_ids]


def _n(x) -> str:
    try:
        return isr(x)
    except (TypeError, ValueError):
        return str(x)


# ----------------------------------------------------------------------------------------------- telegram
def _olay(r: dict, tur: str, now: datetime, kayit: Mapping, isaretli: Callable[[int, str], bool], imlec: Mapping | None,
          imlec_min: int | None, tg_basi: datetime | None, tg_baslangic: datetime | None) -> str:
    t = r["_a"] if tur == "acildi" else r["_k"]
    k = kayit.get((r["islem_no"], tur))
    if k is not None:
        if k.get("yon") != r["yon"]:
            return TG_YON
        if tur == "kapandi" and not _yakin(k.get("kz"), r["net"]):
            return TG_KZ
        return TG_GONDERILDI[0]
    esik = max([d for d in (tg_basi, tg_baslangic) if d is not None], default=None)
    if esik is not None and t < esik:
        return TG_ONCESI
    if isaretli(r["islem_no"], tur):
        return TG_GONDERILDI[1]
    if imlec is None:
        return TG_ONCESI if now - t > timedelta(minutes=BEKLEME_DK) else TG_BEKLEMEDE
    anahtar = "acilan" if tur == "acildi" else "kapanan"
    if r["islem_no"] in set(imlec.get(anahtar) or []):
        return TG_GONDERILDI[2] if tg_basi is None else TG_EKSIK       # kayit tutuluyorken imlec var ama gonderim kaydi yok
    if now - t <= timedelta(minutes=BEKLEME_DK):
        return TG_BEKLEMEDE
    if tg_basi is None and imlec_min is not None and r["islem_no"] < imlec_min:
        return TG_ONCESI                                               # imlec son 500 kimligi tutar: daha eski islem
    return TG_EKSIK


def telegram_karsilastir(rows: list[dict], *, now: datetime, kayit: Mapping, isaretli: Callable[[int, str], bool],
                         imlec: Mapping | None, tg_baslangic: datetime | None = None) -> list[str]:
    """Satirlara `telegram_acildi` / `telegram_kapandi` yazar. kayit: {(trade_id, tur): satir}. Dondurur: Telegram'da fazla kayitlar."""
    ids = [i for k in ("acilan", "kapanan") for i in ((imlec or {}).get(k) or []) if isinstance(i, int)]
    imlec_min = min(ids) if ids else None
    tg_basi = min((_utc(v["_ts"]) for v in kayit.values() if v.get("_ts")), default=None)
    for r in rows:
        r["telegram_acildi"] = _olay(r, "acildi", now, kayit, isaretli, imlec, imlec_min, tg_basi, tg_baslangic)
        r["telegram_kapandi"] = _olay(r, "kapandi", now, kayit, isaretli, imlec, imlec_min, tg_basi, tg_baslangic) \
            if r["durum"] == "kapalı" else TG_YOK
        for ad in ("telegram_acildi", "telegram_kapandi"):
            if r[ad] in TG_SORUN:
                tur = "açılış" if ad == "telegram_acildi" else "kapanış"
                r["uyusmazlik"].append({TG_EKSIK: f"Telegram {tur} mesajı eksik", TG_YON: f"Telegram {tur} mesajında yön yanlış",
                                        TG_KZ: f"Telegram {tur} mesajında K/Z yanlış"}[r[ad]])
    motor_ids = {r["islem_no"] for r in rows}
    fazla = sorted({i for (i, _t) in kayit if i not in motor_ids})
    return [f"Telegram'da fazla işlem #{i} (defterde yok)" for i in fazla]


# ----------------------------------------------------------------------------------------------- kontroller
FIYAT_BEKLENIYOR = "fiyat bekleniyor (piyasa kapalı/veri yok)"


def kontrol(ad: str, gecti: bool | None, ayrinti: str, **ek) -> dict:
    return {"ad": ad, "sonuc": "atlandı" if gecti is None else ("geçti" if gecti else "kaldı"), "ayrinti": ayrinti, **ek}


def toplamlar(rows: Sequence[Mapping]) -> dict:
    out: dict[str, dict] = {}
    for ad, f in (("tumu", lambda r: True), ("long", lambda r: r["yon"] == "long"), ("short", lambda r: r["yon"] == "short")):
        k = [r for r in rows if r["durum"] == "kapalı" and f(r)]
        out[ad] = {"n": len(k), "net": math.fsum(r["net"] for r in k)}
    return out


def son_kapanan(rows: Sequence[Mapping], n: int) -> list[Mapping]:
    """Panelin 'tumu' listesinin gosterdigi kume: cikis zamani yeniden eskiye ilk n kapanan (liste siniri)."""
    kap = sorted((r for r in rows if r["durum"] == "kapalı"), key=lambda r: (r["_k"], r["islem_no"]), reverse=True)
    return kap[:n] if n > 0 else kap


def kontrol_long_short(motor: Mapping, panel_kapanan_rows: Sequence[Mapping], panel_n: int | None, panel_net: float | None) -> list[dict]:
    """Motor ve panel (kapanan 'tumu' gorunumu) long/short ayri toplamlari; panel satirlari listesi sinirliysa (daha_fazla) yalniz
    toplam n/net karsilastirilir."""
    out = []
    pl = {y: [r for r in panel_kapanan_rows if r.get("yon") == y] for y in ("long", "short")}
    for y in ("long", "short"):
        n_m, net_m = motor[y]["n"], motor[y]["net"]
        n_p, net_p = len(pl[y]), math.fsum(float(r.get("kz") or 0.0) for r in pl[y])
        ok = n_m == n_p and _yakin(net_m, net_p)
        out.append(kontrol(f"{y.capitalize()} toplamı (motor = panel)", ok,
                           f"{y.capitalize()} işlemler panelle aynı ({n_m} işlem)" if ok else
                           f"{y.capitalize()}: kayıtta {n_m} işlem {isr(net_m)} $, panelde {n_p} işlem {isr(net_p)} $"))
    if panel_n is not None and panel_net is not None:
        ok = motor["tumu"]["n"] == panel_n and _yakin(motor["tumu"]["net"], panel_net)
        out.append(kontrol("Toplam kapanan (motor = panel 'tümü')", ok,
                           f"Kapanan işlemlerin toplamı panelle aynı ({panel_n} işlem)" if ok else
                           f"Kapanan işlemler: kayıtta {motor['tumu']['n']} işlem {isr(motor['tumu']['net'])} $, "
                           f"panelde {panel_n} işlem {isr(panel_net)} $"))
    return out


def _acik_alanlari(status: Mapping) -> tuple[list[Mapping] | None, dict]:
    """Durum dosyasindaki acik pozisyonlardan kasaya yansiyan kalemler; yeni alanlar yoksa (eski motor) (None, {})."""
    acik = [p for p in status.get("open_positions") or [] if isinstance(p, Mapping)]
    for p in acik:
        if not isinstance(p.get("fee_paid_entry"), (int, float)) or not isinstance(p.get("funding_paid"), (int, float)):
            return None, {}
    g = lambda k: math.fsum(float(p.get(k) or 0.0) for p in acik)   # noqa: E731
    return acik, {"giris_komisyon": g("fee_paid_entry"), "fonlama": g("funding_paid"),
                  "kismi_kz": g("partial_realized_usd"), "kismi_komisyon": g("partial_fee_usd")}


def kontrol_kasa(*, baslangic: float | None, net_sql: float | None, net_motor: float, status: Mapping | None) -> dict:
    """Kasa (durum `wallet`; mark zamanlamasindan bagimsiz) = baslangic + kapananlarin net K/Z toplami (SQL) - acik islemlerin giris
    komisyonu - acik islemlerde odenen fonlama + acik islemlerin kismi cikis K/Z'si - kismi cikis komisyonu. Kismi cikis ve fonlama
    brokerin cuzdanina hemen islenir; defter satiri kapanista yazilir. Yeni alanlar yoksa (eski motor) kontrol 'atlandi'."""
    ad = "Kasa = başlangıç + Σ net K/Z"
    if baslangic is None or net_sql is None:
        return kontrol(ad, None, "Başlangıç kasası ya da defter toplamı okunamadı; kasa kontrolü atlandı")
    if status is None or not isinstance(status.get("wallet"), (int, float)):
        return kontrol(ad, None, "Durum dosyası canlı değil; kasa kontrolü atlandı")
    acik, k = _acik_alanlari(status)
    if acik is None:
        return kontrol(ad, None, "Durum dosyası eski sürüm (açık işlem komisyon/fonlama bilgisi yok); kasa kontrolü atlandı")
    wallet = float(status["wallet"])
    beklenen = baslangic + net_sql - k["giris_komisyon"] - k["fonlama"] + k["kismi_kz"] - k["kismi_komisyon"]
    fark = wallet - beklenen
    if abs(net_sql - net_motor) > TOL:
        return kontrol(ad, False, f"Defter toplamları tutmuyor: SQL toplamı {isr(net_sql)} $, motor toplamı {isr(net_motor)} $")
    if abs(fark) <= TOL:
        return kontrol(ad, True, f"Kasa {usd(wallet)} $ tutuyor")
    return kontrol(ad, False, f"Kasa {usd(beklenen)} $ olmalı, kayıtta {usd(wallet)} $ · fark {usd(abs(fark))} $")


def bilgi_acik_kz(status: Mapping | None) -> str | None:
    """Bilgi satiri (uyusmazlik sayilmaz): broker equity - wallet ile durum dosyasindaki acik K/Z; fark yalniz mark zamanlamasi."""
    if status is None or not all(isinstance(status.get(a), (int, float)) for a in ("equity", "wallet", "unrealized_pnl_usd")):
        return None
    broker = float(status["equity"]) - float(status["wallet"])
    durum = float(status["unrealized_pnl_usd"])
    return (f"Açık işlemlerin anlık kâr/zararı: kasada {isr(broker)} $, panelde {isr(durum)} $ · fark {usd(abs(broker - durum))} $ "
            "(fiyat zamanlaması, uyuşmazlık sayılmaz)")


def kontrol_bagimsiz_toplam(net_sql: float | None, brut_sql: float | None, net_motor: float) -> dict:
    ad = "Net K/Z: SQL toplamı = motor toplamı = brüt - komisyon - fonlama"
    if net_sql is None:
        return kontrol(ad, None, "Defter toplamı okunamadı; kontrol atlandı")
    ok = abs(net_sql - net_motor) <= TOL and (brut_sql is None or abs(net_sql - brut_sql) <= TOL)
    if ok:
        return kontrol(ad, True, f"Defter toplamları tutuyor ({isr(net_sql)} $)")
    if abs(net_sql - net_motor) > TOL:
        return kontrol(ad, False, f"Defter toplamı {isr(net_sql)} $, motor toplamı {isr(net_motor)} $ · fark {usd(abs(net_sql - net_motor))} $")
    return kontrol(ad, False, f"Net toplam {isr(net_sql)} $, brütten masraf düşünce {isr(brut_sql)} $ · fark {usd(abs(net_sql - brut_sql))} $")


def kontrol_acik(motor_n: int, panel_n: int | None, serit_n: int | None, status_n: int | None) -> dict:
    ad = "Açık pozisyon sayısı (motor = panel = şerit = durum)"
    vals = {"defter": motor_n, "panel": panel_n, "şerit": serit_n, "durum": status_n}
    bilinen = {k: v for k, v in vals.items() if v is not None}
    ok = len(set(bilinen.values())) == 1 and panel_n is not None and serit_n is not None
    if ok:
        return kontrol(ad, True, f"{motor_n} açık işlem, hepsi aynı")
    return kontrol(ad, False, "Açık işlem sayısı farklı: " + ", ".join(f"{k} {v if v is not None else 'okunamadı'}" for k, v in vals.items()))


def kontrol_acik_kz(status: Mapping | None, panel_acik: Sequence[Mapping]) -> dict:
    """Panelin acik K/Z fiyati = durum dosyasindaki `mark` (motorun son kapanmis 1 dk mumu); piyasa veritabani okunmaz."""
    ad = "Açık K/Z fiyat kaynağı (panel = motor mark)"
    if status is None:
        return kontrol(ad, None, "Durum dosyası canlı değil; kontrol atlandı")
    pos = {p.get("trade_id"): p for p in status.get("open_positions") or [] if isinstance(p, Mapping)}
    if not pos and not panel_acik:
        return kontrol(ad, True, "Açık işlem yok")
    sorun, enb, bekleyen = [], 0.0, []
    for r in panel_acik:
        p = pos.get(r.get("id"))
        if p is None:
            sorun.append(f"#{r.get('id')} durum dosyasında yok")
            continue
        mark = p.get("mark")
        if mark is None and r.get("simdi") is None:
            bekleyen.append(r.get("id"))          # fiyat yok (seans kapali / veri yok): uyusmazlik DEGIL, ayri durum
            continue
        if mark is None or r.get("simdi") is None:
            sorun.append(f"#{r.get('id')} panel ile motor fiyatı farklı")
            continue
        sgn = 1.0 if str(p.get("side")).lower() == "long" else -1.0
        yeniden = sgn * (float(mark) - float(p["entry_price"])) * float(p["qty"])
        d = max(abs(float(r["simdi"]) - float(mark)) * float(p["qty"]), abs(float(r.get("kz") or 0.0) - yeniden))
        enb = max(enb, d)
        if d > TOL:
            sorun.append(f"#{r.get('id')} fark {usd(d)} $")
    for i in pos:
        if i not in {r.get("id") for r in panel_acik}:
            sorun.append(f"#{i} panelde yok")
    bek = ("; " + FIYAT_BEKLENIYOR + ": " + ", ".join(f"#{i}" for i in bekleyen)) if bekleyen else ""
    if not sorun:
        return kontrol(ad, True, "Açık işlemlerin kâr/zararı panelle aynı" + bek, fiyat_bekleniyor=bekleyen)
    return kontrol(ad, False, "Açık işlem kâr/zararı panelde farklı: " + ", ".join(sorun[:3]) + bek, fiyat_bekleniyor=bekleyen)


def kontrol_limit(panel_oran: float | None, ayar_orani: float | None) -> dict:
    ad = "Günlük zarar limiti oranı (panel = kâğıt ayarı)"
    if panel_oran is None or ayar_orani is None:
        return kontrol(ad, None, "Oran okunamadı; kontrol atlandı")
    ok = abs(panel_oran - ayar_orani) < 1e-12
    return kontrol(ad, ok, f"Günlük zarar limiti %{usd(ayar_orani * 100)}" + (" (panelle aynı)" if ok else
                                                                              f" olmalı, panelde %{usd(panel_oran * 100)}"))


# ----------------------------------------------------------------------------------------------- ozet
def ozet(rows: Sequence[Mapping], kontroller: Sequence[Mapping], ekstra: Sequence[str], *, now: datetime, panel_notu: str = "",
         telegram_kaynak: str = "", bilgi: Sequence[str] = ()) -> dict:
    sat = [r for r in rows if r["uyusmazlik"]]
    kal = [k for k in kontroller if k["sonuc"] == "kaldı"]
    liste = ([k["ayrinti"] for k in kal]
             + [f"#{r['islem_no']} {r['coin']} {r['yon']}: " + "; ".join(r["uyusmazlik"]) for r in sat]
             + list(ekstra))
    bekleyen = sorted({int(i) for k in kontroller for i in (k.get("fiyat_bekleniyor") or []) if isinstance(i, int)})
    sayac: dict[str, int] = {}
    for r in rows:
        for a in ("telegram_acildi", "telegram_kapandi"):
            sayac[r[a]] = sayac.get(r[a], 0) + 1
    return {"sema": SEMA, "uretim": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "uretim_tsi": tsi_tam(now), "islem_sayisi": len(rows),
            "kapanan": sum(1 for r in rows if r["durum"] == "kapalı"), "acik": sum(1 for r in rows if r["durum"] == "açık"),
            "uyusmazlik_sayisi": len(liste), "uyusmazliklar": liste,
            "telegram": {"eksik": sum(1 for r in rows for a in ("telegram_acildi", "telegram_kapandi") if r[a] == TG_EKSIK),
                         "yanlis_yon": sum(1 for r in rows for a in ("telegram_acildi", "telegram_kapandi") if r[a] == TG_YON),
                         "yanlis_kz": sum(1 for r in rows for a in ("telegram_acildi", "telegram_kapandi") if r[a] == TG_KZ),
                         "fazla": sum(1 for e in ekstra if e.startswith("Telegram")),
                         "oncesi": sum(1 for r in rows for a in ("telegram_acildi", "telegram_kapandi") if r[a] == TG_ONCESI),
                         "dagilim": dict(sorted(sayac.items())), "kaynak": telegram_kaynak},
            "fiyat_bekleniyor": bekleyen, "fiyat_bekleniyor_durum": FIYAT_BEKLENIYOR if bekleyen else None,
            "panel_notu": panel_notu, "bilgi": list(bilgi), "kontroller": list(kontroller)}


FIYAT_ESIK_DK = 10


def _seans_acik(cls, now: datetime) -> bool:
    """Piyasa seansta mi (simdi ve FIYAT_ESIK_DK dk once)? Sinif bilinmiyorsa False: 'fiyat yok' sorun sayilmaz."""
    from . import arm_time as AT   # noqa: PLC0415
    try:
        return (AT.session_tag(str(cls), now) == "open"
                and AT.session_tag(str(cls), now - timedelta(minutes=FIYAT_ESIK_DK)) == "open")
    except ValueError:
        return False


def _yeni_basladi(status: Mapping | None, now: datetime) -> bool:
    """Durum dosyasindaki motor `started_at` FIYAT_ESIK_DK dakikadan yeniyse True (kurulum sonrasi yeniden baslatma)."""
    v = (status or {}).get("started_at")
    if not v:
        return False
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return now - t < timedelta(minutes=FIYAT_ESIK_DK)


def sorunlar(rows: Sequence[Mapping], kontroller: Sequence[Mapping], ekstra: Sequence[str], status: Mapping | None, now: datetime) -> list[str]:
    """Telegram'a gidecek GERCEK sorunlar (sade Turkce, islem numarasi yok, coin adiyla). Bos liste = mesaj yok. 'Fiyat bekleniyor'
    (piyasa kapali / veri yok) sorun DEGILDIR; yalniz seans icinde fiyat gelmiyorsa sorun olur."""
    import re   # noqa: PLC0415
    out: list[str] = []
    coin_of = {r["islem_no"]: r["coin"] for r in rows}
    pos = {p.get("trade_id"): p for p in (status or {}).get("open_positions") or [] if isinstance(p, Mapping)}
    for k in kontroller:
        if k.get("sonuc") != "kaldı":
            continue
        ad, ay = str(k.get("ad", "")), str(k.get("ayrinti", ""))
        if ad.startswith("Kasa"):
            m = re.search(r"Kasa (\S+) \$ olmalı, kayıtta (\S+) \$", ay)
            out.append(f"Kasa kayıtla tutmuyor: {m.group(1)} $ olmalı, kayıtta {m.group(2)} $" if m else "Kasa kayıtla tutmuyor")
        elif ad.startswith("Açık K/Z"):
            out.append("Açık işlemlerin kâr/zararı panelle tutmuyor")
        else:
            out.append(re.sub(r" ?#\d+", "", ay).strip() or ad)
    taze_baslangic = _yeni_basladi(status, now)          # motor yeni (yeniden) basladi: ilk 1 dk mumu gelene kadar mark yok, sorun DEGIL
    for i in sorted({int(x) for k in kontroller for x in (k.get("fiyat_bekleniyor") or []) if isinstance(x, int)}):
        p = pos.get(i) or {}
        if not taze_baslangic and p.get("asset_class") and _seans_acik(p.get("asset_class"), now):
            out.append(f"{coin_of.get(i) or TS.coin(p.get('pair'))} işleminin güncel fiyatı alınamıyor")
    for r in rows:
        if r["uyusmazlik"]:
            out.append(f"{r['coin']} işleminde kayıtlar tutmuyor: " + "; ".join(str(u) for u in r["uyusmazlik"][:2]))
    if ekstra:
        out.append("Panelde ya da Telegram'da fazladan kayıt var")
    return list(dict.fromkeys(out))


def markdown(doc: Mapping, rows: Sequence[Mapping]) -> str:
    def f(x, nd=4):
        return "—" if x is None else (("-" if x < 0 else "") + TS.sayi(x, nd) if isinstance(x, float) else str(x))
    L = ["# İşlem mutabakatı", "",
         f"Son kontrol: {doc['uretim_tsi']} (TSİ). İşlem: {doc['islem_sayisi']} (kapanan {doc['kapanan']}, açık {doc['acik']}). "
         f"Uyuşmazlık: {doc['uyusmazlik_sayisi']}.", "", "## Kontroller", "", "| Kontrol | Sonuç | Ayrıntı |", "|---|---|---|"]
    L += [f"| {k['ad']} | {k['sonuc']} | {k['ayrinti']} |" for k in doc["kontroller"]]
    L += ["", "## Bilgi", ""] + [f"- {b}" for b in doc.get("bilgi") or []] if doc.get("bilgi") else []
    L += ["", "## Telegram kaynağı", "", doc["telegram"].get("kaynak") or "—", "", "## Uyuşmazlıklar", ""]
    L += [f"- {u}" for u in doc["uyusmazliklar"]] or ["Yok."]
    L += ["", "## İşlemler", "",
          "| İşlem no | Kol | Coin | Yön | Durum | Açılış (TSİ) | Kapanış (TSİ) | Giriş | Çıkış | Brüt $ | Komisyon $ | Fonlama $ | Net K/Z $ | Panel | Telegram açıldı | Telegram kapandı |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| " + " | ".join([str(r["islem_no"]), r["kol"], r["coin"], r["yon"], r["durum"], f(r["acilis"]), f(r["kapanis"]),
                                    f(r["giris"], 6), f(r["cikis"], 6), f(r["brut"]), f(r["komisyon"]), f(r["fonlama"]), f(r["net"]),
                                    r["panel"], r["telegram_acildi"], r["telegram_kapandi"]]) + " |")
    return "\n".join(L) + "\n"
