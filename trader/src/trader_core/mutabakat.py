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
            r["uyusmazlik"].append("panelde yok" + (" (panel işlemi diğer listede gösteriyor)" if diger else ""))
            continue
        fark = []
        if p.get("yon") != r["yon"]:
            fark.append(f"yön panel={p.get('yon')} motor={r['yon']}")
        if p.get("coin") != r["coin"]:
            fark.append(f"coin panel={p.get('coin')} motor={r['coin']}")
        if p.get("kol") != r["kol"]:
            fark.append(f"kol panel={p.get('kol')} motor={r['kol']}")
        if not _yakin(p.get("giris"), r["giris"], 1e-6):
            fark.append(f"giriş fiyatı panel={p.get('giris')} motor={r['giris']}")
        if p.get("acilis") != PP.tsi_kisa(r["_a"]):
            fark.append(f"açılış saati panel={p.get('acilis')} motor={PP.tsi_kisa(r['_a'])}")
        if r["durum"] == "kapalı":
            if not _yakin(p.get("kz"), r["net"]):
                fark.append(f"net K/Z panel={_n(p.get('kz'))} motor={_n(r['net'])}")
            if not _yakin(p.get("cikis"), r["cikis"], 1e-6):
                fark.append(f"çıkış fiyatı panel={p.get('cikis')} motor={r['cikis']}")
            if p.get("kapanis") != PP.tsi_kisa(r["_k"]):
                fark.append(f"kapanış saati panel={p.get('kapanis')} motor={PP.tsi_kisa(r['_k'])}")
            if not _yakin(p.get("komisyon"), r["komisyon"]) or not _yakin(p.get("fonlama"), r["fonlama"]):
                fark.append("komisyon/fonlama farklı")
        r["panel"] = "aynı" if not fark else "FARK: " + "; ".join(fark)
        r["uyusmazlik"].extend(f"panel: {x}" for x in fark)
    motor_ids = {r["islem_no"] for r in rows}
    return [f"panelde fazla işlem #{i}" for i in list(pk) + list(pa) if i not in motor_ids]


def _n(x) -> str:
    try:
        return f"{float(x):+.4f}"
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
                r["uyusmazlik"].append(f"telegram {ad.split('_')[1]}: {r[ad]}")
    motor_ids = {r["islem_no"] for r in rows}
    fazla = sorted({i for (i, _t) in kayit if i not in motor_ids})
    return [f"Telegram'da fazla işlem #{i} (defterde yok)" for i in fazla]


# ----------------------------------------------------------------------------------------------- kontroller
def kontrol(ad: str, gecti: bool | None, ayrinti: str) -> dict:
    return {"ad": ad, "sonuc": "atlandı" if gecti is None else ("geçti" if gecti else "kaldı"), "ayrinti": ayrinti}


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
                           f"motor {n_m} işlem {net_m:+.4f} $; panel {n_p} işlem {net_p:+.4f} $"))
    if panel_n is not None and panel_net is not None:
        ok = motor["tumu"]["n"] == panel_n and _yakin(motor["tumu"]["net"], panel_net)
        out.append(kontrol("Toplam kapanan (motor = panel 'tümü')", ok,
                           f"motor {motor['tumu']['n']} işlem {motor['tumu']['net']:+.4f} $; panel {panel_n} işlem {panel_net:+.4f} $"))
    return out


def kontrol_kasa(*, baslangic: float | None, net_sql: float | None, net_motor: float, status: Mapping | None,
                 acik_giris_komisyon: float) -> dict:
    """kasa = baslangic + Σ net (komisyon + fonlama dahil; SQL'den bagimsiz toplam) ile status equity. Acik islem: kagit kasa acilista
    giris komisyonunu zaten dusmustur ve K/Z dalgalanir: beklenen equity = baslangic + Σnet - acik giris komisyonu + acik K/Z."""
    ad = "Kasa = başlangıç + Σ net K/Z"
    if baslangic is None or net_sql is None:
        return kontrol(ad, None, "başlangıç kasası ya da defter toplamı okunamadı")
    if status is None or not isinstance(status.get("equity"), (int, float)):
        return kontrol(ad, None, "durum dosyası canlı değil (equity okunamadı)")
    eq = float(status["equity"])
    unreal = float(status.get("unrealized_pnl_usd") or 0.0)
    beklenen = baslangic + net_sql - acik_giris_komisyon + unreal
    fark = eq - beklenen
    parca = (f"başlangıç {baslangic:.2f} + Σnet {net_sql:+.4f} (motor toplamı {net_motor:+.4f}) - açık giriş komisyonu "
             f"{acik_giris_komisyon:.4f} + açık K/Z {unreal:+.4f} = {beklenen:.4f}; durum equity {eq:.4f}; fark {fark:+.4f} $")
    return kontrol(ad, abs(fark) <= TOL and abs(net_sql - net_motor) <= TOL, parca)


def kontrol_bagimsiz_toplam(net_sql: float | None, brut_sql: float | None, net_motor: float) -> dict:
    ad = "Net K/Z: SQL toplamı = motor toplamı = brüt - komisyon - fonlama"
    if net_sql is None:
        return kontrol(ad, None, "defter SQL toplamı okunamadı")
    ok = abs(net_sql - net_motor) <= TOL and (brut_sql is None or abs(net_sql - brut_sql) <= TOL)
    return kontrol(ad, ok, f"SQL net {net_sql:+.4f}; motor {net_motor:+.4f}; brüt-komisyon-fonlama {('?' if brut_sql is None else f'{brut_sql:+.4f}')}")


def kontrol_acik(motor_n: int, panel_n: int | None, serit_n: int | None, status_n: int | None) -> dict:
    ad = "Açık pozisyon sayısı (motor = panel = şerit = durum)"
    vals = {"motor(defter)": motor_n, "panel": panel_n, "şerit": serit_n, "durum": status_n}
    bilinen = {k: v for k, v in vals.items() if v is not None}
    ok = len(set(bilinen.values())) == 1 and panel_n is not None and serit_n is not None
    return kontrol(ad, ok, ", ".join(f"{k} {v if v is not None else '?'}" for k, v in vals.items()))


def kontrol_acik_kz(status: Mapping | None, panel_acik: Sequence[Mapping]) -> dict:
    """Panelin acik K/Z fiyati = durum dosyasindaki `mark` (motorun son kapanmis 1 dk mumu); piyasa veritabani okunmaz."""
    ad = "Açık K/Z fiyat kaynağı (panel = motor mark)"
    kaynak = "kaynak: durum dosyasındaki mark (motorun son kapanmış 1 dk mumu); panel aynı alanı okur, market.sqlite okunmaz"
    if status is None:
        return kontrol(ad, None, "durum dosyası canlı değil; " + kaynak)
    pos = {p.get("trade_id"): p for p in status.get("open_positions") or [] if isinstance(p, Mapping)}
    if not pos and not panel_acik:
        return kontrol(ad, True, "açık pozisyon yok; " + kaynak)
    sorun, enb = [], 0.0
    for r in panel_acik:
        p = pos.get(r.get("id"))
        if p is None:
            sorun.append(f"#{r.get('id')} durumda yok")
            continue
        mark = p.get("mark")
        if mark is None or r.get("simdi") is None:
            sorun.append(f"#{r.get('id')} mark yok")
            continue
        sgn = 1.0 if str(p.get("side")).lower() == "long" else -1.0
        yeniden = sgn * (float(mark) - float(p["entry_price"])) * float(p["qty"])
        d = max(abs(float(r["simdi"]) - float(mark)) * float(p["qty"]), abs(float(r.get("kz") or 0.0) - yeniden))
        enb = max(enb, d)
        if d > TOL:
            sorun.append(f"#{r.get('id')} fark {d:.4f} $")
    for i in pos:
        if i not in {r.get("id") for r in panel_acik}:
            sorun.append(f"#{i} panelde yok")
    return kontrol(ad, not sorun, f"en büyük fark {enb:.4f} $" + (f"; sorun: {', '.join(sorun)}" if sorun else "") + "; " + kaynak)


def kontrol_limit(panel_oran: float | None, ayar_orani: float | None) -> dict:
    ad = "Günlük zarar limiti oranı (panel = kâğıt ayarı)"
    if panel_oran is None or ayar_orani is None:
        return kontrol(ad, None, "oran okunamadı")
    return kontrol(ad, abs(panel_oran - ayar_orani) < 1e-12,
                   f"panel %{panel_oran * 100:g}; kâğıt ayarı (engine.paper.json) %{ayar_orani * 100:g}")


# ----------------------------------------------------------------------------------------------- ozet
def ozet(rows: Sequence[Mapping], kontroller: Sequence[Mapping], ekstra: Sequence[str], *, now: datetime, panel_notu: str = "",
         telegram_kaynak: str = "") -> dict:
    sat = [r for r in rows if r["uyusmazlik"]]
    kal = [k for k in kontroller if k["sonuc"] == "kaldı"]
    liste = ([f"#{r['islem_no']} {r['coin']} {r['yon']}: " + "; ".join(r["uyusmazlik"]) for r in sat]
             + list(ekstra) + [f"kontrol: {k['ad']} - {k['ayrinti']}" for k in kal])
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
            "panel_notu": panel_notu, "kontroller": list(kontroller)}


def markdown(doc: Mapping, rows: Sequence[Mapping]) -> str:
    def f(x, nd=4):
        return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))
    L = ["# İşlem mutabakatı", "",
         f"Son kontrol: {doc['uretim_tsi']} (TSİ). İşlem: {doc['islem_sayisi']} (kapanan {doc['kapanan']}, açık {doc['acik']}). "
         f"Uyuşmazlık: {doc['uyusmazlik_sayisi']}.", "", "## Kontroller", "", "| Kontrol | Sonuç | Ayrıntı |", "|---|---|---|"]
    L += [f"| {k['ad']} | {k['sonuc']} | {k['ayrinti']} |" for k in doc["kontroller"]]
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
