"""C1 CT kadro: src/trader_core/ct_kadro.py icin belirtime dayali testler.

Kaynak: docs/motor/c1-ct-kadro-spec.md, bolum 2 (okuma ve eslemesi).
Bu testler uygulamaya bakilmadan yazilmistir; yalnizca belirtimdeki
sozlesmeyi dogrular.

Kapsam disi (belirtimde fonksiyon adi yok): scripts/ct_kadro_cek.py
dogrulama/atomik yazim testleri. Bunlar atlandi.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from trader_core.ct_kadro import hl_to_binance, oku

NOW = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
SEMA = "ct.kadro_yon.v1"
EVREN = {"BTC/USDT", "ETH/USDT", "1000PEPE/USDT", "1000SHIB/USDT", "NVDA/USDT"}


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload(uretildi: datetime = NOW, **over) -> dict:
    data = {
        "sema": SEMA,
        "uretildi_utc": _iso_z(uretildi),
        "coinler": [
            {
                "coin": "BTC",
                "long_trader": 5,
                "short_trader": 1,
                "net_yon": "long",
                "net_nominal_usd": 1000.0,
            }
        ],
    }
    data.update(over)
    return data


def _write(tmp_path, data, name="kadro_yon.json") -> str:
    path = tmp_path / name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------- oku: hatali girdi


def test_oku_missing_file_returns_none(tmp_path):
    assert oku(str(tmp_path / "yok.json"), NOW) is None


def test_oku_corrupt_json_returns_none(tmp_path):
    path = _write(tmp_path, "{bu json degil")
    assert oku(path, NOW) is None


def test_oku_wrong_schema_returns_none(tmp_path):
    path = _write(tmp_path, _payload(sema="ct.kadro_yon.v0"))
    assert oku(path, NOW) is None


def test_oku_missing_schema_returns_none(tmp_path):
    data = _payload()
    del data["sema"]
    path = _write(tmp_path, data)
    assert oku(path, NOW) is None


def test_oku_malformed_timestamp_returns_none(tmp_path):
    # uretildi_utc ISO-8601 Z olmali; bozuk deger bozuk dosya sayilir.
    path = _write(tmp_path, _payload(uretildi_utc="bu bir tarih degil"))
    assert oku(path, NOW) is None


# ---------------------------------------------------------------- oku: yas sinirlari


def test_oku_age_exactly_45_min_is_ok(tmp_path):
    path = _write(tmp_path, _payload(uretildi=NOW - timedelta(minutes=45)))
    assert oku(path, NOW) is not None


def test_oku_age_45_min_plus_1s_returns_none(tmp_path):
    path = _write(tmp_path, _payload(uretildi=NOW - timedelta(minutes=45, seconds=1)))
    assert oku(path, NOW) is None


def test_oku_azami_yas_dk_keyword_is_respected(tmp_path):
    path = _write(tmp_path, _payload(uretildi=NOW - timedelta(minutes=11)))
    assert oku(path, NOW, azami_yas_dk=10) is None
    path2 = _write(tmp_path, _payload(uretildi=NOW - timedelta(minutes=9)), name="k2.json")
    assert oku(path2, NOW, azami_yas_dk=10) is not None


def test_oku_future_exactly_5_min_is_ok(tmp_path):
    path = _write(tmp_path, _payload(uretildi=NOW + timedelta(minutes=5)))
    assert oku(path, NOW) is not None


def test_oku_future_5_min_plus_1s_returns_none(tmp_path):
    path = _write(tmp_path, _payload(uretildi=NOW + timedelta(minutes=5, seconds=1)))
    assert oku(path, NOW) is None


# ---------------------------------------------------------------- oku: basarili okuma


def test_oku_fresh_payload_returns_mapping_with_uretildi(tmp_path):
    path = _write(tmp_path, _payload(uretildi=NOW - timedelta(minutes=2)))
    result = oku(path, NOW)
    assert result is not None
    assert "_uretildi" in result
    # Belirtim: {cift: kayit} sozlugu; BTC icin cift BTC/USDT.
    assert "BTC/USDT" in result


def test_oku_record_fields_and_values(tmp_path):
    path = _write(tmp_path, _payload(uretildi=NOW - timedelta(minutes=2)))
    rec = oku(path, NOW)["BTC/USDT"]
    assert set(rec.keys()) == {"long", "short", "net_yon", "net_nominal_usd", "veri_yasi_sn"}
    assert rec["long"] == 5
    assert rec["short"] == 1
    assert rec["net_yon"] == "long"
    assert rec["net_nominal_usd"] == pytest.approx(1000.0)


def test_oku_veri_yasi_sn_is_age_in_seconds(tmp_path):
    path = _write(tmp_path, _payload(uretildi=NOW - timedelta(seconds=60)))
    rec = oku(path, NOW)["BTC/USDT"]
    assert rec["veri_yasi_sn"] == pytest.approx(60.0)


def test_oku_net_nominal_usd_null_is_allowed(tmp_path):
    coin = {
        "coin": "BTC",
        "long_trader": 3,
        "short_trader": 0,
        "net_yon": "notr",
        "net_nominal_usd": None,
    }
    path = _write(tmp_path, _payload(coinler=[coin]))
    rec = oku(path, NOW)["BTC/USDT"]
    assert rec["net_nominal_usd"] is None
    assert rec["net_yon"] == "notr"


# ---------------------------------------------------------------- hl_to_binance


def test_hl_btc_maps_to_usdt_pair():
    assert hl_to_binance("BTC", EVREN) == "BTC/USDT"


def test_hl_kpepe_maps_to_1000_prefix():
    assert hl_to_binance("kPEPE", EVREN) == "1000PEPE/USDT"


def test_hl_kshib_maps_to_1000_prefix():
    assert hl_to_binance("kSHIB", EVREN) == "1000SHIB/USDT"


def test_hl_dex_prefix_is_stripped():
    assert hl_to_binance("xyz:NVDA", EVREN) == "NVDA/USDT"


def test_hl_coin_not_in_universe_returns_none():
    assert hl_to_binance("FOO", EVREN) is None


def test_hl_dex_coin_not_in_universe_returns_none():
    assert hl_to_binance("xyz:FOO", EVREN) is None


def test_hl_k_prefix_not_in_universe_returns_none():
    # kFOO -> 1000FOO/USDT, evrende yok.
    assert hl_to_binance("kFOO", EVREN) is None


def test_hl_lowercase_k_followed_by_lowercase_does_not_trigger_1000_rule():
    # Belirtim: 1000 kurali yalnizca kucuk k + buyuk harf icin.
    # Ciktinin tam bicimi belirsiz; yalnizca 1000 onekinin uygulanmadigi dogrulanir.
    evren = {"KAS/USDT", "1000AS/USDT"}
    assert hl_to_binance("kas", evren) != "1000AS/USDT"
