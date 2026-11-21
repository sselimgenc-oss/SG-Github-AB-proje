"""Kaldirilan kolun (C1) defter/durum gocu: tek seferlik, idempotent, yedekli, dogrulamali (docs/motor/ct-ayrilik-spec.md bolum 5).

Defterin kendi goc deseni uygulanir (`ledger._run_migrations`): tek islem (`BEGIN IMMEDIATE`) icinde yalnizca-ekleme tetikleyicileri
birakilir, satirlar silinir/duzeltilir, tetikleyicilerin TAMAMI yeniden kurulur, sonra `Ledger._verify` (motorun acilista yaptigi
denetim) ve davranis sinamasi (UPDATE reddedilmeli) ile tetikleyicilerin yerinde oldugu dogrulanir. Sema surumu degismez (veri goc'u).
Sira: (0) motor durdu mu / acik C1 pozisyonu var mi (varsa REDDEDILIR, hicbir sey degismez) -> (1) yedek -> (2) defter -> (3) state
(kasa, gun basi ozsermaye, kol anahtarlari) -> (4) yan dosyalar -> (5) dogrulama -> basariliysa yedek SILINIR, rapor yazilir;
herhangi bir adim basarisizsa yedekten GERI YUKLENIR (yari goc kalmaz).

Kasa ("C1 hic olmamis gibi"): kagit broker cuzdani `state.sqlite` `broker_snapshot.wallet`. Tum C1 islemleri kapaliyken
yeni_kasa = eski_kasa - Σ C1 realized_pnl (realized_pnl = brut - giris/cikis komisyonu - fonlama). Dogrulama: kasa kalani
(kasa + acik islemlerin giris komisyonu/fonlamasi - baslangic - Σ kapanan net K/Z) goc ONCESI ve SONRASI ayni olmali; sifirsa kasa tam
`baslangic + Σ net K/Z (C1 disi)`'dir. Gecmis `equity_marks` ve `day_start:<gun>` ayni kayma ile duzeltilir (C1 acikken oluşan
gerceklesmemis K/Z gecmis fiyatlar olmadan geri alinamaz: o aralikta isaretler yalniz gerceklesen kisimla duzeltilir).
Paper risk kademesi bellekte (gunluk dosyasi yok) ve kol kucultme carpani defterden turetilir: ikisi de yeniden baslatmada kendiliginden
C1'siz yeniden kurulur."""
from __future__ import annotations

import bisect
import contextlib
import json
import logging
import os
import shutil
import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from . import ledger as L

log = logging.getLogger("trader.kol_kaldirma")

KOLLAR = ("C1",)
ISARET = "c1_goc.done"
RAPOR = "c1_goc_raporu.json"
TOL = 1e-6
TRADE_KV_ONEKLERI = ("partial:", "naked:", "ext_reduction:", "exit_retry:", "exit_unresolved_since:", "entry_fee_estimated:", "eq:",
                     "gecikme:")
TURETILMIS_CIKTILAR = ("durum/mutabakat_v1.json", "durum/mutabakat.md", "durum/strateji-veri-ml.md", "durum/tutarlilik_v1.json")


class GocReddedildi(Exception):
    """Onkosul saglanmadi (motor calisiyor / acik C1 pozisyonu): hicbir sey degismedi; sonra yeniden denenir."""


class GocHatasi(Exception):
    """Goc ya da dogrulama basarisiz (geri yuklendi ya da geri yukleme de basarisiz: mesaj belirtir)."""


def _z(dt: datetime) -> str:
    return L._fmt_ts(dt)


def _yer(n: int) -> str:
    return ",".join("?" * n)


def _con(path, *, ro: bool = False) -> sqlite3.Connection:
    p = os.fspath(path)
    if ro:
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10, isolation_level=None)
    else:
        c = sqlite3.connect(p, timeout=10, isolation_level=None)
    c.execute("PRAGMA busy_timeout=10000")
    return c


# ----------------------------------------------------------------------------------------------- on kosullar / plan
def _plan(ledger_path: Path, state_path: Path, kollar: Sequence[str]) -> dict:
    kl = tuple(kollar)
    sc = _con(state_path, ro=True)
    try:
        acik = sc.execute(f"SELECT trade_id, setup, status FROM positions WHERE setup IN ({_yer(len(kl))}) AND status != 'closed'", kl).fetchall()
        s_ids = [r[0] for r in sc.execute(f"SELECT trade_id FROM positions WHERE setup IN ({_yer(len(kl))})", kl)]
        snap_raw = sc.execute("SELECT v FROM kv WHERE k='broker_snapshot'").fetchone()
        bekleyen = (sc.execute(f"SELECT COUNT(*) FROM ledger_outbox WHERE done=0 AND trade_id IN ({_yer(len(s_ids))})", s_ids).fetchone()[0]
                    if s_ids else 0)
    finally:
        sc.close()
    if bekleyen:
        raise GocReddedildi(f"{bekleyen} C1 outbox satiri defterde bekliyor; motor acilista bosaltir")
    if acik:
        raise GocReddedildi(f"acik {','.join(kl)} pozisyonu var ({[tuple(a) for a in acik]}); once motor kapatmali")
    lc = _con(ledger_path, ro=True)
    try:
        lc.row_factory = sqlite3.Row
        acik_l = lc.execute(f"SELECT trade_id FROM v_trades WHERE setup IN ({_yer(len(kl))}) AND exit_ts IS NULL", kl).fetchall()
        if acik_l:
            raise GocReddedildi(f"defterde kapanmamis {','.join(kl)} islemi var: {[r[0] for r in acik_l]}")
        trades = [dict(r) for r in lc.execute(
            f"SELECT bot, trade_id, entry_ts, exit_ts, realized_pnl, fee_entry, fee_exit, funding_paid, gross_pnl FROM v_trades "
            f"WHERE setup IN ({_yer(len(kl))})", kl)]
        raw_ids = [tuple(r) for r in lc.execute(f"SELECT DISTINCT bot, trade_id FROM trade_entries WHERE setup IN ({_yer(len(kl))})", kl)]
        meta = {r[0]: r[1] for r in lc.execute("SELECT key, value FROM meta")}
    finally:
        lc.close()
    if snap_raw is None:
        raise GocHatasi("state.sqlite icinde broker_snapshot yok (kagit cuzdani okunamadi)")
    snap = json.loads(snap_raw[0])
    pos_snap = snap.get("positions") or {}
    return {"trades": trades, "raw_ids": raw_ids, "tids": sorted({t for _, t in raw_ids} | set(s_ids)), "snap": snap,
            "pos_snap": pos_snap, "bot": meta.get("bot", "learner")}


class _Kayma:
    """Zamana gore C1'in kasaya yansittigi kayma: kapananlarin net K/Z'si - acik C1 islemlerinin giris komisyonu."""

    def __init__(self, trades: Sequence[dict]) -> None:
        kap = sorted((t["exit_ts"], float(t["realized_pnl"] or 0.0)) for t in trades if t["exit_ts"])
        self.x_ts = [a for a, _ in kap]
        self.x_cum = [0.0]
        for _, r in kap:
            self.x_cum.append(self.x_cum[-1] + r)
        ent = sorted((t["entry_ts"], float(t["fee_entry"] or 0.0)) for t in trades)
        self.e_ts = [a for a, _ in ent]
        self.e_cum = [0.0]
        for _, f in ent:
            self.e_cum.append(self.e_cum[-1] + f)
        xf = sorted((t["exit_ts"], float(t["fee_entry"] or 0.0)) for t in trades if t["exit_ts"])
        self.xf_ts = [a for a, _ in xf]
        self.xf_cum = [0.0]
        for _, f in xf:
            self.xf_cum.append(self.xf_cum[-1] + f)
        self.n = len(trades)

    def delta(self, ts: str) -> float:
        k = bisect.bisect_right(self.x_ts, ts)
        e = bisect.bisect_right(self.e_ts, ts)
        xf = bisect.bisect_right(self.xf_ts, ts)
        acik_komisyon = self.e_cum[e] - self.xf_cum[xf]
        return self.x_cum[k] - acik_komisyon

    def n_open(self, ts: str) -> int:
        return bisect.bisect_right(self.e_ts, ts) - bisect.bisect_right(self.xf_ts, ts)

    def toplam(self) -> float:
        return self.x_cum[-1]


# ----------------------------------------------------------------------------------------------- yedek / geri yukleme
def _sqlite_yedek(src: Path, dst: Path) -> None:
    s = _con(src, ro=True)
    try:
        d = sqlite3.connect(os.fspath(dst))
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def _yedekle(var: Path, yedek: Path, sqlites: Sequence[Path], dosyalar: Sequence[Path]) -> list[tuple[Path, Path, str]]:
    yedek.mkdir(parents=True, exist_ok=True)
    kayit: list[tuple[Path, Path, str]] = []          # (hedef, yedek dosyasi, tur)
    for i, p in enumerate(sqlites):
        if p.is_file():
            b = yedek / f"{i}-{p.name}"
            _sqlite_yedek(p, b)
            kayit.append((p, b, "sqlite"))
    for i, p in enumerate(dosyalar):
        if p.is_file():
            b = yedek / f"f{i}-{p.name}"
            shutil.copy2(p, b)
            kayit.append((p, b, "dosya"))
    return kayit


def _geri_yukle(kayit: Sequence[tuple[Path, Path, str]]) -> None:
    for hedef, b, tur in kayit:
        if tur == "sqlite":
            for ek in ("-wal", "-shm", "-journal"):
                with contextlib.suppress(OSError):
                    os.unlink(os.fspath(hedef) + ek)
        shutil.copy2(b, hedef)


# ----------------------------------------------------------------------------------------------- defter
def _betik(c: sqlite3.Connection, script: str) -> None:
    """`executescript` acik islemi COMMIT eder; tek islem korunsun diye deyimler tek tek calistirilir (tetikleyici govdesi ';' tasir)."""
    buf = ""
    for ln in script.splitlines():
        buf += ln + "\n"
        if sqlite3.complete_statement(buf):
            c.execute(buf)
            buf = ""
    if buf.strip():
        raise GocHatasi("eksik SQL deyimi")


def _defter_goc(ledger_path: Path, kollar: Sequence[str], kayma: _Kayma, now: datetime) -> dict:
    kl = tuple(kollar)
    c = _con(ledger_path)
    sayilar: dict[str, int] = {}
    try:
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute("CREATE TEMP TABLE _kal(bot TEXT, trade_id INTEGER)")
            c.execute(f"INSERT INTO _kal SELECT DISTINCT bot, trade_id FROM trade_entries WHERE setup IN ({_yer(len(kl))})", kl)
            for n in sorted(L._EXPECTED_TRIGGERS):
                c.execute(f"DROP TRIGGER IF EXISTS {n}")

            def sil(tablo: str, where: str, args: Sequence = ()) -> None:
                sayilar[tablo] = c.execute(f"DELETE FROM {tablo} WHERE {where}", tuple(args)).rowcount

            sil("trade_exits", "EXISTS (SELECT 1 FROM _kal k WHERE k.bot=trade_exits.bot AND k.trade_id=trade_exits.trade_id)")
            sil("trade_notes", "trade_id IN (SELECT trade_id FROM _kal)")
            sil("trade_entries", f"setup IN ({_yer(len(kl))})", kl)
            sil("decision_events", f"setup IN ({_yer(len(kl))})", kl)
            sil("shadow_decisions", f"setup IN ({_yer(len(kl))})", kl)
            # gecmis kasa isaretleri: C1 etkisi cikarilir (kayma zamanla)
            rows = c.execute("SELECT id, ts, wallet, equity, equity_low, n_open FROM equity_marks").fetchall()
            duz = 0
            for i, ts, w, e, lo, n in rows:
                d = kayma.delta(ts)
                no = kayma.n_open(ts)
                if abs(d) > 0 or no:
                    c.execute("UPDATE equity_marks SET wallet=?, equity=?, equity_low=?, n_open=? WHERE id=?",
                              (w - d, e - d, lo - d, max(0, int(n) - no), i))
                    duz += 1
            sayilar["equity_marks_duzeltilen"] = duz
            c.execute("DROP TABLE _kal")
            _betik(c, L._trigger_ddl(L._APPEND_ONLY_TABLES) + "\n" + L._EXCURSION_TRIGGER_DDL)
            c.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("kol_kaldirildi:" + ",".join(kl), _z(now)))
            bad = c.execute("PRAGMA foreign_key_check").fetchall()
            if bad:
                raise GocHatasi(f"goc sonrasi yabanci anahtar ihlali: {len(bad)} satir")
            c.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                c.execute("ROLLBACK")
            raise
    finally:
        c.close()
    return sayilar


# ----------------------------------------------------------------------------------------------- state
def _state_goc(state_path: Path, plan: dict, kayma: _Kayma) -> dict:
    c = _con(state_path)
    sayilar: dict[str, int] = {}
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            tids = plan["tids"]
            cids = [r[0] for r in c.execute(f"SELECT client_id FROM orders WHERE trade_id IN ({_yer(len(tids))})", tids)] if tids else []
            sayilar["positions"] = c.execute(f"DELETE FROM positions WHERE trade_id IN ({_yer(len(tids))})", tids).rowcount if tids else 0
            sayilar["orders"] = c.execute(f"DELETE FROM orders WHERE trade_id IN ({_yer(len(tids))})", tids).rowcount if tids else 0
            sayilar["ledger_outbox"] = (c.execute(f"DELETE FROM ledger_outbox WHERE trade_id IN ({_yer(len(tids))})", tids).rowcount
                                        if tids else 0)
            kv = 0
            for t in tids:
                for pre in TRADE_KV_ONEKLERI:
                    kv += c.execute("DELETE FROM kv WHERE k=?", (f"{pre}{t}",)).rowcount
            for cid in cids:
                kv += c.execute("DELETE FROM kv WHERE k=?", ("broker_order:" + cid,)).rowcount
            sayilar["kv"] = kv
            # kasa
            snap = dict(plan["snap"])
            eski = float(snap["wallet"])
            yeni = eski - kayma.toplam()
            snap["wallet"] = yeni
            c.execute("UPDATE kv SET v=? WHERE k='broker_snapshot'", (json.dumps(snap, sort_keys=True),))
            # gun basi ozsermaye (gun 00:00 UTC itibariyla kayma)
            gd = 0
            for k, v in c.execute("SELECT k, v FROM kv WHERE k LIKE 'day_start:%'").fetchall():
                try:
                    val = float(json.loads(v))
                except (ValueError, TypeError):
                    continue
                gun = k.split(":", 1)[1]
                d = kayma.delta(gun + "T00:00:00.000Z")
                if abs(d) > 0:
                    c.execute("UPDATE kv SET v=? WHERE k=?", (json.dumps(val - d, sort_keys=True), k))
                    gd += 1
            sayilar["day_start_duzeltilen"] = gd
            c.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                c.execute("ROLLBACK")
            raise
    finally:
        c.close()
    return sayilar


# ----------------------------------------------------------------------------------------------- yan dosyalar
def _yan_dosyalar(var: Path, kollar: Sequence[str], tids: set[int]) -> dict:
    kl = tuple(kollar)
    out: dict[str, int] = {}
    for ad, tablolar in (("learner/counterfactual.sqlite", ("cf_outcomes", "cf_shadow_outcomes")),
                         ("learner/exit_counterfactual.sqlite", ("ecf_outcomes", "ecf_modes"))):
        p = var / ad
        if not p.is_file():
            continue
        c = _con(p)
        try:
            for t in tablolar:
                cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
                if "setup" in cols:
                    out[t] = c.execute(f"DELETE FROM {t} WHERE setup IN ({_yer(len(kl))})", kl).rowcount
        finally:
            c.close()
    tg = var / "telegram"
    jl = tg / "islem_gonderildi.jsonl"
    if jl.is_file():
        keep, n = [], 0
        for ln in jl.read_text(encoding="utf-8").splitlines():
            try:
                tid = int(json.loads(ln).get("trade_id"))
            except (ValueError, TypeError, AttributeError):
                keep.append(ln)
                continue
            if tid in tids:
                n += 1
            else:
                keep.append(ln)
        if n:
            jl.write_text("".join(x + "\n" for x in keep), encoding="utf-8")
        out["islem_gonderildi_satir"] = n
    im = tg / "islem_imleci.json"
    if im.is_file():
        try:
            d = json.loads(im.read_text(encoding="utf-8"))
            n = 0
            for k in ("acilan", "kapanan"):
                if isinstance(d.get(k), list):
                    y = [x for x in d[k] if x not in tids]
                    n += len(d[k]) - len(y)
                    d[k] = y
            if n:
                im.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            out["islem_imleci"] = n
        except (ValueError, OSError, AttributeError):
            pass
    ts = 0
    for rel in TURETILMIS_CIKTILAR:
        p = var / rel
        if p.is_file():
            p.unlink()
            ts += 1
    out["turetilmis_cikti_silinen"] = ts
    return out


# ----------------------------------------------------------------------------------------------- dogrulama
def _kasa_kalani(ledger_path: Path, state_path: Path, wallet_start: float, kollar: Sequence[str] | None) -> dict:
    """kalan = kasa + acik islemlerin giris komisyonu ve fonlamasi - baslangic - Σ kapanan net K/Z (kollar verilirse O kollar haric)."""
    sc = _con(state_path, ro=True)
    try:
        snap = json.loads(sc.execute("SELECT v FROM kv WHERE k='broker_snapshot'").fetchone()[0])
    finally:
        sc.close()
    lc = _con(ledger_path, ro=True)
    try:
        if kollar:
            net = lc.execute(f"SELECT COALESCE(SUM(realized_pnl),0) FROM v_closed_trades WHERE setup NOT IN ({_yer(len(kollar))})",
                             tuple(kollar)).fetchone()[0]
        else:
            net = lc.execute("SELECT COALESCE(SUM(realized_pnl),0) FROM v_closed_trades").fetchone()[0]
    finally:
        lc.close()
    acik = sum(float(p.get("fee_paid_entry") or 0.0) + float(p.get("funding_paid") or 0.0) for p in (snap.get("positions") or {}).values())
    wallet = float(snap["wallet"])
    return {"wallet": wallet, "net_kapanan": float(net), "acik_komisyon_fonlama": acik,
            "kalan": wallet + acik - wallet_start - float(net)}


def _tetikler_ve_butunluk(ledger_path: Path, kollar: Sequence[str]) -> bool:
    """Motorun acilista yaptigi `_verify` + tetikleyici davranis sinamasi + FK/butunluk + C1 kalmadi."""
    c = _con(ledger_path, ro=True)
    try:
        bot = c.execute("SELECT value FROM meta WHERE key='bot'").fetchone()[0]
    finally:
        c.close()
    led = L.open_ledger(ledger_path, bot, create=False, migrate=False)         # Ledger._verify burada calisir (eksik tetikleyici -> hata)
    led.close()
    c = _con(ledger_path)
    try:
        trig = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        if not L._EXPECTED_TRIGGERS <= trig:
            raise GocHatasi(f"eksik tetikleyici: {sorted(L._EXPECTED_TRIGGERS - trig)[:3]}")
        c.execute("BEGIN")
        try:
            try:
                c.execute("UPDATE meta SET value=value WHERE key='bot'")
            except sqlite3.DatabaseError as e:
                if "append-only" not in str(e):
                    raise
            else:
                raise GocHatasi("yalnizca-ekleme tetikleyicisi UPDATE'i reddetmedi")
        finally:
            c.execute("ROLLBACK")
        if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise GocHatasi("integrity_check basarisiz")
        if c.execute("PRAGMA foreign_key_check").fetchall():
            raise GocHatasi("foreign_key_check basarisiz")
        kl = tuple(kollar)
        for t in ("decision_events", "trade_entries", "shadow_decisions"):
            if c.execute(f"SELECT COUNT(*) FROM {t} WHERE setup IN ({_yer(len(kl))})", kl).fetchone()[0]:
                raise GocHatasi(f"{t} icinde {','.join(kl)} kaldi")
    finally:
        c.close()
    return True


def _state_temiz(state_path: Path, kollar: Sequence[str]) -> None:
    c = _con(state_path, ro=True)
    try:
        kl = tuple(kollar)
        if c.execute(f"SELECT COUNT(*) FROM positions WHERE setup IN ({_yer(len(kl))})", kl).fetchone()[0]:
            raise GocHatasi("state.positions icinde kaldirilan kol kaldi")
    finally:
        c.close()


# ----------------------------------------------------------------------------------------------- ana akis
def _yedek_temizle(yedek: Path) -> None:
    shutil.rmtree(yedek, ignore_errors=True)
    with contextlib.suppress(OSError):
        yedek.parent.rmdir()                                   # bos kaldiysa var/yedek de kalkar (arsiv istenmiyor)


def _atomik_json(p: Path, doc: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def calistir(var_dir, *, wallet_start: float, kollar: Sequence[str] = KOLLAR, now: datetime | None = None,
             bildir: Callable[[str], None] | None = None, motor_aktif_fn: Callable[[], bool] | None = None,
             yedek_sil: bool = True) -> dict:
    """Doner: rapor sozlugu (durum: 'tamam' | 'zaten_yapildi'). Hata: GocReddedildi (degisiklik yok) / GocHatasi (geri yuklendi)."""
    var = Path(var_dir)
    now = now or datetime.now(timezone.utc)
    ledger_path, state_path = var / "learner" / "ledger.sqlite", var / "learner" / "state.sqlite"
    isaret = var / ISARET
    if isaret.is_file():
        return {"durum": "zaten_yapildi"}
    if not ledger_path.is_file() or not state_path.is_file():
        raise GocReddedildi("defter ya da state dosyasi yok")
    if motor_aktif_fn is not None and motor_aktif_fn():
        raise GocReddedildi("motor calisiyor; once durdurulmali")
    plan = _plan(ledger_path, state_path, kollar)
    kayma = _Kayma(plan["trades"])
    if not plan["tids"]:                                       # silinecek bir sey yok: yalniz isaret (tekrar calistirmada no-op)
        rapor = {"durum": "tamam", "zaman": _z(now), "eski_kasa": plan["snap"]["wallet"], "yeni_kasa": plan["snap"]["wallet"],
                 "silinen": {}, "tetikler_dogrulandi": True, "not": "silinecek C1 kaydi yoktu"}
        _atomik_json(var / "durum" / RAPOR, {k: v for k, v in rapor.items() if k != "durum"})
        isaret.write_text(_z(now) + "\n", encoding="utf-8")
        return rapor
    yedek = var / "yedek" / ("c1-goc-" + now.strftime("%Y%m%dT%H%M%SZ"))
    sqlites = [ledger_path, state_path, var / "learner" / "counterfactual.sqlite", var / "learner" / "exit_counterfactual.sqlite"]
    dosyalar = [var / "telegram" / "islem_gonderildi.jsonl", var / "telegram" / "islem_imleci.json"] + [var / r for r in TURETILMIS_CIKTILAR]
    kayit = _yedekle(var, yedek, sqlites, dosyalar)
    eski_kalan = _kasa_kalani(ledger_path, state_path, wallet_start, None)
    try:
        silinen = {"defter": _defter_goc(ledger_path, kollar, kayma, now)}
        silinen["state"] = _state_goc(state_path, plan, kayma)
        silinen["yan_dosyalar"] = _yan_dosyalar(var, kollar, set(plan["tids"]))
        tetik = _tetikler_ve_butunluk(ledger_path, kollar)
        _state_temiz(state_path, kollar)
        yeni_kalan = _kasa_kalani(ledger_path, state_path, wallet_start, kollar)
        if abs(yeni_kalan["kalan"] - eski_kalan["kalan"]) > TOL:
            raise GocHatasi(f"kasa kalani degisti: once {eski_kalan['kalan']:.9f}, sonra {yeni_kalan['kalan']:.9f}")
        beklenen = eski_kalan["wallet"] - kayma.toplam()
        if abs(yeni_kalan["wallet"] - beklenen) > TOL:
            raise GocHatasi(f"yeni kasa beklenenden farkli: {yeni_kalan['wallet']} != {beklenen}")
    except BaseException as e:
        log.critical("C1 gocu BASARISIZ, yedekten geri yukleniyor: %s: %s", type(e).__name__, e)
        try:
            _geri_yukle(kayit)
            tetik_geri = _tetikler_ve_butunluk(ledger_path, ())
            durum = f"geri yuklendi (tetikleyiciler dogrulandi={tetik_geri})"
        except BaseException as e2:  # noqa: BLE001
            durum = f"GERI YUKLEME DE BASARISIZ ({type(e2).__name__}: {e2}); yedek duruyor: {yedek}"
            log.critical("%s", durum)
            if bildir:
                with contextlib.suppress(Exception):
                    bildir(f"CRIT: C1 kaldirma gocu basarisiz ve {durum}")
            raise GocHatasi(durum) from e
        if bildir:
            with contextlib.suppress(Exception):
                bildir(f"CRIT: C1 kaldirma gocu basarisiz: {type(e).__name__}: {e} - {durum}")
        _yedek_temizle(yedek)
        raise GocHatasi(f"{type(e).__name__}: {e}; {durum}") from e
    rapor = {"zaman": _z(now), "eski_kasa": round(eski_kalan["wallet"], 6), "yeni_kasa": round(yeni_kalan["wallet"], 6),
             "kaldirilan_net_kz": round(kayma.toplam(), 6), "kasa_kalani": round(yeni_kalan["kalan"], 9),
             "silinen_kayit": silinen, "tetikler_dogrulandi": bool(tetik), "kasa_dogrulandi": True}
    _atomik_json(var / "durum" / RAPOR, rapor)
    isaret.write_text(_z(now) + "\n", encoding="utf-8")
    if yedek_sil:
        _yedek_temizle(yedek)
    if bildir:
        with contextlib.suppress(Exception):
            bildir(f"[ML] Kasa: {rapor['eski_kasa']:.2f} $ -> {rapor['yeni_kasa']:.2f} $ (C1 kaydi kaldirildi; "
                   f"{rapor['kaldirilan_net_kz']:+.2f} $ cikarildi)")
    return {"durum": "tamam", **rapor}
