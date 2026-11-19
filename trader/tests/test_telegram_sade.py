"""Sade Telegram mesajlari: onek, satir siniri, yasak kelimeler, 6 saat tekrar kurali, Duzeldi, "Bot durdu" muafiyeti,
gunluk zarar %80 (gunde bir), islem acildi/kapandi bicimi, susturulan turler."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from test_telegram_report import DAY, NOW, mkledger
from trader_core import health as H
from trader_core import lesson as LS
from trader_core import telegram as T
from trader_core import tg_sade as TS

UTC = timezone.utc
T0 = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
YASAK = re.compile(r"_|journalctl|systemctl|sunucu|\.py|\.service|\.timer|\.json|\.sqlite|trader_|\.sh\b", re.I)


class Clk:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def adv(self, **kw):
        self.t += timedelta(**kw)


class Fake:
    def __init__(self):
        self.texts = []

    def __call__(self, url, json=None, timeout=None):
        if url.endswith("sendMessage"):
            self.texts.append(json["text"])
        return 200, {"ok": True, "result": {"message_id": len(self.texts)}}


@pytest.fixture
def rig(tmp_path):
    clk, fake = Clk(), Fake()
    env = {"TELEGRAM_BOT_TOKEN": "1:tok", "TELEGRAM_CHAT_ID": "5", "TELEGRAM_VAR_DIR": str(tmp_path / "tg"),
           "ENGINE_STATUS_PATH": str(tmp_path / "status.json"), "LEDGER_PATH": str(tmp_path / "l.sqlite")}
    n = T.notifier_from_env(env, fake, clk, lambda s: None)
    cfg = T.TelegramConfig.from_env(env)
    return type("R", (), {"clk": clk, "fake": fake, "n": n, "cfg": cfg, "tmp": tmp_path})


def alert(code, level=H.Status.WARN, fp=None, title="t", now=T0):
    return H.Alert(level, code, title, "b", fp or f"x|{code}", now)


def ok_form(text, max_satir=TS.MAX_SATIR):
    assert text.startswith("[ML] "), text
    assert len(text.splitlines()) <= max_satir, text
    assert not YASAK.search(text), text


# ------------------------------------------------------------------ bicim: onek, satir siniri, yasak kelime
def test_tum_bicimleyiciler_kurallara_uyar(tmp_path):
    sp = tmp_path / "status.json"
    sp.write_text(json.dumps({"open_positions": [{"pair": "SOL/USDT", "stop": 1.0}, {"pair": "BTC/USDT", "stop": 2.0}]}))
    metinler = [
        TS.islem_acildi("learner", "SOL/USDT", "long", 142.3, 300, 139.1),
        TS.islem_kapandi("learner", "SOL/USDT", "long", 9.6, 300, "target"),
        TS.islem_kapandi("learner", "BTC/USDT", "short", -6.4, 300, "trail_stop"),
        TS.limit_uyari(40.0, 50.0), TS.limit_doldu(50.0, 50.0), TS.bot_durdu(str(sp)), TS.bot_durdu(None),
        TS.bot_duzeldi(), TS.duzeldi("hesap_ayarı yeniden doğru"),
        TS.onay_istegi("rr_min", 1.5, 1.8, "kanıt_sayısı yeterli", "17.11 10:00"),
        TS.ders_mesaji("warn", "rolled_back"),
        TS.birim_metni("trader-feed.service"), TS.birim_metni("trader-engine-live.service", str(sp)),
        TS.birim_metni("trader-backup.service"),
        T.build_report(T.TelegramConfig("1:t", 5, str(tmp_path), "", str(sp), ledger_path=str(tmp_path / "l")), NOW, DAY),
    ]
    for m in metinler:
        assert m is not None
        ok_form(m, TS.MAX_SATIR_OZET if "Günlük özet" in m else TS.MAX_SATIR)
    for kod in list(TS._SADE):
        t = TS.saglik_mesaji(alert(kod, H.Status.CRIT, fp=f"x|{kod}"))[1]
        ok_form(t)
        ok_form(TS.saglik_mesaji(alert(kod, H.Status.OK, fp=f"x|{kod}"))[1])


def test_yasak_izler_temizlenir():
    t = TS.temizle("sunucuda trader_engine.service durdu, journalctl bak: rr_min")
    assert not YASAK.search(t) and "durdu" in t


# ------------------------------------------------------------------ islem mesajlari
def test_acildi_tam_iki_satir():
    t = TS.islem_acildi("learner", "SOL/USDT", "long", 142.3, 300, 139.1)
    assert t == "[ML] 🟩 öğrenen · SOL · uzun\nGiriş 142,30 · Tutar 300 $ · Stop 139,10"
    assert "USDT" not in t and len(t.splitlines()) == 2
    assert "kısa" in TS.islem_acildi("learner", "BTC/USDT", "short", 60000, 500, 61000)


def test_kapandi_sonuc_neden_ve_ikon():
    k = TS.islem_kapandi("learner", "SOL/USDT", "long", 9.6, 300, "target")
    assert k == "[ML] 🟢 öğrenen · SOL · uzun kapandı\nSonuç +9,60 $ (+3,2%) · kâr al"
    z = TS.islem_kapandi("learner", "BTC/USDT", "short", -6.4, 300, "stop")
    assert z.splitlines()[0].startswith("[ML] 🔻") and "−6,40 $ (−2,1%) · stop" in z
    assert "🔴" not in z and "🔴" in TS.islem_kapandi("learner", "BTC/USDT", "short", -6.4, 300, "stop", kritik=True)
    assert "süre" in TS.islem_kapandi("learner", "ETH/USDT", "long", 1, 100, "time_stop")
    assert "elle" in TS.islem_kapandi("learner", "ETH/USDT", "long", 1, 100, "manual")


def test_islem_tick_acilan_ve_kapanani_bildirir_tekrar_etmez(rig):
    mkledger(rig.tmp / "l.sqlite", "learner", [(True, True), (False, False)])
    (rig.tmp / "tg").mkdir(exist_ok=True)
    (rig.tmp / "tg" / "islem_imleci.json").write_text(json.dumps({"acilan": [], "kapanan": []}))
    n = T.islem_tick(rig.cfg, rig.n, NOW)
    assert n == 3                                          # 2 acilis + 1 kapanis
    assert sum("kapandı" in t for t in rig.fake.texts) == 1
    assert sum(t.splitlines()[1].startswith("Giriş") for t in rig.fake.texts if "kapandı" not in t) == 2
    for t in rig.fake.texts:
        ok_form(t, 2)
    assert T.islem_tick(rig.cfg, rig.n, NOW) == 0          # ayni islem ikinci kez gitmez


def test_islem_tick_ilk_calismada_gecmis_yagmuru_yok(rig):
    mkledger(rig.tmp / "l.sqlite", "learner", [(True, True), (False, True)])
    (rig.tmp / "tg").mkdir(exist_ok=True)
    assert T.islem_tick(rig.cfg, rig.n, NOW) == 0 and rig.fake.texts == []


# ------------------------------------------------------------------ 6 saat kurali + Duzeldi
def test_ayni_alarm_6_saatte_bir_ve_duzeldi_bir_kez(rig):
    a = alert("account_mode_drift", fp="account_mode:learner|account_mode_drift")
    assert rig.n.send(a) is True
    assert len(rig.fake.texts) == 1
    ok_form(rig.fake.texts[0])
    assert rig.fake.texts[0].splitlines()[2].startswith("Senden:")
    rig.clk.adv(hours=5, minutes=59)
    rig.n.send(a)
    assert len(rig.fake.texts) == 1                        # 6 saat dolmadi
    rig.clk.adv(minutes=2)
    rig.n.send(a)
    assert len(rig.fake.texts) == 2                        # 6 saat doldu: bir hatirlatma
    duz = alert("account_mode_drift", H.Status.OK, fp="account_mode:learner|account_mode_drift")
    rig.n.send(duz)
    rig.n.send(duz)
    assert len(rig.fake.texts) == 3 and rig.fake.texts[-1].startswith("[ML] ✅ Düzeldi")   # tek Duzeldi


def test_uyarisi_gitmemis_sey_icin_duzeldi_gitmez(rig):
    rig.n.send(alert("account_mode_drift", H.Status.OK, fp="a|account_mode_drift"))
    assert rig.fake.texts == []


def test_ek_uyari_parmak_izi_zaman_damgali_olsa_da_6_saat_kurali(rig):
    for i in range(3):
        rig.n.send(alert("disk_dolu", fp=f"disk|dolu|{rig.clk().isoformat()}", title="Disk dolmak üzere (%85)"))
        rig.clk.adv(hours=1)
    assert len(rig.fake.texts) == 1 and "(%85)" in rig.fake.texts[0]
    rig.n.send(alert("disk_dolu", H.Status.OK, fp=f"disk|dolu|duzeldi|{rig.clk().isoformat()}"))
    assert len(rig.fake.texts) == 2 and "Düzeldi" in rig.fake.texts[1]


# ------------------------------------------------------------------ Bot durdu
def test_bot_durdu_6_saat_kuralindan_muaf_ve_pozisyon_bilgisi_verir(rig):
    (rig.tmp / "status.json").write_text(json.dumps({"open_positions": [{"pair": "SOL/USDT", "stop": 139.1}]}))
    a = alert("api_unreachable", H.Status.CRIT, fp="api_reachable:learner|api_unreachable")
    rig.n.send(a)
    rig.clk.adv(minutes=20)
    rig.n.send(a)
    rig.clk.adv(minutes=20)
    rig.n.send(a)
    assert len(rig.fake.texts) == 3                        # her seferinde gider (6 saat kurali yok)
    t = rig.fake.texts[0]
    assert t.startswith("[ML] 🔴 Bot durdu") and "Açık pozisyon: 1" in t and "stopları borsada yerinde" in t
    ok_form(t)
    rig.n.send(alert("api_unreachable", H.Status.OK, fp="api_reachable:learner|api_unreachable"))
    rig.n.send(alert("api_unreachable", H.Status.OK, fp="api_reachable:learner|api_unreachable"))
    assert rig.fake.texts[3] == "[ML] ✅ Düzeldi: bot yeniden çalışıyor." and len(rig.fake.texts) == 4


def test_bot_durdu_durum_dosyasi_yoksa_stopu_kontrol_ettirir(rig):
    t = TS.bot_durdu(None)
    assert "stopları kontrol et" in t
    assert "Açık pozisyon yok" in TS.bot_durdu(_bos_durum(rig))


def _bos_durum(rig):
    p = rig.tmp / "bos.json"
    p.write_text(json.dumps({"open_positions": []}))
    return str(p)


def test_motor_deneme_tukendi_ve_birim_basarisiz_bot_durdu_olur(rig):
    a = H.Alert(H.Status.CRIT, "engine_retry_exhausted", "x", "y", "engine-retry-exhausted:learner", T0)
    rig.n.send(a)
    assert rig.fake.texts[0].startswith("[ML] 🔴 Bot durdu")
    assert "feed" not in TS.birim_metni("trader-feed.service").lower()
    assert TS.birim_metni("trader-telegram.service") is None


# ------------------------------------------------------------------ gunluk zarar %80
def _durum(rig, eq, dse=1000.0):
    (rig.tmp / "status.json").write_text(json.dumps({"equity": eq, "day_start_equity": dse}))


def test_zarar_80_yuzde_gunde_bir_kez(rig):
    _durum(rig, 970.0)                                     # 30 $ / 50 $ = %60: sessiz
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 0
    _durum(rig, 960.0)                                     # 40 $ = %80
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 1
    assert T.zarar_tick(rig.cfg, rig.n, T0 + timedelta(hours=1)) == 0       # ayni gun ikinci uyari yok
    assert "%80" in rig.fake.texts[0] and "Günlük zarar sınırına yaklaşıldı" in rig.fake.texts[0]
    ok_form(rig.fake.texts[0])
    assert T.zarar_tick(rig.cfg, rig.n, T0 + timedelta(days=1)) == 1        # ertesi gun yine
    assert len(rig.fake.texts) == 2


def test_limit_doldu_acik_pozisyonlarin_akibetini_soyler(rig):
    _durum(rig, 945.0)
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 1
    t = rig.fake.texts[0]
    assert "limiti doldu" in t and "stoplarıyla yönetilmeye devam" in t and "yeni işlem açılmaz" in t
    ok_form(t)
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 0


# ------------------------------------------------------------------ susturulan turler
@pytest.mark.parametrize("kod", ["ct_kadro_bayat", "pa_proposer_stale", "tutarlilik_sapma", "heartbeat_send_failed",
                                 "ml_expiring_7d", "ml_expiring_3d", "ml_shadow_down", "drift_stale", "bilinmeyen_kod"])
def test_teknik_uyarilar_susar(rig, kod):
    assert rig.n.send(alert(kod)) is True
    assert rig.n.send(alert(kod, H.Status.OK)) is True
    assert rig.fake.texts == []


def test_ders_info_ve_teknik_hatalar_susar_geri_alma_gider(rig):
    def nt(level, code):
        return LS.LessonNotice(level, code, "t", "b", f"{code}|d|1", T0)
    for lvl, code in (("info", "applied"), ("info", "needs_user_expired"), ("warn", "run_failed"), ("warn", "llm_error")):
        assert rig.n.notify(nt(lvl, code)) is True
    assert rig.fake.texts == []
    rig.n.notify(nt("warn", "rolled_back"))
    rig.n.notify(nt("warn", "rolled_back"))
    assert len(rig.fake.texts) == 1 and "geri alındı" in rig.fake.texts[0]


def test_onay_istegi_karar_mesaji_kisa_ve_sade(rig):
    req = LS.ApprovalRequest(request_id="lr-2026-11-16-1", proposal_id=3, base_version_id=1, param="rr_min", from_value=1.5,
                             to_value=1.8, scope="s", reason_code="rc", shadow_period=False, provisional=False, title="T",
                             body="kanıt_sayısı yeterli, kâr artıyor", evidence={"n": 1}, created_at=T0,
                             expires_at=T0 + timedelta(hours=24))
    assert rig.n.request_approval(req) is True
    t = rig.fake.texts[0]
    assert t.startswith("[ML] 🗳 Karar gerekiyor: en düşük kazanç/risk oranı")
    assert len(t.splitlines()) <= 6 and "rr_min" not in t and "kanıt sayısı" in t
    assert "/onayla lr-2026-11-16-1" in t


def test_gunluk_ozet_12_satiri_asmaz_ve_haftalik_yalniz_pazar(rig):
    mkledger(rig.tmp / "l.sqlite", "learner", [(True, True), (False, True)] * 4)
    (rig.tmp / "tg").mkdir(exist_ok=True)
    pos = [{"pair": f"P{i}/USDT", "side": "long", "stop": 1.0} for i in range(9)]
    (rig.tmp / "status.json").write_text(json.dumps({
        "mode": "live", "equity": 900.0, "day_start_equity": 1000.0, "entries_open": False, "open_positions": pos,
        "loop_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}))
    rep = T.build_report(rig.cfg, NOW, DAY, {})
    ok_form(rep, TS.MAX_SATIR_OZET)
    assert not T.haftalik_gonder(rig.cfg, rig.n, NOW)                         # 16 Kasim 2026 pazartesi
    pazar = datetime(2026, 11, 22, 18, 0, tzinfo=UTC)
    assert T.haftalik_gonder(rig.cfg, rig.n, pazar) is True
    assert T.haftalik_gonder(rig.cfg, rig.n, pazar) is False                  # haftada bir
    ok_form(rig.fake.texts[-1])
    assert rig.fake.texts[-1].startswith("[ML] 🗓 Haftalık özet")
