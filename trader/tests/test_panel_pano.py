"""Yeni pano: sade Turkce veri katmani, risk durumu, TSI gunu, bos kart gizleme, kol adi, yasak metin taramasi."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from panel_support import NOW, ROOT, Env, status_doc
from trader_core import panel_data as P
from trader_core import panel_pano as PP
from trader_core import tg_sade as TS
from trader_panel.data import PanelData, load_config

STATIC = ROOT / "src/trader_panel/static"
UTC = timezone.utc


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    e = Env(tmp_path_factory.mktemp("pano"))
    yield e
    e.close()


@pytest.fixture(scope="module")
def pano(env):
    return PanelData(load_config(env.cfg_path), clock=lambda: NOW).pano("learner")


def walk_strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from walk_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_strings(v)


def test_limit_equals_single_source_not_hardcoded_5pct(pano):
    r = pano["serit"]["risk"]
    assert r["limit_orani"] == P.daily_loss_rate("paper")
    assert r["limit"] == pytest.approx(P.daily_loss_rate("paper") * 1000.0)       # day_start_equity fikstur = 1000
    assert r["limit"] != pytest.approx(0.05 * 1000.0) or P.daily_loss_rate("paper") == 0.05
    src = (ROOT / "src/trader_core/panel_pano.py").read_text(encoding="utf-8")
    assert "0.05" not in src and "* 0.05" not in src


def test_risk_status_levels():
    live = {"mode": "paper", "day_start_equity": 1000.0, "entries_open": True}
    lim = P.daily_loss_rate("paper") * 1000.0
    g = PP.risk_durumu(live, "live", False, 0.0)
    assert g["renk"] == "yesil" and g["metin"] == "Güvenli" and "günlük limite kalan" in g["alt"]
    y = PP.risk_durumu(live, "live", False, -0.7 * lim)
    assert y["renk"] == "sari" and y["metin"] == "Limite yakın"
    assert PP.risk_durumu(live, "live", False, -0.69 * lim)["renk"] == "yesil"
    k = PP.risk_durumu({**live, "entries_open": False, "entries_blocked_reason": "stale_data"}, "live", False, 0.0)
    assert k["renk"] == "kirmizi" and k["metin"] == "Durdu: piyasa verisi eski"
    d = PP.risk_durumu(live, "live", False, -lim)
    assert d["renk"] == "kirmizi" and "limiti doldu" in d["metin"]
    assert PP.risk_durumu(live, "stale", False, 0.0)["renk"] == "kirmizi"
    assert PP.risk_durumu(live, "live", True, 0.0)["metin"] == "Durdu: acil durdurma"
    unk = PP.risk_durumu({**live, "entries_open": False, "entries_blocked_reason": "yeni_bilinmeyen_kod"}, "live", False, 0.0)
    assert "_" not in unk["metin"] and "bilinmeyen" not in unk["metin"]


def test_no_raw_codes_files_sha_utc_in_data_layer(pano, env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    texts = list(walk_strings(pano)) + list(walk_strings(d.kapanan("learner", "tumu")))
    bad = re.compile(r"\.(py|json|sqlite)\b|sha256|UTC|\bT\d\d:\d\d|\d{4}-\d{2}-\d{2}|gate_code|entries_blocked|[a-z]+_[a-z]+")
    for t in texts:
        if t in ("learner", "bot_durum") or re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:.]+Z", t):
            continue
        assert not bad.search(t), t


def test_kol_adi_used_like_telegram(env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    rows = d.kapanan("learner", "tumu")["rows"]
    assert rows and all(r["kol"] == TS.kol_adi("R1@1h") == "Yatay piyasa kenarı · 1 saat" for r in rows)
    assert all(r["coin"] in ("ETH", "BTC") and r["yon"] == "long" for r in rows)
    assert d.pano("learner")["acik"]["rows"][0]["kol"] == "Yatay piyasa kenarı · 1 saat"


def test_tsi_day_boundary(env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    # 2026-11-15 21:30 UTC = 16.11 00:30 TSI => 16.11 gunune dahil, 15.11'e degil; 20:59 UTC = 15.11 23:59 TSI
    a, b = PP.period_bounds("bugun", datetime(2026, 11, 16, 18, 0, tzinfo=UTC))
    assert a == datetime(2026, 11, 15, 21, 0, tzinfo=UTC) and b == datetime(2026, 11, 16, 21, 0, tzinfo=UTC)
    a2, _ = PP.period_bounds("bugun", datetime(2026, 11, 16, 20, 59, tzinfo=UTC))
    assert a2 == datetime(2026, 11, 15, 21, 0, tzinfo=UTC)
    a3, _ = PP.period_bounds("bugun", datetime(2026, 11, 16, 21, 0, tzinfo=UTC))      # 17.11 00:00 TSI: yeni gun
    assert a3 == datetime(2026, 11, 16, 21, 0, tzinfo=UTC)
    assert PP.tsi_kisa(datetime(2026, 11, 15, 21, 30, tzinfo=UTC)) == "16.11 00:30"
    assert d.kapanan("learner", "bugun")["n"] == 2          # 16.11 (TSI) kapanislari: fikstur 2 adet
    assert d.kapanan("learner", "tumu")["n"] == 5


def test_empty_cards_hidden_and_unmeasured_text(pano):
    assert pano["ders"] is None and pano["ml"] is None            # fikstur: ders/ML verisi yok -> kart uretilmez
    z = pano["kz"]
    assert z["oran"]["kazanma_yuzde"] == 60.0                    # 5 islem >= asgari
    o = PP.olculemedi(8, 30)
    assert o == {"olculemedi": "Henüz ölçülemedi (8 işlem, en az 30 gerek)"}


def test_unmeasured_win_rate_when_few_trades(tmp_path):
    from panel_support import mkledger, STD_LEARNER
    p = tmp_path / "l.sqlite"
    mkledger(p, "learner", STD_LEARNER[:2])
    ctx = PP.Ctx(str(p))
    kz = PP.kz_view(ctx, 1000.0, NOW, None, [])
    assert kz["oran"] == {"olculemedi": "Henüz ölçülemedi (2 işlem, en az 5 gerek)"}
    assert kz["egri"] is None


def test_invalid_period_rejected(env):
    d = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    assert d.kapanan("learner", "yil")["ok"] is False


# ---------------- panel.js / html yasak metin taramasi
def _js_code():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)                  # yorumlar goruntulenmez
    return re.sub(r"(?m)(?<![:'\"])//.*$", "", js)


def test_panel_js_free_of_forbidden_text():
    js = _js_code() + (STATIC / "index.html").read_text(encoding="utf-8")
    for bad in ("gate_code", "entries_blocked_reason", "sha256", "commit", "UTC", "/onayla", "kill dosyası", "journalctl",
                "param_version_id", ".sqlite", "panel.py"):
        assert bad not in js, bad
    assert not re.search(r"\b5\s*%|0\.05\b", js)
    assert "Salt okunur panel" not in js
    assert not re.search(r"['\"][\w/-]+\.(json|py|sqlite)['\"]", js)


def test_panel_js_new_structure():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    for t in ("ÖZET", "AÇIK", "KAPANAN", "K/Z", "ÖĞRENME", "TEKNİK", "Risk durumu", "Zirveden düşüş", "Toplam K/Z", "Bugün K/Z",
              "window.self !== window.top", "data-theme", "YENILE_S = 300", "son güncelleme"):
        assert t in js, t
    assert "TAB_MS" not in js and "setInterval" in js and "location.reload" in js
    css = (STATIC / "panel.css").read_text(encoding="utf-8")
    assert "repeat(3,minmax(0,1fr))" in css and "repeat(6,minmax(0,1fr))" in css and ".gomulu .ust{display:none}" in css


# ---------------- Turkce bicim, ek yardimcisi, ders/ML durumlari
def _node_js(code: str) -> str:
    import shutil
    import subprocess
    if shutil.which("node") is None:
        pytest.skip("node yok")
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_turkish_suffix_helper_and_number_format():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    fn = js.split("/* ek:basla")[1].split("*/", 1)[1].split("/* ek:bitir */")[0]
    trn = re.search(r"  function trn\(x, d\) \{.*?\n  \}\n", js, re.S).group(0)
    want = {1: "i", 2: "si", 3: "ü", 4: "ü", 5: "i", 6: "sı", 7: "si", 8: "i", 9: "u", 10: "u", 20: "si", 30: "u", 40: "ı", 50: "si",
            60: "ı", 70: "i", 80: "i", 90: "ı", 100: "ü", 1000: "i"}
    out = _node_js(trn + fn + f"for (const n of {list(want)}) console.log(n + ek(n)); console.log(trn(1428.4)); console.log(trn(-7.2)); console.log(trn(0.5, 1));")
    lines = out.split("\n")
    for line, (n, e) in zip(lines, want.items()):
        assert line == f"{n}'{e}", line
    assert lines[len(want):len(want) + 3] == ["1.428,40", "7,20", "0,5"]


def test_server_number_format_turkish():
    assert PP.tr_sayi(1428.4) == "1.428,40" and PP.tr_sayi(-7.2) == "7,20" and PP.tr_sayi(1000000) == "1.000.000,00"


def test_param_sentence_has_unit_and_turkish_decimal():
    s = PP._param_farki({"stop_buffer_atr": 0.3}, {"stop_buffer_atr": 0.2})
    assert s == "stop payı 0,3 → 0,2 ATR"


def test_strip_has_start_not_kasa_pct_and_title_turkish(pano):
    assert pano["serit"]["baslangic"] == 1000.0 and "kasa_yuzde" not in pano["serit"]
    assert "<h1>İşlem Botu</h1>" in (STATIC / "index.html").read_text(encoding="utf-8")


def test_partial_state_is_not_healthy_and_says_why():
    ml = {"kapsam": {"aktif": 4, "toplam": 9, "en_az": 10, "eksik": []}}
    k = PP.kismi_durum({"renk": "sari"}, ml)
    assert k == ["ML 4/9 kolda çalışıyor, diğerlerinde yeterli işlem yok (en az 10)"]
    y = PP.ne_yapmali("live", {"renk": "yesil"}, 3, k)
    assert y.startswith("Bir şey yapmanız gerekmiyor; ML 4/9 kolda")
    assert PP.kismi_durum({"renk": "kirmizi"}, None) == ["ders işlemleri etkilemiyor"]
    assert PP.kismi_durum({"renk": "yesil"}, {"kapsam": {"aktif": 9, "toplam": 9, "en_az": 10, "eksik": []}}) == []


def test_katki_label_uses_resolved_count():
    assert PP.katki_olculemedi(0) == {"olculemedi": "Henüz ölçülemedi (sonucu belli 0 karar, en az 10)"}


def test_ml_denominator_is_paper_config_arms_and_threshold_from_engine():
    from trader_engine import ogrenme_filtre as OF
    assert PP.min_kol_islem() == OF.MIN_ISLEM
    arms = P.paper_maps()[0]
    assert len(arms) >= 9                                         # payda: kagit ayarindaki gercek kol listesi
    src = (ROOT / "src/trader_core/panel_pano.py").read_text(encoding="utf-8")
    assert "paper_maps()[0]" in src and "trader_engine" not in src.replace("ogrenme_filtre.MIN_ISLEM", "")      # core motoru ice aktarmaz; sabit esitligi yukarida
