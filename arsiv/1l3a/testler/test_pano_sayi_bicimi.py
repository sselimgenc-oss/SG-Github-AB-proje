"""Pano sayı biçimi: Türkçe (binlik nokta, ondalık virgül, eksi '−', yüzde önde) ve Telegram ile aynı; makine biçimi (data-*) bozulmaz."""
import re

from motor.canli import pano
from motor.canli import telegram as tg
from testler.test_pano_olcum_kartlari import ornek_kur, _html


def _gorunen(h: str) -> str:
    h = re.sub(r"<style.*?</style>|<script.*?</script>", "", h, flags=re.S)
    return " ".join(re.findall(r">([^<>]+)<", h)) + " " + " ".join(re.findall(r'title="([^"]*)"', h))


def test_bicimleyiciler_telegram_ile_ayni():
    assert pano._usd("10250.55") == tg.usd("10250.55") == "10.250,55 $"
    assert pano._usd("250.55", True) == tg.usd("250.55", True) == "+250,55 $"
    assert pano._usd("-12.40", True) == tg.usd("-12.40", True) == "−12,40 $"
    assert pano.f_yuzde(0.0251) == "%2,51" and pano.f_yuzde(0.0251, True) == "+%2,51" and pano.f_yuzde(-0.0012, True) == "−%0,12"
    assert pano.f_yuzde(0.0251, True) == tg.yuzde(0.0251, True) and pano.f_yuzde(-0.0012, True) == tg.yuzde(-0.0012, True)
    assert pano.f_para("-1234.5", True) == "−1.234,50" and pano.f_para("10250.55") == "10.250,55" and pano.f_sayi(1.5) == "1,50"
    assert pano._fiyat("152.3") == "152,30" and pano._fiyat("0.00123") == "0,00123"


def test_pano_ornek_veride_turkce_bicim(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch))
    m = _gorunen(h)
    assert "10.250,55" in m and "+250,55 $" in m and "−12,34 $" in m and "%2,51" in m
    assert not re.search(r"\d,\d{3}\.\d{2}", m)                       # "10,250.55" gibi İngilizce biçim yok
    assert not re.search(r"\d\.\d{2}\s?%|[+-]\d+\.\d+ \$", m)         # "2.51%", "+1.50 $" yok
    assert "-" not in re.findall(r"[+\-−]\d[\d.,]* \$", m).__str__().replace("−", "")   # eksi işareti yalnız '−'
    assert re.search(r'data-net="-?\d+(\.\d+)?"', h) or "data-net" not in h   # makine biçimi (JS okur) bozulmadı


def test_alarm_veya_karantinada_risk_kutusu_yesil_degil(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch))
    assert 'data-risk="dikkat"' in h and "Güvenli" not in h[h.index('data-risk='):h.index("</div></div>", h.index('data-risk='))]
