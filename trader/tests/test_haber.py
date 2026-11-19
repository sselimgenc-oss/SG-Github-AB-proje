"""Haber/duygu etiketi (src/trader_core/haber.py, scripts/haber_run.py): yalniz kayit; sentetik veri, ag yok (getirici enjekte), her hata sessiz."""
from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

from trader_core import haber

ROOT = Path(__file__).resolve().parent.parent
SIMDI = int(datetime(2026, 11, 19, 12, 0, tzinfo=UTC).timestamp() * 1000)
SAAT_ONCE = "Thu, 19 Nov 2026 10:00:00 +0000"
ESKI = "Tue, 17 Nov 2026 10:00:00 +0000"
FNG = {"data": [{"value": "25", "value_classification": "Extreme Fear", "timestamp": "1"}]}


def _rss(*ogeler: tuple[str, str]) -> bytes:
    govde = "".join(f"<item><title>{b}</title><pubDate>{t}</pubDate></item>" for b, t in ogeler)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{govde}</channel></rss>'.encode()


RSS = _rss(("Bitcoin surges to record high", SAAT_ONCE), ("SOL jumps as Solana adoption grows", SAAT_ONCE),
           ("Exchange hack drains ETH", SAAT_ONCE), ("Solid quarter for banks", SAAT_ONCE), ("Old bitcoin story", ESKI))


def _yukle_betik():
    spec = importlib.util.spec_from_file_location("haber_run_t", ROOT / "scripts" / "haber_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_gecerli_okuma_ve_tekillestirme():
    anlik = haber.guncelle({}, SIMDI, lambda u: FNG, lambda u: RSS)
    assert anlik["duygu"] == {"deger": 25, "sinif": "Extreme Fear", "ms": SIMDI}
    assert len(anlik["haberler"]) == 4                       # iki kaynakta aynı başlıklar tekilleşir; 2 günlük başlık atılır
    assert anlik["haber_ms"] == SIMDI


def test_coin_eslesme_tam_kelime_ve_isim():
    anlik = haber.guncelle({}, SIMDI, lambda u: FNG, lambda u: RSS)
    assert haber.coin_haber(anlik, "BTC", SIMDI) == {"BTC": {"adet_24s": 1, "ton": "pozitif"}}
    assert haber.coin_haber(anlik, "SOL", SIMDI) == {"SOL": {"adet_24s": 1, "ton": "pozitif"}}
    assert haber.coin_haber(anlik, "ETH", SIMDI) == {"ETH": {"adet_24s": 1, "ton": "negatif"}}
    assert haber.coin_haber(anlik, "DOGE", SIMDI) == {"DOGE": {"adet_24s": 0, "ton": None}}
    assert not haber.eslesir("Solid quarter", "SOL") and not haber.eslesir("Resolve it", "SOL")
    assert haber.eslesir("kPEPE rallies, PEPE up", "kPEPE")
    assert haber.coin_haber(anlik, "BTC", SIMDI + 30 * 3600_000) is None        # haber onbellegi bayat -> null


def test_pencere_24_saat_ve_ileri_tarih():
    anlik = {"haberler": [{"t": SIMDI - 25 * 3600_000, "b": "Bitcoin old", "ton": "notr"},
                          {"t": SIMDI + 10 * 3600_000, "b": "Bitcoin future", "ton": "notr"},
                          {"t": SIMDI - 23 * 3600_000, "b": "Bitcoin ok", "ton": "notr"}], "haber_ms": SIMDI}
    assert haber.coin_haber(anlik, "BTC", SIMDI) == {"BTC": {"adet_24s": 1, "ton": "notr"}}
    assert haber.coin_haber({"haberler": [], "haber_ms": SIMDI + 5 * 3600_000}, "BTC", SIMDI) is None     # ileri tarihli onbellek


def test_ton_kaba_anahtar_kelime():
    assert haber.ton("Prices surge") == "pozitif" and haber.ton("Exchange hack") == "negatif" and haber.ton("Fed meets") == "notr"
    anlik = {"haberler": [{"t": SIMDI, "b": "Bitcoin surges", "ton": "pozitif"}, {"t": SIMDI, "b": "Bitcoin crash", "ton": "negatif"}],
             "haber_ms": SIMDI}
    assert haber.coin_haber(anlik, "BTC", SIMDI) == {"BTC": {"adet_24s": 2, "ton": "notr"}}       # eşit -> notr


def test_duygu_ozet_26_saat():
    a = {"duygu": {"deger": 25, "sinif": "Fear", "ms": SIMDI}}
    assert haber.duygu_ozet(a, SIMDI + 25 * 3600_000) == {"deger": 25, "sinif": "Fear"}
    assert haber.duygu_ozet(a, SIMDI + 27 * 3600_000) is None
    assert haber.duygu_ozet({}, SIMDI) is None and haber.duygu_ozet(None, SIMDI) is None
    assert haber.duygu_ozet({"duygu": {"deger": 250, "sinif": "x", "ms": SIMDI}}, SIMDI) is None
    assert haber.duygu_coz({"data": [{"value": "101", "value_classification": "x"}]}) is None
    assert haber.duygu_coz({"bozuk": 1}) is None and haber.duygu_coz(None) is None


def test_bozuk_xml_ve_dtd_bos_doner():
    assert haber.rss_coz(b"<rss><item>", SIMDI) == [] and haber.rss_coz("", SIMDI) == [] and haber.rss_coz(None, SIMDI) == []
    assert haber.rss_coz(b'<!DOCTYPE x [<!ENTITY a "b">]><rss><channel><item><title>a</title><pubDate>' + SAAT_ONCE.encode() + b"</pubDate></item></channel></rss>", SIMDI) == []
    assert haber.rss_coz(_rss(("tarihsiz", "bozuk tarih")), SIMDI) == []


def test_kaynak_hatasi_onbellegi_korur():
    ilk = haber.guncelle({}, SIMDI, lambda u: FNG, lambda u: RSS)

    def patla(u):
        raise TimeoutError("x")

    ikinci = haber.guncelle(ilk, SIMDI + 3600_000, patla, patla)
    assert ikinci == ilk
    ucuncu = haber.guncelle(ilk, SIMDI + 3600_000, lambda u: {"bozuk": 1}, lambda u: b"<bozuk")
    assert ucuncu == ilk


def test_belge_gidis_donus_ve_bozuk_belge(tmp_path):
    anlik = haber.guncelle({}, SIMDI, lambda u: FNG, lambda u: RSS)
    doc = haber.belge_yap(anlik, SIMDI)
    assert doc["sema"] == "ml.haber.v1" and doc["uretim"] == "2026-11-19T12:00:00Z"
    assert haber.belge_coz(doc) == anlik
    assert haber.belge_coz({**doc, "sema": "x"}) is None and haber.belge_coz([]) is None and haber.belge_coz({**doc, "basliklar": "x"}) is None
    assert haber.belge_coz({**doc, "basliklar": [{"t": 1, "b": "x", "ton": "yok"}]}) is None
    p = tmp_path / "haber_v1.json"
    p.write_text("{bozuk", encoding="utf-8")
    assert haber.dosya_oku(p) is None and haber.dosya_oku(tmp_path / "yok.json") is None


def test_etiket_onbellek_yok_bozuk_bayat_null(tmp_path):
    p = tmp_path / "haber_v1.json"
    assert haber.etiket("BTC/USDT", SIMDI, p) is None                                   # yok
    p.write_text("{bozuk", encoding="utf-8")
    assert haber.etiket("BTC/USDT", SIMDI, p) is None                                   # bozuk
    anlik = haber.guncelle({}, SIMDI, lambda u: FNG, lambda u: RSS)
    p.write_text(json.dumps(haber.belge_yap(anlik, SIMDI)), encoding="utf-8")
    e = haber.etiket("BTC/USDT", SIMDI, p)                                              # baz varlık BTC
    assert e == {"duygu": {"deger": 25, "sinif": "Extreme Fear"}, "haber": {"BTC": {"adet_24s": 1, "ton": "pozitif"}}}
    assert haber.etiket("BTC/USDT", SIMDI + 7 * 3600_000, p)["haber"] is None            # haber 6 saatten eski; duygu hala taze
    assert haber.etiket("BTC/USDT", SIMDI + 27 * 3600_000, p) is None                   # ikisi de bayat
    assert haber.etiket("BTC/USDT", SIMDI - 5 * 3600_000, p) is None                    # ileri tarihli onbellek (geri test)


def test_betik_atomik_yazar_ve_hatada_dokunmaz(tmp_path):
    m = _yukle_betik()
    p = tmp_path / "durum" / "haber_v1.json"
    assert m.kos(p, SIMDI, lambda u: FNG, lambda u: RSS) == 0
    ilk = p.read_bytes()
    assert haber.dosya_oku(p)["duygu"]["deger"] == 25 and not list(p.parent.glob("*.tmp*"))

    def patla(u):
        raise OSError("ag yok")

    assert m.kos(p, SIMDI + 3600_000, patla, patla) == 0
    assert p.read_bytes() == ilk                                                        # hiçbir kaynak yok: dosya aynı
    p2 = tmp_path / "yok" / "haber_v1.json"
    assert m.kos(p2, SIMDI, patla, patla) == 0 and not p2.exists()
