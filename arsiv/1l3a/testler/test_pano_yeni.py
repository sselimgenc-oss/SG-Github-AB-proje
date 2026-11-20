"""Yeni pano yapısı (6 sekme): ÖZET · AÇIK · KAPANAN · K/Z · ÖĞRENME · TEKNİK. Şerit, risk durumu, "Ne yapmalıyım?", uyarı katlama, otomatik yenileme,
iframe, dosya/alan adı yok, gizli ad yok, ders / makine öğrenmesi kartları, 390 px'te yatay kaydırma yok."""
import copy
import html
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from motor.canli import durum as d
from motor.canli import hesap_adlari as ha
from motor.canli import pano
from motor.risk.limitler import SERT_LIMITLER
from testler.test_pano import genis_durum
from testler.test_pano_olcum_kartlari import GIZLI_PARCA, _yaz, ornek_kur

SIMDI = datetime(2026, 1, 5, 12, 10, tzinfo=timezone.utc)


def _html(durum, simdi=SIMDI) -> str:
    veri, sorun = pano.yukle(durum)
    return pano.html_olustur(veri, sorun, simdi)


def _metin(h: str) -> str:
    """Görünen metin: script/style ve etiketler çıkarılır."""
    g = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h.split("<body>")[-1], flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", g))


def _bolum(h: str, n: int) -> str:
    return h.split(f'<section class="n{n}">')[1].split("</section>")[0]


def _risk_durum(tmp_path, gunluk=0.01, kill=False, limit_tetik=False):
    p = genis_durum()
    r = p["ozet"]["risk"]
    r["gunluk_kayip"].update({"deger": gunluk, "tetiklendi": limit_tetik})
    r["kill_switch"]["tetiklendi"] = kill
    for x in p["stratejiler"]["stratejiler"] + [p["stratejiler"]["set"]]:                    # alarm yok: sağlıklı durum
        for b in x["beklenti"].values():
            for m in ("net_getiri", "max_dusus"):
                b[m]["alarm"] = False
    d.yaz_hepsi(tmp_path, **p, yazildi=d.zaman_oku("2026-01-05T12:05:00Z"))
    return p


# ------------------------------------------------------------------------------------------------------------ sekmeler ve şerit
def test_sekme_sirasi_ve_adlari(tmp_path):
    h = _html(ornek_kur(tmp_path, pytest.MonkeyPatch()))
    etiketler = re.findall(r'<label for="t\d">([^<]+?)(?: <em|</label>)', h)
    assert [e.strip() for e in etiketler] == ["ÖZET", "AÇIK", "KAPANAN", "K/Z", "ÖĞRENME", "TEKNİK"]
    assert h.count('<section class="n') == 6


def test_serit_alti_kutu_dolar_buyuk_yuzde_alt(tmp_path):
    p = _risk_durum(tmp_path)
    h = _html(tmp_path)
    serit = h[h.index('class="izgara serit"'):h.index('class="sekme-kok"')]
    o = p["ozet"]
    etiket = re.findall(r'class="e">([^<]+)<', serit)
    assert etiket == ["Kasa", "Bugün K/Z", "Toplam K/Z", "Açık poz.", "Zirveden düşüş", "Risk durumu"]
    for b in (pano.f_para(o["ozsermaye"]) + " $", pano.f_para(o["gun_pnl"], True) + " $", pano.f_yuzde(o["gun_getiri"], True), pano.f_yuzde(o["toplam_getiri"], True),
              pano.f_yuzde(o["zirveden_dusus"])):
        assert b in serit, b
    assert "Bu hafta" not in serit and h.index('class="izgara serit"') < h.index('class="tabs"')       # sekmeye bağlı değil
    assert "max-width:600px" in h and "repeat(3,minmax(0,1fr))" in h                                  # telefonda 3 sütun x 2 satır


def test_serit_konsensus_dahil_degil_notu(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch))
    assert "toplama dahil değil" in h and "CT konsensüs hesabı ayrı kasa" in h and "1 + 1 konsensüs" in h
    shutil.rmtree(tmp_path / "ct")
    assert "CT konsensüs hesabı ayrı kasa" not in _html(tmp_path / "durum") and "1 + 1 konsensüs" not in _html(tmp_path / "durum")


@pytest.mark.parametrize("gunluk,kill,doldu,seviye,ad", [(0.01, False, False, "guvenli", "Güvenli"), (0.04, False, False, "yakin", "Limite yakın"),
                                                         (0.05, False, True, "durdu", "Durdu"), (0.0, True, False, "durdu", "Durdu")])
def test_risk_durumu_kutusu(tmp_path, gunluk, kill, doldu, seviye, ad):
    _risk_durum(tmp_path, gunluk, kill, doldu)
    h = _html(tmp_path)
    assert f'data-risk="{seviye}"' in h
    kutu = h[h.index('data-risk='):h.index("</div></div>", h.index('data-risk='))]
    assert ad in kutu and "günlük kalan" in kutu and "durdurma sınırına kalan" in kutu and kutu.count('class="alt"') == 2


def test_risk_limitleri_koddan_okunur(tmp_path, monkeypatch):
    """%70 eşiği ve kalan tutar motor/risk/limitler.py sabitinden: sabit değişirse sonuç değişir (kopya yok)."""
    p = genis_durum()
    oz = copy.deepcopy(p["ozet"])
    oz["risk"]["gunluk_kayip"]["deger"] = 0.02
    assert pano.risk_durumu(oz)["seviye"] == "guvenli"
    monkeypatch.setattr(pano, "SERT_LIMITLER", type("L", (), {"gunluk_max_kayip_yuzde": 2.5, "kill_switch_dusus_yuzde": SERT_LIMITLER.kill_switch_dusus_yuzde})())
    assert pano.risk_durumu(oz)["seviye"] == "yakin"
    assert pano.risk_durumu(oz)["kalan_usd"] is not None


def test_ne_yapmaliyim_varsayilan_ve_durumlar(tmp_path):
    _risk_durum(tmp_path)
    veri, sorun = pano.yukle(tmp_path)
    veri["saglik"]["karantina"] = {"gorunur": [], "gizli": 0}
    veri["ozet"]["kaynak"] = "paper"
    assert pano.ne_yapmali(veri, sorun, SIMDI) == ("", "Bir şey yapmanız gerekmiyor.")
    assert "Bir şey yapmanız gerekmiyor." in _bolum(pano.html_olustur(veri, sorun, SIMDI), 1)
    veri["saglik"]["karantina"] = {"gorunur": ["a|BTCUSDT|1h"], "gizli": 0}
    sinif, metin = pano.ne_yapmali(veri, sorun, SIMDI)
    assert sinif == "gerek" and "Karantinada" in metin
    veri["ozet"]["risk"]["kill_switch"]["tetiklendi"] = True
    assert "Kill switch" in pano.ne_yapmali(veri, sorun, SIMDI)[1]


def test_uyari_bantlari_en_fazla_iki_gorunur_kalani_katlanir():
    u = [("kritik", "bir"), ("uyari", "iki"), ("bilgi", "uc"), ("uyari", "dort")]
    h = pano._gorunur_uyarilar(u)
    assert h.count('class="uyari ') == 1 and "4 durum var" in h and "DURUM kartında" in h and "<details" not in h      # üst bant tek satır
    assert 'class="uyari kritik"' in h and pano._gorunur_uyarilar([]) == ""


def test_otomatik_yenileme_son_guncelleme_iframe_ve_dugmeler(tmp_path):
    _risk_durum(tmp_path)
    h = _html(tmp_path)
    assert '<meta http-equiv="refresh" content="300">' in h
    assert 'id="gunc"' in h and 'data-uretim="2026-01-05T12:10:00Z"' in h and "Son güncelleme" in h and "Date.now()" in h
    assert "window.self!==window.top" in h and ".ifr .ust{display:none}" in h
    assert 'id="yazdir"' not in h and "Yazdır" not in h and "@media print" not in h
    assert 'id="tema"' in h and 'data-theme="light"' in h and 'data-theme="dark"' in h


# ------------------------------------------------------------------------------------------------------------ dosya adı / gizli ad / "_" yok
def test_dosya_alan_adi_alt_cizgi_ve_utc_gorunmez(tmp_path, monkeypatch):
    for durum in (ornek_kur(tmp_path / "tam", monkeypatch), ornek_kur(tmp_path / "bos", monkeypatch, tam=False)):
        m = _metin(_html(durum))
        assert not re.search(r"\.jsonl?\b", m) and "_" not in m and " UTC" not in m and "sha256" not in m.lower() and "motor yazar" not in m
    veri, sorun = pano.yukle(tmp_path / "yok")
    h = pano.html_olustur(veri, ["ozet.json okunamadı", "x"], SIMDI)
    assert ".json" not in _metin(h) and "veri dosyası" in _metin(pano._uyari_listesi(veri, ["ozet.json okunamadı", "x"], SIMDI))


def test_veri_yokken_henuz_veri_yok(tmp_path):
    d.yaz_hepsi(tmp_path, **genis_durum(ek=False), yazildi=d.zaman_oku("2026-01-05T12:05:00Z"))
    m = _metin(_html(tmp_path))
    assert "Veri yok:" not in m and "dosya_esik_dk" not in m
    h = pano.html_olustur({}, [], SIMDI)
    assert "Henüz veri yok" in h and "</html>" in h


def test_gizli_hesap_adi_hicbir_yerde_gorunmez(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch)).lower()
    govde = h.split("<main>")[-1].split("</main>")[0]
    for g in GIZLI_PARCA:
        assert g not in govde, g
    assert "diğer hesap" in govde


def test_hesap_adlari_ortak_fonksiyon_ve_telegram():
    from motor.canli import telegram as tg
    assert ha.coin_adi("SOLUSDT") == "SOL" and ha.coin_adi("BTCUSDT") == "BTC" and ha.coin_adi("DK_NVDA") == "NVDA"
    assert ha.hesap_adi("swing__cci-esik|SOLUSDT|1d") == "CCI Eşik · SOL 1G" == tg.ad("swing__cci-esik|SOLUSDT|1d")
    assert ha.hesap_adi("dis__bir-strateji|ETHUSDT|1h", gorunur=False) == "Diğer hesap"
    assert tg.ad("dis__bir-strateji|ETHUSDT|1h") == ha.hesap_adi("dis__bir-strateji|ETHUSDT|1h")


# ------------------------------------------------------------------------------------------------------------ ÖZET
def test_ozet_en_fazla_alti_kart_ve_isik_sirasi(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch))
    ozet = _bolum(h, 1)
    basliklar = re.findall(r'class="pb">([^<]+)<', ozet)
    assert len(basliklar) <= 6 and set(basliklar) == {"Durum", "Ne yapmalıyım?", "Açık işlemler", "Son kapanan işlemler", "Ders öğrenmesi", "Makine öğrenmesi"}
    assert basliklar[0] == "Durum" and "Performans uyarısı" in ozet and "BEKLENTİ ALARMI" in ozet                  # fixture: beklenti alarmı -> kırmızı ışık en üstte
    assert 'for="t3"' in ozet and "tümü" in ozet                                    # KAPANAN bağlantısı
    assert ozet.count("<tr") == 0                                                    # tablo yok: kısa kartlar
    _risk_durum(tmp_path / "temiz")
    ozet2 = _bolum(_html(tmp_path / "temiz"), 1)
    assert "Sistem sağlıklı" in ozet2 and re.findall(r'class="pb">([^<]+)<', ozet2)[-1] == "Durum"      # sağlıklıysa en altta


# ------------------------------------------------------------------------------------------------------------ AÇIK / KAPANAN / K/Z
def test_acik_sekmesi_konsensus_dahil_ve_satir_ayrintisi(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch))
    acik = _bolum(h, 2)
    assert "2 açık işlem · toplam K/Z" in acik and "+0,00 $" in acik
    assert re.findall(r"<span>([^<]+)</span>", re.search(r'<div class="lh">(.*?)</div>', acik).group(1)) == ["Sembol", "Giriş → şimdi", "K/Z", "Süre"]
    assert "HYPE" in acik and "CT konsensüs hesabı" in acik and "BTC" in acik and "HYPEUSDT" not in acik and "USDT" not in _metin(h)
    assert "<details" in acik and "Zarar-kes" in acik and "Büyüklük" in acik and "+1,50 $" in acik and "+%3,00" in acik
    assert 'class="daha"' in acik                                                                       # "daha fazla"


def test_kapanan_sekmesi_donem_secici_ozet_ve_konsensus(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch))
    kap = _bolum(h, 3)
    for b in ("Bugün", "7g", "30g", "Tümü"):
        assert f">{b}</button>" in kap
    assert 'id="k-n">4<' in kap and "kazanan" in kap and 'id="k-net"' in kap and "+3,90 $" in kap
    assert "CT konsensüs hesabı" in kap and "−2,40 $" in kap and "Diğer hesap" in kap
    assert kap.index("05.01 14:30") < kap.index("05.01 14:00") < kap.index("05.01 12:00")             # en yeni üstte
    assert kap.count('data-t="') == 4 and "Süre" in kap and "Çıkış" in kap


def test_kz_sekmesi_kaynaga_gore_ve_donemler(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch))
    kz = _bolum(h, 4)
    for b in ("Kasa eğrisi (30 gün)", "<svg", "Bugün", "7 gün", "30 gün", "Toplam", "Kazanma oranı", "Ortalama kazanç", "Ortalama kayıp", "Kaynağa göre K/Z", "Masraflar", "Komisyon", "Funding"):
        assert b in kz, b
    kaynak = kz[kz.index("Kaynağa göre K/Z"):]
    assert "CT konsensüs hesabı" in kaynak and "+250,25 $" in kaynak
    assert "Ortalama kayıp</span><b class=\"\">—" in kz or "Ortalama kayıp" in kz


# ------------------------------------------------------------------------------------------------------------ ÖĞRENME
def test_ders_ve_ml_kartlari_olculemiyorsa_uydurma_yok(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch))
    og = _bolum(h, 5)
    assert "Açık, işlemleri etkiliyor" in og and "Son öğrendiği" in og and "Son 7 günde değiştirdiği işlem" in og and "Son 5 ders" in og
    assert "Katkı (dersler olmasaydı farkı)" in og and "+0,50 R · son 90 gün" in og and "1 R = bir işlemde göze alınan risk" in og
    assert "0 onay · 2 ret" in og and "0 küçültme" not in og and "Son 5 karar" in og and "eğitim tarihi kayıtlı değil" in og and "Katkı (ML&#x27;li − ML&#x27;siz)" in og
    assert "Otomatik değişiklikler" in og and "Kâr koruyan iz-süren zarar-kes" in og and "geri alındı" in og


def test_ders_etkisiz_kirmizi_ve_kapali(tmp_path, monkeypatch):
    durum = ornek_kur(tmp_path, monkeypatch)
    _yaz(durum / "ogrenme_ders.json", {"a:dis_ewo_ema_ofset": {"status": "candidate", "born": "2026-01-01", "effect": None, "n": 0}})
    og = _bolum(_html(durum), 5)
    assert 'class="iyi">Açık, işlemleri etkiliyor' in og and "etkisiz" not in og     # aday ders de girişi atlatır (kâğıtta etkili)
    _yaz(durum / "ogrenme_ders.json", {"a:dis_ewo_ema_ofset": {"status": "retired", "born": "2026-01-01", "effect": None, "n": 0}})
    og = _bolum(_html(durum), 5)
    assert 'class="uyari">Açık, henüz ders çıkmadı' in og and "kotu\">Açık" not in og
    _yaz(durum / "ogrenme_ders.json", {"a:dis_ewo_ema_ofset": {"status": "alive", "born": "2026-01-01", "effect": None, "n": 0}})
    _yaz(durum / "ogrenme_fren.json", {"askida": {"a:dis_ewo_ema_ofset": {"zaman": "2026-01-02", "neden": "fren"}}})
    assert 'Açık, henüz ders çıkmadı' in _bolum(_html(durum), 5)                     # askıdaki ders girişi atlatmaz
    (durum / "ogrenme_fren.json").unlink()
    (durum / "ogrenme_ders.json").unlink()
    assert "Kapalı" in _bolum(_html(durum), 5)


def test_ml_isabet_yeterli_ornekle_ve_son_kararlar(tmp_path, monkeypatch):
    durum = ornek_kur(tmp_path, monkeypatch)
    satirlar = []
    for i in range(12):
        satirlar.append({"id": f"x{i}", "kurulum": "dis_ewo_ema_ofset", "enstruman": "SOLUSDT", "alindi": True, "r": 1.0 if i % 3 else -1.0,
                         "ts": f"2026-01-0{1 + i // 4}T0{i % 10}:00:00Z", "yon": "long"})
    _yaz(durum / "ogrenme_adaylar.jsonl", "".join(json.dumps(x) + "\n" for x in satirlar))
    _yaz(durum / "ogrenme_durum.json", {"drift_uyari": [], "egitim": {"dis_ewo_ema_ofset": {"zaman": "2026-01-04T21:00:00Z", "n": 12, "model": True}}})
    og = html.unescape(_bolum(_html(durum), 5))
    assert "05.01.2026 · 12 örnek" in og and "aldı · +1,00 R" in og and "SOL" in og


def test_alinsaydi_gevsetme_dosyasi_varsa_tek_satir(tmp_path, monkeypatch):
    durum = ornek_kur(tmp_path, monkeypatch, tam=False)
    assert "Henüz değişiklik yok" in _bolum(_html(durum), 5)
    _yaz(durum / "alinsaydi_gevsetme.json", [{"hesap": "dis__lube", "metin": "ML eşiği gevşetildi"}, {"metin": "Etiket kuralı kapatıldı"}])
    og = _bolum(_html(durum), 5)
    assert "Diğer hesap: ML eşiği gevşetildi" in og and "Etiket kuralı kapatıldı" in og and "lube" not in og.lower()
    _yaz(durum / "ogrenme_durum.json", {"drift": {"dis__lube": "sapma var"}, "drift_uyari": []})
    assert "Sapma: Diğer hesap sapma var" in _bolum(_html(durum), 5)


# ------------------------------------------------------------------------------------------------------------ TEKNİK
def test_teknik_bolumleri_katli_ve_bos_olanlar_gizli(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path, monkeypatch))
    tk = _bolum(h, 6)
    ad = re.findall(r'<details class="tk"><summary>([^<]+)</summary>', tk)
    assert ad[:3] == ["Sağlık", "Risk limitleri", "Kalite kapıları"] and "Model ayrıntısı" in ad and "Kayıtlar" in ad
    assert "Beklenti konumu" in ad and "Etiket × sonuç" in ad and "Aralık karnesi" not in ad      # veri yoksa bölüm yok
    assert tk.count("<details") == len(ad) and " open" not in tk
    bos = _bolum(_html(ornek_kur(tmp_path / "b", monkeypatch, tam=False)), 6)
    assert "Boşluk riski" not in bos and "veri birikiyor" not in bos


# ------------------------------------------------------------------------------------------------------------ 390 px
def _node_hazir() -> bool:
    return shutil.which("node") is not None and Path("/opt/node22/lib/node_modules/playwright").exists()


@pytest.mark.skipif(not _node_hazir(), reason="playwright (node) yok")
@pytest.mark.parametrize("genislik", [390, 1280])
def test_her_sekmede_yatay_kaydirma_yok(tmp_path, monkeypatch, genislik):
    html = tmp_path / "pano.html"
    html.write_text(_html(ornek_kur(tmp_path / "k", monkeypatch)), encoding="utf-8")
    betik = (f"const {{chromium}}=require('/opt/node22/lib/node_modules/playwright');(async()=>{{const b=await chromium.launch();const s=await b.newPage("
             f"{{viewport:{{width:{genislik},height:900}}}});await s.goto('file://{html}');const o=[];for(const t of ['t1','t2','t3','t4','t5','t6']){{await s.click('label[for='+t+']');"
             "await s.evaluate(()=>document.querySelectorAll('details').forEach(x=>x.open=true));o.push(await s.evaluate(()=>document.documentElement.scrollWidth))}"
             "console.log(JSON.stringify(o));await b.close()})()")
    cikti = subprocess.run(["node", "-e", betik], capture_output=True, text=True, timeout=120)
    assert cikti.returncode == 0, cikti.stderr
    assert max(json.loads(cikti.stdout.strip())) <= genislik


# ------------------------------------------------------------------------------------------------------------ Pano3 görünüm birliği
def test_tema_cihaz_ayarini_izler_sabit_koyu_yok(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path / "k", monkeypatch))
    css = re.search(r"<style>(.*?)</style>", h, re.S).group(1)
    assert "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"])" in css
    assert ':root[data-theme="dark"]' in css and ':root[data-theme="light"]' in css
    kok = re.search(r"(?m)^:root\{([^}]*)\}", css).group(1)
    assert "--bg:#f1f2f5" in kok and "#0a0a0b" not in kok          # varsayılan açık; sabit koyu yok
    assert "color-scheme" not in kok or "dark" not in kok


def test_tema_localstorage_try_catch_ve_iframe_gizli(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path / "k", monkeypatch))
    js = h[h.index("1l3a-tema") - 60:]
    assert "try{var t=localStorage.getItem(k)" in js and "try{localStorage.setItem(k,y)}catch(e){}" in js and "setAttribute('data-theme'" in js
    assert "window.self!==window.top" in h and ".ifr .ust{display:none}" in h


def test_rozet_yalniz_acik_ve_kapanan(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path / "k", monkeypatch))
    tabs = re.search(r'<div class="tabs".*?</div>', h, re.S).group(0)
    etiketler = re.findall(r'<label for="(t\d)">(.*?)</label>', tabs, re.S)
    assert len(etiketler) == 6
    for i, ic in etiketler:
        assert ("<em>" in ic) == (i in ("t2", "t3")), (i, ic)
    assert "<em" not in tabs.split('for="t4"')[1]


def test_gorunum_radius_yazi_tipi_ve_serit(tmp_path, monkeypatch):
    h = _html(ornek_kur(tmp_path / "k", monkeypatch))
    assert re.search(r"\.kart\{[^}]*border-radius:12px", h)
    assert 'system-ui,-apple-system,"Segoe UI",Roboto,sans-serif' in h and "ui-monospace" not in h
    assert "font-variant-numeric:tabular-nums" in h
    assert ".serit{grid-template-columns:repeat(3,minmax(0,1fr))}" in h


def _ekran_goruntusu(tmp_path, monkeypatch, renk, ad):
    html_ = tmp_path / "pano.html"
    html_.write_text(_html(ornek_kur(tmp_path / "k", monkeypatch)), encoding="utf-8")
    hedef = tmp_path / "ekran" / ad                  # repodaki raporlar/pano3 dosyaları test koşusunda yeniden yazılmaz
    hedef.parent.mkdir(parents=True, exist_ok=True)
    betik = ("const {chromium}=require('/opt/node22/lib/node_modules/playwright');(async()=>{const b=await chromium.launch();"
             f"const c=await b.newContext({{viewport:{{width:390,height:844}},deviceScaleFactor:2,colorScheme:'{renk}'}});const s=await c.newPage();"
             f"await s.goto('file://{html_}');await s.screenshot({{path:'{hedef}',fullPage:true}});await b.close()}})()")
    return subprocess.run(["node", "-e", betik], capture_output=True, text=True, timeout=120), hedef


@pytest.mark.skipif(not _node_hazir(), reason="playwright (node) yok")
@pytest.mark.parametrize("renk,ad", [("light", "pano3_ozet_390_acik.png"), ("dark", "pano3_ozet_390_koyu.png")])
def test_ozet_ekran_goruntusu_acik_koyu(tmp_path, monkeypatch, renk, ad):
    r, hedef = _ekran_goruntusu(tmp_path, monkeypatch, renk, ad)
    assert r.returncode == 0, r.stderr
    assert hedef.exists()


def test_eski_tema_anahtari_sifirlanir_ve_iframe_cihaz_temasini_izler():
    from motor.canli import pano
    src = open(pano.__file__, encoding="utf-8").read()
    assert "localStorage.removeItem('1l3a-tema')" in src and "'1l3a-tema-v2'" in src     # eski "koyu" seçimi bir kez silinir
    assert "if(!/\\bifr\\b/.test(h.className))" in src                                   # kapı iframe'inde kayıtlı tema okunmaz: cihaz ayarı


def test_ml_karti_ortak_ifadeler():
    from motor.canli import pano
    taban = {"acik": True, "min_n": 10, "onay7": 0, "ret7": 0, "fark_r": None, "pencere": None, "son_egitim": None, "son5": []}
    h = pano._ml_karti({**taban, "model_sayisi": 0, "en_cok_islem": 7})
    assert "Açık, veri birikiyor (7/10 işlem)" in h and "henüz model kurulmadı" not in h
    assert "Açık, model bekleniyor" in pano._ml_karti({**taban, "model_sayisi": 0, "en_cok_islem": 12})
    assert "Açık, işlemleri etkiliyor" in pano._ml_karti({**taban, "model_sayisi": 2, "en_cok_islem": 12})
    assert "Kapalı" in pano._ml_karti({"acik": False})
