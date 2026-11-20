"""C1 (CT kadro) uygulama testleri: okuyucu dogrulamasi (yerel http stub; ag yok), eslestirme, bayatlik, C1 sinyal kurallari,
defter ozellikleri, saglik uyarisi. Belirtim: docs/motor/c1-ct-kadro-spec.md."""
from __future__ import annotations

import http.server
import json
import os
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from trader_core import ct_kadro as CK  # noqa: E402
from trader_core import indicators as I  # noqa: E402
from trader_engine.strategies import arms as AR  # noqa: E402
from trader_engine.strategies.arms import ArmInput  # noqa: E402
from trader_engine.strategies.arms import c1 as C1  # noqa: E402
import ct_kadro_cek as K  # noqa: E402
import health_run as HR  # noqa: E402

UTC = timezone.utc
BARS = pd.date_range("2026-11-01", periods=60, freq="1h", tz="UTC")
D = BARS[-1].to_pydatetime() + timedelta(hours=1)          # karar ani: son kapanmis bar = D - 1 saat


def _zaman(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _belge(uretildi: datetime, coinler: list, sema: str = "ct.kadro_yon.v1") -> dict:
    return {"sema": sema, "uretildi_utc": _zaman(uretildi), "coinler": coinler}


def _oge(coin="BTC", long=4, short=1, net="long", nom=1000.0) -> dict:
    return {"coin": coin, "long_trader": long, "short_trader": short, "net_yon": net, "net_nominal_usd": nom}


_SAYAC = [0]


def _yaz(path: Path, doc: dict) -> Path:
    """Dosyayi yazar ve mtime'i benzersiz kilar (ayni tik icinde tekrar yazimda onbellek kacmasin)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    _SAYAC[0] += 1
    t = 1_800_000_000 + _SAYAC[0]
    os.utime(path, (t, t))
    return path


@pytest.fixture
def kadro_yolu(tmp_path, monkeypatch):
    p = tmp_path / "ct" / "kadro_yon.json"
    monkeypatch.setenv("TRADER_CT_KADRO", str(p))
    C1._CACHE.update(path=None, mtime=None, doc=None)
    C1._EMITTED.clear()
    return p


# ----------------------------------------------------------------------------- okuyucu (yerel http stub)
@pytest.fixture(autouse=True)
def _yerel_stub_proxysiz(monkeypatch):
    """Yerel stub (127.0.0.1) ortam proxy'sinden gecmesin: test yalniz loopback konusur."""
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")


@contextmanager
def _stub(status: int, body: bytes):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):   # sessiz
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/kadro.json"
    finally:
        srv.shutdown()
        srv.server_close()


def _durum(var: Path) -> dict:
    return json.loads((var / "ct" / "durum.json").read_text(encoding="utf-8"))


def test_reader_writes_valid_payload_byte_exact_and_counts_invalid(tmp_path):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    coinler = [_oge("BTC"), _oge("dex:NVDA", 1, 0, "long", None), {"coin": "ETH", "long_trader": -1},
               _oge("SOL", 0, 0, "notr", None)]
    body = json.dumps(_belge(now - timedelta(minutes=5), coinler)).encode("utf-8")
    with _stub(200, body) as url:
        assert K.kos(url, tmp_path, now, allow_http=True) == K.EXIT_OK
    assert (tmp_path / "ct" / "kadro_yon.json").read_bytes() == body          # aynen gelen JSON
    d = _durum(tmp_path)
    assert d["son_basari"] == "2026-11-19T12:00:00Z" and d["son_hata"] is None and d["gecersiz_oge"] == 1
    assert d["son_deneme"] == "2026-11-19T12:00:00Z"


def test_reader_schema_mismatch_writes_nothing_but_records_error(tmp_path):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    body = json.dumps(_belge(now, [_oge()], sema="baska.v9")).encode("utf-8")
    with _stub(200, body) as url:
        K.kos(url, tmp_path, now, allow_http=True)
    assert not (tmp_path / "ct" / "kadro_yon.json").exists()
    d = _durum(tmp_path)
    assert d["son_basari"] is None and "sema" in d["son_hata"]


def test_reader_non_200_is_error_and_keeps_previous_success(tmp_path):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    (tmp_path / "ct").mkdir()
    (tmp_path / "ct" / "durum.json").write_text(json.dumps({"son_basari": "2026-11-19T11:50:00Z"}), encoding="utf-8")
    with _stub(503, b"{}") as url:
        assert K.kos(url, tmp_path, now, allow_http=True) == K.EXIT_OK
    d = _durum(tmp_path)
    assert d["son_hata"] == "http 503" and d["son_basari"] == "2026-11-19T11:50:00Z"
    assert not (tmp_path / "ct" / "kadro_yon.json").exists()


def test_reader_rejects_bad_json_and_bad_timestamp(tmp_path):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    with _stub(200, b"<html>") as url:
        K.kos(url, tmp_path, now, allow_http=True)
    assert _durum(tmp_path)["son_hata"]
    bad = {"sema": "ct.kadro_yon.v1", "uretildi_utc": "19.11.2026 12:00", "coinler": []}
    with _stub(200, json.dumps(bad).encode()) as url:
        K.kos(url, tmp_path, now, allow_http=True)
    assert "uretildi_utc" in _durum(tmp_path)["son_hata"]


def test_reader_stale_uretildi_is_not_success(tmp_path):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    body = json.dumps(_belge(now - timedelta(minutes=60), [_oge()])).encode()
    with _stub(200, body) as url:
        K.kos(url, tmp_path, now, allow_http=True)
    d = _durum(tmp_path)
    assert d["son_basari"] is None and "bayat" in d["son_hata"]
    assert (tmp_path / "ct" / "kadro_yon.json").exists()                     # dosya yazilir; C1 yine yasi denetler


def test_reader_refuses_plain_http_without_test_flag():
    with pytest.raises(K.CekHatasi):
        K.getir("http://example.invalid/kadro.json")


def test_reader_unit_and_timer_contract():
    svc = (ROOT / "deploy" / "trader-ct-kadro.service").read_text(encoding="utf-8")
    tm = (ROOT / "deploy" / "trader-ct-kadro.timer").read_text(encoding="utf-8")
    assert "ct_kadro_cek.py" in svc and "User=trader" in svc and "MemoryMax=100M" in svc
    assert "ReadWritePaths=/opt/trader/var/ct" in svc and "OnUnitActiveSec=5min" in tm and "OnBootSec=3min" in tm


# ----------------------------------------------------------------------------- eslestirme ve bayatlik (saf)
@pytest.mark.parametrize("coin,beklenen", [("kPEPE", "1000PEPE/USDT"), ("kSHIB", "1000SHIB/USDT"),
                                           ("dex:NVDA", "NVDA/USDT"), ("xyz:NVDA", "NVDA/USDT"), ("BTC", "BTC/USDT"),
                                           ("dex:AAPL", "AAPL/USDT")])
def test_mapping_known_forms(coin, beklenen):
    assert CK.hl_to_binance(coin) == beklenen


def test_mapping_unknown_and_evren_membership():
    assert CK.hl_to_binance("FOOBAR") == "FOOBAR/USDT"                                          # evren yoksa uyelik denetlenmez
    assert CK.hl_to_binance("FOOBAR", {"BTC/USDT"}) is None                                     # evren disi -> None
    assert CK.hl_to_binance("kPEPE", {"1000PEPE/USDT"}) == "1000PEPE/USDT"
    assert CK.hl_to_binance("dex:NVDA", {"NVDA/USDT"}) == "NVDA/USDT"
    for bad in ("", "btc", "BTC:X", "a:b:c", "dex:", "kpepe", None, 7):
        assert CK.hl_to_binance(bad) is None


def test_staleness_window_and_future_tolerance(kadro_yolu):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    _yaz(kadro_yolu, _belge(now - timedelta(minutes=44), [_oge()]))
    assert CK.oku(kadro_yolu, now) is not None and "_uretildi" in CK.oku(kadro_yolu, now)
    _yaz(kadro_yolu, _belge(now - timedelta(minutes=46), [_oge()]))
    assert CK.oku(kadro_yolu, now) is None                                 # 45 dk siniri
    _yaz(kadro_yolu, _belge(now + timedelta(minutes=3), [_oge()]))
    assert CK.oku(kadro_yolu, now) is not None                             # 5 dk gelecek toleransi icinde
    _yaz(kadro_yolu, _belge(now + timedelta(minutes=6), [_oge()]))
    assert CK.oku(kadro_yolu, now) is None


def test_oku_missing_or_corrupt_file_is_none(tmp_path):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    assert CK.oku(tmp_path / "yok.json", now) is None
    bad = tmp_path / "bozuk.json"
    bad.write_text("{", encoding="utf-8")
    assert CK.oku(bad, now) is None
    wrong = tmp_path / "sema.json"
    wrong.write_text(json.dumps(_belge(now, [_oge()], sema="x")), encoding="utf-8")
    assert CK.oku(wrong, now) is None


def test_oku_maps_pairs_and_carries_fields(kadro_yolu):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    _yaz(kadro_yolu, _belge(now - timedelta(minutes=5), [_oge("kPEPE", 3, 1, "long", 250.5), _oge("dex:NVDA", 0, 4, "short", None)]))
    m = CK.oku(kadro_yolu, now)
    assert set(m) == {"_uretildi", "1000PEPE/USDT", "NVDA/USDT"}
    assert m["1000PEPE/USDT"] == {"long": 3, "short": 1, "net_yon": "long", "net_nominal_usd": 250.5, "veri_yasi_sn": 300.0}
    assert m["NVDA/USDT"]["net_nominal_usd"] is None and m["NVDA/USDT"]["short"] == 4


# ----------------------------------------------------------------------------- C1 sinyal (sentetik barlar)
def _trig() -> pd.DataFrame:
    i = pd.RangeIndex(len(BARS))
    close = pd.Series(100.0 + 0.05 * i.to_numpy(dtype=float), index=BARS)
    return pd.DataFrame({"open": close - 0.02, "high": close + 0.6, "low": close - 0.6, "close": close}, index=BARS)


def _trig_dusen() -> pd.DataFrame:
    """Dusen seri: kapanis EMA50 altinda, mumlar kirmizi (short teyidi)."""
    i = pd.RangeIndex(len(BARS))
    close = pd.Series(100.0 - 0.05 * i.to_numpy(dtype=float), index=BARS)
    return pd.DataFrame({"open": close + 0.02, "high": close + 0.6, "low": close - 0.6, "close": close}, index=BARS)


def _inp(pair="BTC/USDT", tf="1h", trig=None, core_fn=None) -> ArmInput:
    trig = _trig() if trig is None else trig
    core = C1._bos(trig.index)
    core["regime"] = "range"
    return ArmInput(pair=pair, tf=tf, D=D, trig=trig, h4=pd.DataFrame(), params=None,
                    core_fn=core_fn or (lambda: core))


def _sinyal(inp: ArmInput):
    out = C1.compute(inp)
    return out.iloc[-1]


def _atr_son(trig: pd.DataFrame) -> float:
    return float(I.atr(trig[["high", "low", "close"]], 14).iloc[-1])


def test_c1_long_candidate_levels_and_features(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 4, 1, "long", 1000.0)]))
    trig = _trig()
    r = _sinyal(_inp(trig=trig))
    assert bool(r["signal"]) and r["setup"] == "C1" and r["side"] == "long" and r["skip_reason"] is None
    entry, atr = float(trig["close"].iloc[-1]), _atr_son(trig)
    assert r["planned_entry"] == pytest.approx(entry)
    assert r["planned_stop"] == pytest.approx(entry - 1.5 * atr)           # stop 1,5 ATR
    assert r["planned_target"] == pytest.approx(entry + 2 * 1.5 * atr)     # hedef 2R
    assert r["rr"] == pytest.approx(2.0) and r["stop_dist_atr"] == pytest.approx(1.5)
    # defter ozellikleri: tasiyici sutunlar
    assert int(r["pullback_ema"]) == 4 and r["ema_value"] == pytest.approx(1.0)
    assert r["body_ratio"] == pytest.approx(0.8) and r["wick_ratio"] == pytest.approx(1000.0)
    assert r["edge_dist_atr"] == pytest.approx(600.0)                     # veri yasi (uretildi D-10 dk) saniye olarak


def test_c1_short_candidate_mirrors_levels(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("dex:NVDA", 1, 4, "short", -500.0)]))
    trig = _trig_dusen()
    r = _sinyal(_inp(pair="NVDA/USDT", trig=trig))
    entry, atr = float(trig["close"].iloc[-1]), _atr_son(trig)
    assert bool(r["signal"]) and r["side"] == "short"
    assert r["planned_stop"] == pytest.approx(entry + 1.5 * atr)
    assert r["planned_target"] == pytest.approx(entry - 2 * 1.5 * atr)


def test_c1_count_threshold_three(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 2, 0, "long", None)]))
    assert not bool(_sinyal(_inp()).signal)                                  # toplam 2 < 3
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=9), [_oge("BTC", 3, 0, "long", None)]))
    assert bool(_sinyal(_inp()).signal)                                      # toplam 3 = esik


def test_c1_dominance_threshold_070(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 7, 3, "long", None)]))
    assert bool(_sinyal(_inp()).signal)                                      # 7/10 = 0,70 esik dahil
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=9), [_oge("BTC", 13, 6, "long", None)]))
    assert not bool(_sinyal(_inp()).signal)                                  # 13/19 = 0,684 < 0,70


def test_c1_nominal_sign_must_agree_and_null_is_ok(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 4, 1, "long", -10.0)]))
    assert not bool(_sinyal(_inp()).signal)                                  # long ama nominal negatif
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=9), [_oge("BTC", 4, 1, "long", 0.0)]))
    assert not bool(_sinyal(_inp()).signal)                                  # long icin > 0 sarti (sifir red)
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=8), [_oge("BTC", 4, 1, "long", None)]))
    assert bool(_sinyal(_inp()).signal)                                      # null: isaret denetlenmez
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=7), [_oge("BTC", 1, 4, "short", 10.0)]))
    assert not bool(_sinyal(_inp()).signal)                                  # short ama nominal pozitif


def test_c1_net_yon_must_match_dominant_side(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 1, 6, "long", None)]))
    assert not bool(_sinyal(_inp()).signal)                                  # baskin short, net long
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=9), [_oge("BTC", 4, 1, "notr", None)]))
    assert not bool(_sinyal(_inp()).signal)                                  # notr: aday yok


def test_c1_one_candidate_per_uretildi(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 4, 1, "long", None)]))
    assert bool(_sinyal(_inp()).signal)
    assert not bool(_sinyal(_inp()).signal)                                  # ayni uretildi: ikinci aday yok
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=5), [_oge("BTC", 4, 1, "long", None)]))
    assert bool(_sinyal(_inp()).signal)                                      # yeni uretildi: yeniden aday


def test_c1_no_file_or_stale_file_no_candidates_and_no_core_call(kadro_yolu):
    def boom():
        raise AssertionError("aday yokken ortak tablo hesaplanmamali")
    assert not bool(_sinyal(_inp(core_fn=boom)).signal)                      # dosya yok
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=50), [_oge("BTC", 4, 1, "long", None)]))
    assert not bool(_sinyal(_inp(core_fn=boom)).signal)                      # bayat (45 dk)


def test_c1_pair_not_in_file_no_candidate(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 4, 1, "long", None)]))
    assert not bool(_sinyal(_inp(pair="ETH/USDT")).signal)


def _teyit_trig(ema_tarafi: str, mum: str) -> pd.DataFrame:
    """Yukselen seri; son bar kapanisi EMA50'nin ustunde/altinda, mum yesil/kirmizi olacak sekilde ayarlanir."""
    t = _trig()
    ema = float(I.ema(t["close"], 50).iloc[-1])
    c = ema + 1.0 if ema_tarafi == "ust" else ema - 1.0
    o = c - 0.3 if mum == "yesil" else c + 0.3
    t.iloc[-1, t.columns.get_loc("close")] = c
    t.iloc[-1, t.columns.get_loc("open")] = o
    t.iloc[-1, t.columns.get_loc("high")] = max(c, o) + 0.6
    t.iloc[-1, t.columns.get_loc("low")] = min(c, o) - 0.6
    return t


@pytest.mark.parametrize("ema_tarafi,mum,beklenen", [("ust", "yesil", True), ("alt", "yesil", False),
                                                      ("ust", "kirmizi", False), ("alt", "kirmizi", False)])
def test_c1_long_requires_price_action_confirmation(kadro_yolu, ema_tarafi, mum, beklenen):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 4, 1, "long", None)]))
    assert bool(_sinyal(_inp(trig=_teyit_trig(ema_tarafi, mum))).signal) is beklenen


def test_c1_short_requires_price_action_confirmation(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 1, 4, "short", None)]))
    assert not bool(_sinyal(_inp(trig=_trig())).signal)                      # yukselen seri: short teyidi yok
    t = _trig_dusen()
    assert bool(_sinyal(_inp(trig=t)).signal)                                # dusen seri: teyit var
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=9), [_oge("BTC", 1, 4, "short", None)]))
    t.iloc[-1, t.columns.get_loc("open")] = float(t["close"].iloc[-1]) - 0.3  # yesil mum: short teyidi bozulur
    assert not bool(_sinyal(_inp(trig=t)).signal)


def test_c1_unconfirmed_bar_does_not_consume_the_ct_file(kadro_yolu):
    _yaz(kadro_yolu, _belge(D - timedelta(minutes=10), [_oge("BTC", 4, 1, "long", None)]))
    assert not bool(_sinyal(_inp(trig=_teyit_trig("alt", "yesil"))).signal)   # teyitsiz: aday yok, dosya tuketilmez
    assert bool(_sinyal(_inp(trig=_trig())).signal)                          # ayni dosya, teyitli bar: aday


def test_c1_contract_fields():
    mod = AR.find_arm("C1")
    assert mod.SETUP == "C1" and tuple(mod.TIMEFRAMES) == ("1h", "4h") and mod.CORE is False and mod.ML_SCORED is False
    assert mod.EXIT_MODE == "target" and mod.PRIORITY == 80
    assert len(mod.FEATURES) == 6 and set(mod.FEATURES.values()) <= set(AR.CARRIERS)
    assert AR.features_of("C1") == mod.FEATURES
    AR.validate_arm(mod, "c1")


# ----------------------------------------------------------------------------- saglik uyarisi
def test_health_ct_alert_fresh_stale_missing(tmp_path):
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    var = tmp_path / "ct"
    assert HR.ct_kadro_alerts({}, now, var_dir=str(var)) == []                  # durum.json hic yok: birim calismadi, uyari yok
    var.mkdir()
    (var / "durum.json").write_text("{bozuk", encoding="utf-8")
    assert HR.ct_kadro_alerts({}, now, var_dir=str(var))[0].code == "ct_kadro_bayat"   # bozuk durum: uyari
    (var / "durum.json").write_text(json.dumps({"son_basari": "2026-11-19T11:30:00Z"}), encoding="utf-8")
    assert HR.ct_kadro_alerts({}, now, var_dir=str(var)) == []                  # 30 dk: taze
    (var / "durum.json").write_text(json.dumps({"son_basari": "2026-11-19T11:00:00Z"}), encoding="utf-8")
    al = HR.ct_kadro_alerts({}, now, var_dir=str(var))
    assert len(al) == 1 and al[0].code == "ct_kadro_bayat" and al[0].level == HR.H.Status.WARN
    (var / "durum.json").write_text(json.dumps({"son_basari": None}), encoding="utf-8")
    assert HR.ct_kadro_alerts({}, now, var_dir=str(var))[0].code == "ct_kadro_bayat"
