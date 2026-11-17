"""WP-B6 Telegram duraklatma duman testleri (11 §9.5): /durdur, /devam katmanlari, /durum satiri."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import telegram as T
from trader_engine.clock import SimClock
from trader_engine.killswitch import Killswitch
from trader_engine.pause import EntryPause

UTC = timezone.utc
CHAT = 555000111
T0 = datetime(2026, 12, 30, 10, 0, tzinfo=UTC)


class Clk:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


class FakeTG:
    def __init__(self):
        self.calls = []

    def __call__(self, url, json=None, timeout=None):
        m = url.rsplit("/", 1)[1]
        self.calls.append((m, json))
        if m == "sendMessage":
            return 200, {"ok": True, "result": {"message_id": len(self.calls)}}
        return 200, {"ok": True, "result": []}

    def texts(self):
        return [p["text"] for m, p in self.calls if m == "sendMessage"]


class _Fn:
    def __init__(self, fn):
        self.fn = fn

    def now(self):
        return self.fn()


@pytest.fixture
def rig(tmp_path):
    clk, fake = Clk(), FakeTG()
    cfg = T.TelegramConfig(token="1:tok", chat_id=CHAT, var_dir=str(tmp_path / "tg"), kill_file=str(tmp_path / "KILL"),
                           status_path=str(tmp_path / "status.json"))
    ks = Killswitch(cfg.kill_file, _Fn(clk))
    pauses = {b: EntryPause(str(tmp_path / f"PAUSE.{b}"), _Fn(clk), audit_path=str(tmp_path / f"a.{b}.jsonl"))
              for b in ("learner", "twin")}
    d = T.TelegramDaemon(cfg, T.TelegramClient("1:tok", fake, lambda s: None), now_fn=clk,
                         runner=lambda *a: (0, "{}"), sleep=lambda s: None, random_code=lambda: "0427",
                         killswitch=ks, pauses=pauses)
    d.r = type("R", (), {"clk": clk, "fake": fake, "tmp": tmp_path, "pauses": pauses})
    return d


def msg(d, text, uid, age=0):
    return {"update_id": uid, "message": {"message_id": uid, "date": int(d.r.clk().timestamp()) - age,
                                          "chat": {"id": CHAT, "type": "private"}, "from": {"id": CHAT}, "text": text}}


def say(d, text, uid):
    d.process_updates([msg(d, text, uid)])
    return d.r.fake.texts()[-1]


def status(d, **kw):
    st = {"mode": "paper", "kill_state": "flat"}
    st.update(kw)
    Path(d.cfg.status_path).write_text(json.dumps(st))


def test_durdur_two_steps_all_bots(rig):
    d = rig
    assert "0427" in say(d, "/durdur", 1)
    assert not any(p.active() for p in d.r.pauses.values())
    assert "Yeni giriş durduruldu" in say(d, "0427", 2) and "/hepsini_kapat" in d.r.fake.texts()[-1]
    for p in d.r.pauses.values():
        (h,) = p.holds()
        assert h.reason == "user_cmd" and h.by == "telegram:111"
    assert "zaten" in say(d, "/durdur", 3)          # idempotent, kod yok
    assert not d._pending_p.exists()


def test_durdur_ttl_boundaries(rig):
    d = rig
    for age, ok in ((119, True), (120, True), (121, False)):
        for p in d.r.pauses.values():
            p.remove("user_cmd", "t")
        d.r.clk.t = T0
        say(d, "/durdur", 10 + age)
        d.r.clk.t = T0 + timedelta(seconds=age)
        d.process_updates([msg(d, "0427", 1000 + age)])
        assert d.r.pauses["learner"].active() is ok, age


def test_durdur_wrong_code_cancels_and_works_with_kill(rig):
    d = rig
    d.killswitch.set("telegram:111", "user_cmd")
    say(d, "/durdur", 1)
    say(d, "9999", 2)
    assert not d.r.pauses["learner"].active() and not d._pending_p.exists()
    say(d, "/durdur", 3)
    say(d, "0427", 4)
    assert d.r.pauses["learner"].active() and d.killswitch.active()


def test_devam_one_layer_per_call(rig):
    d = rig
    status(d, mode="paper")
    d.killswitch.set("telegram:111", "user_cmd")
    for p in d.r.pauses.values():
        p.add("user_cmd", "telegram:111")
    t = say(d, "/devam", 1)
    assert "KILL kaldirilacak" in t and "duraklatma" in t
    assert "learner: user_cmd — girişler hâlâ kapalı" in say(d, "0427", 2)
    assert not d.killswitch.active() and d.r.pauses["learner"].active()
    assert "duraklatma" in say(d, "/devam", 3)
    t = say(d, "0427", 4)
    assert "learner: girişler açık" in t and "twin: girişler açık" in t
    assert not any(p.active() for p in d.r.pauses.values())
    assert "etkin degil" in say(d, "/devam", 5)


def test_devam_origin_rule_and_drawdown_review(rig):
    d = rig
    d.r.pauses["learner"].add("drawdown_review", "engine:rk1")
    d.r.pauses["twin"].add("unknown_position", "engine:reconcile")
    t = say(d, "/devam", 1)
    assert "kaldırılamaz" in t and "drawdown_review" in t and not d._pending_p.exists()
    d.r.pauses["learner"].add("user_cmd", "telegram:111")
    say(d, "/devam", 2)
    t = say(d, "0427", 3)
    assert "learner: drawdown_review — girişler hâlâ kapalı" in t and "twin: unknown_position" in t
    assert [h.reason for h in d.r.pauses["learner"].holds()] == ["drawdown_review"]
    assert d.r.pauses["twin"].active()
    assert "kaldırılamaz" in say(d, "/devam", 4)


def test_devam_kill_layer_still_refuses_exiting_and_live_rules(rig):
    d = rig
    d.r.pauses["learner"].add("user_cmd", "telegram:111")
    d.killswitch.set("telegram:111", "user_cmd")
    status(d, kill_state="exiting")
    assert "kapanis" in say(d, "/devam", 1)
    assert d.r.pauses["learner"].active()


def test_status_line_and_legacy_durdur(rig, tmp_path):
    d = rig
    status(d)
    say(d, "/durdur", 1)
    say(d, "0427", 2)
    say(d, "/durum", 3)
    t = d.r.fake.texts()[-1]
    assert "duraklatma learner: user_cmd (telegram:111, 2026-12-30T10:00:00Z)" in t
    d2 = T.TelegramDaemon(d.cfg, d.client, now_fn=d.r.clk, runner=lambda *a: (0, "{}"), killswitch=d.killswitch)
    d2.r = d.r
    d2.process_updates([msg(d2, "/durdur", 9)])
    assert "desteklenmiyor" in d.r.fake.texts()[-1]
