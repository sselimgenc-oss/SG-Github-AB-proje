#!/usr/bin/env python3
"""Islem mutabakati (gunluk + her kurulum sonrasi; YALNIZ BILGI: motoru etkilemez, islem engellemez).

Her islem icin motor defteri (acik + kapanan; SALT OKUNUR, gocurme yok) = panelin veri katmani (`PanelData.pano/kapanan`, ayni
defter/durum dosyasi, surec ici) = Telegram (gonderim kaydi, outbox `sent` isaretleri, imlec). Ek kontroller: long/short toplamlari,
kasa denklemi (SQL'den bagimsiz toplam), acik pozisyon sayisi, acik K/Z fiyat kaynagi, gunluk limit orani.
Ciktilar: `<veri>/var/durum/mutabakat_v1.json` (ozet + satirlar; herkese acik ikiz Worker'a da yayimlanir) ve `mutabakat.md`.
Uyusmazlik > 0 ise gunde bir Telegram mesaji (outbox'a yazilir; mesaji telegram servisi gonderir). Kilitli donem verisi okunmaz.
Telegram gecmisine erisim yoktur: kaynak = motorun gonderim kaydi (`islem_gonderildi.jsonl`; yoksa outbox isaretleri ve imlec).
Cikis: 0 (uyusmazlik olsa da); 2: defter okunamadi.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import ledger as L  # noqa: E402
from trader_core import mutabakat as M  # noqa: E402
from trader_core import panel_data as P  # noqa: E402
from trader_core import tg_sade as TS  # noqa: E402
from trader_engine.fileio import atomic_write_text  # noqa: E402
from trader_panel.data import PanelData, load_config  # noqa: E402

BOT = "learner"
KAYNAK_NOTU = ("Telegram geçmişine erişim yok; motorun gönderdi kaydı (imleç) kullanıldı. Sıra: (1) gönderim kaydı "
               "islem_gonderildi.jsonl (ts, işlem no, tür, yön, K/Z; kayıt başlangıcından itibaren), (2) outbox 'sent' işaretleri "
               "(teslim edilmiş mesajın anahtarı; mesaj metni yok), (3) islem_imleci.json (duyurulmuş işlem numaraları). "
               "Gönderim kaydından önceki işlemlerde imleç yalnız 'duyuruldu' sayıldığını gösterir, mesaj metnini kanıtlamaz; "
               "mesaj sisteminden önceki işlemler 'Telegram öncesi' sayılır, uyuşmazlık değildir.")


def data_root(env) -> Path:
    v = (env.get("TRADER_DATA_ROOT") or "").strip()
    return Path(v) if v and os.path.isabs(v) else _HERE.parent


def _json(p: Path):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _parse_z(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def gonderim_kaydi(path: Path) -> dict:
    """islem_gonderildi.jsonl -> {(trade_id, tur): satir + '_ts'}; bozuk satir atlanir, son kayit gecerli."""
    out: dict = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            d = json.loads(ln)
            ts = _parse_z(d["ts"])
            if ts is not None and d.get("tur") in ("acildi", "kapandi"):
                out[(int(d["trade_id"]), d["tur"])] = {**d, "_ts": ts}
        except (ValueError, KeyError, TypeError):
            continue
    return out


def sql_toplam(ledger_path: Path) -> tuple[float | None, float | None]:
    """Panel/motor fonksiyonlarindan BAGIMSIZ: kapanan islemlerin net (realized_pnl) ve brut-komisyon-fonlama toplamlari."""
    try:
        c = sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True, timeout=5)
        try:
            r = c.execute("SELECT SUM(realized_pnl), SUM(gross_pnl - fee_entry - COALESCE(fee_exit, 0) - COALESCE(funding_paid, 0)) "
                          "FROM v_closed_trades WHERE bot=?", (BOT,)).fetchone()
        finally:
            c.close()
        return float(r[0] or 0.0), float(r[1] or 0.0)
    except sqlite3.Error:
        return None, None


def ayar_orani(config_dir: Path) -> float | None:
    risk: dict = {}
    for ad in ("engine.base.json", "engine.learner.json", "engine.paper.json"):
        d = _json(config_dir / ad)
        if d and isinstance(d.get("risk"), dict):
            risk.update(d["risk"])
    v = risk.get("daily_max_loss")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def isaret_fonksiyonu(tg_dir: Path, rows: list[dict]):
    sent = tg_dir / "outbox" / "sent"
    gruplar: dict = {}
    for r in sorted(rows, key=lambda r: (r["_a"], r["islem_no"])):
        gruplar.setdefault(r["_a"].strftime("%Y-%m-%dT%H:%M"), []).append(r["islem_no"])
    dakika = {i: dk for dk, ids in gruplar.items() for i in ids}

    def var(key: str) -> bool:
        return (sent / hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]).exists()

    def f(i: int, tur: str) -> bool:
        if tur == "kapandi":
            return var(f"islem-kapat:{i}")
        return var(f"islem-ac:{i}") or var("islem-ac:" + "-".join(str(x) for x in gruplar.get(dakika.get(i), [])))
    return f


def telegram_bildir(root_tg: Path, durum_dir: Path, doc: dict | int, now: datetime) -> bool:
    """Gunde en cok bir mesaj (kurulum ozetiyle ayni sade bicim): outbox'a yazar (telegram servisi gonderir). Yazilamazsa False."""
    n = doc if isinstance(doc, int) else int(doc.get("uyusmazlik_sayisi") or 0)
    gun = now.astimezone(M.TR).date().isoformat()
    isaret = durum_dir / "mutabakat_bildirim.json"
    if (_json(isaret) or {}).get("gun") == gun:
        return False
    try:
        from trader_core.telegram import Outbox  # noqa: PLC0415
        ok = Outbox(root_tg, lambda: now).enqueue({"text": TS.islem_kontrolu(doc), "severity": "WARN", "dedup_key": f"mutabakat:{gun}",
                                                    "expires_at": None, "reply_markup": None, "created_at": now.timestamp()})
        if ok:
            atomic_write_text(isaret, json.dumps({"gun": gun, "n": n}) + "\n")
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


def kos(root: Path, now: datetime, env, tg_baslangic: datetime | None = None) -> tuple[int, dict | None]:
    cfg_path = root / "config" / "panel.json"
    cfg = load_config(cfg_path)
    led_path = Path(cfg.ledger_path)
    if not led_path.exists():
        print("mutabakat: defter yok; atlandi", file=sys.stderr)
        return 0, None
    led = P.open_ledger_ro(str(led_path), BOT)            # salt okunur, migrate yok
    try:
        kapali = led.list_closed_trades(None, None, P.CLOSED_MAX)
        acik = led.list_open_trades()
        dec = {d.id: d for d in led.list_decisions()}
    finally:
        led.close()

    def kol(t):
        d = dec.get(t.decision_id)
        return TS.kol_adi(getattr(d, "arm_id", None) or d.setup, d.trigger_tf) if d is not None else TS.kol_adi(t.setup)

    rows = M.motor_satirlari(kapali, acik, kol)
    toplam = M.toplamlar(rows)
    # --- panel (surec ici; ayni defter/durum)
    data = PanelData(cfg, clock=lambda: now)
    pano = data.pano(BOT)
    kap = data.kapanan(BOT, "tumu")
    if not pano.get("ok") or not kap.get("ok"):
        return 2, None
    fazla = M.panel_karsilastir(rows, kap["rows"], pano["acik"]["rows"], int(cfg.closed_limit))
    # --- telegram
    tg_dir = Path((env.get("TELEGRAM_VAR_DIR") or "").strip() or root / "var" / "telegram")
    fazla += M.telegram_karsilastir(rows, now=now, kayit=gonderim_kaydi(tg_dir / "islem_gonderildi.jsonl"),
                                    isaretli=isaret_fonksiyonu(tg_dir, rows), imlec=_json(tg_dir / "islem_imleci.json"),
                                    tg_baslangic=tg_baslangic)
    # --- kontroller
    st = P.read_status(cfg.status_path, now)
    status = st["data"] if st["state"] == "live" else None
    net_sql, brut_sql = sql_toplam(led_path)
    try:
        ws = json.loads(Path(cfg.engine_config).read_text(encoding="utf-8")).get("wallet_start")
        ws = float(ws) if isinstance(ws, (int, float)) and not isinstance(ws, bool) else None
    except (OSError, ValueError, AttributeError):
        ws = None
    kontroller = [M.kontrol_kasa(baslangic=ws, net_sql=net_sql, net_motor=toplam["tumu"]["net"], status=status),
                  M.kontrol_bagimsiz_toplam(net_sql, brut_sql, toplam["tumu"]["net"])]
    gorunen = M.toplamlar(M.son_kapanan(rows, int(cfg.closed_limit))) if kap.get("daha_fazla") else toplam   # liste sinirli: ayni kume
    kontroller += M.kontrol_long_short(gorunen, kap["rows"], kap.get("n"), kap.get("net"))
    kontroller.append(M.kontrol_acik(len(acik), pano["acik"]["n"], pano["serit"].get("acik"),
                                     len(status.get("open_positions") or []) if status is not None else None))
    kontroller.append(M.kontrol_acik_kz(status, pano["acik"]["rows"]))
    kontroller.append(M.kontrol_limit(pano["serit"]["risk"].get("limit_orani"), ayar_orani(root / "config")))
    siniri = f"Panel 'tümü' listesi son {int(cfg.closed_limit)} kapanan işlemi gösterir; toplamlar tüm işlemleri kapsar."
    bilgi = [b for b in (M.bilgi_acik_kz(status),) if b]
    doc = M.ozet(rows, kontroller, fazla, now=now, panel_notu=siniri, telegram_kaynak=KAYNAK_NOTU, bilgi=bilgi)
    satirlar = M.temiz(rows)
    durum = root / "var" / "durum"
    atomic_write_text(durum / "mutabakat_v1.json", json.dumps({**doc, "satirlar": satirlar}, ensure_ascii=False, indent=1) + "\n")
    atomic_write_text(durum / "mutabakat.md", M.markdown(doc, rows))
    tam = {**doc, "satirlar": satirlar}
    gitti = kurulum_ozeti(tg_dir, durum, tam, now, env=env)
    if doc["uyusmazlik_sayisi"] > 0 and not gitti:          # tek mesaj: kurulum ozeti gittiyse gunluk uyari ayni kosuda gonderilmez
        telegram_bildir(tg_dir, durum, tam, now)
    return 0, doc


OZET_KAYIT = "mutabakat_ozet_surum.json"      # son ozetin gittigi kod surumu (surum dizini); yeni kurulumda ozet bir kez gider


RELEASE_DOSYASI = "/etc/trader-release"


def kod_surumu(env=None) -> str:
    """Calisan kodun surum kimligi: kurulumun yazdigi /etc/trader-release icindeki `COMMIT=<sha>` (sunucuda betik SABIT bir
    dizinden (/opt/trader) calisir; yol her kurulumda ayni kalir, yalniz commit degisir). Dosya yoksa/okunamazsa eski davranis:
    surum dizininin gercek yolu. Dosya yolu MUTABAKAT_RELEASE_FILE ile degistirilebilir (test)."""
    env = os.environ if env is None else env
    yol = (env.get("MUTABAKAT_RELEASE_FILE") or "").strip() or RELEASE_DOSYASI
    try:
        for ln in Path(yol).read_text(encoding="utf-8").splitlines():
            if ln.startswith("COMMIT="):
                sha = ln[len("COMMIT="):].strip()
                if sha:
                    return "commit:" + sha
                break
    except (OSError, ValueError):
        pass
    return str(Path(__file__).resolve().parent.parent)


def kurulum_ozeti(root_tg: Path, durum_dir: Path, doc: dict, now: datetime, surum: str | None = None, env=None) -> bool:
    """Kurulum sonrasi tek seferlik SESSIZ (INFO) Telegram ozeti: kod surumu son ozettekinden farkliysa bir kez gider.
    Ilk kez (kayit yok) da gider. Hata sessizce False."""
    surum = surum or kod_surumu(env)
    kayit = durum_dir / OZET_KAYIT
    if (_json(kayit) or {}).get("surum") == surum:
        return False
    try:
        from trader_core.telegram import Outbox  # noqa: PLC0415
        ok = Outbox(root_tg, lambda: now).enqueue({"text": TS.islem_kontrolu_ozet(doc), "severity": "INFO",
                                                    "dedup_key": f"mutabakat-ozet:{doc.get('uretim')}", "expires_at": None,
                                                    "reply_markup": None, "created_at": now.timestamp()})
        if ok:
            atomic_write_text(kayit, json.dumps({"surum": surum, "uretim": doc.get("uretim")}) + "\n")
        return bool(ok)
    except Exception:  # noqa: BLE001
        return False


def main(argv=None, now_fn=None, env=None) -> int:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description="Islem mutabakati: motor = panel = Telegram (yalniz bilgi)")
    ap.add_argument("--once", action="store_true", help="bir kez calis (zamanlayici)")
    ap.add_argument("--root", type=Path, default=None, help="veri kok dizini (varsayilan: TRADER_DATA_ROOT ya da kod koku)")
    ap.add_argument("--telegram-baslangic", default=None, help="ISO UTC: bundan once olan olaylar 'Telegram oncesi' sayilir")
    a = ap.parse_args(argv)
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    tgb = _parse_z(a.telegram_baslangic) if a.telegram_baslangic else None
    try:
        code, doc = kos(a.root or data_root(env), now, env, tgb)
    except Exception as e:  # noqa: BLE001
        print(f"mutabakat: hata {type(e).__name__}", file=sys.stderr)
        return 2
    if doc is not None:
        print(f"mutabakat: {doc['islem_sayisi']} islem, {doc['uyusmazlik_sayisi']} uyusmazlik")
    return code


if __name__ == "__main__":
    sys.exit(main())
