"""Dış nabız: sunucu tarafı mantığı (motor/canli/nabiz.py) ve Worker (deploy/nabiz_worker.js, node ile)."""
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from motor.canli import nabiz

KOK = Path(__file__).resolve().parent.parent
WORKER = KOK / "deploy" / "nabiz_worker.js"
SIMDI = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)


def _kalp(tmp_path, dk_once):
    z = (SIMDI - timedelta(minutes=dk_once)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (tmp_path / "kalp_atisi.json").write_text(json.dumps({"zaman": z}))


def test_taze_kalp_iyi(tmp_path):
    _kalp(tmp_path, 2)
    g = nabiz.govde_uret(SIMDI, True, False, tmp_path)
    assert g == {"proje": "1l3a", "zaman": "2026-11-19T12:00:00Z", "durum": "iyi"}


def test_bayat_kalp_sorunlu(tmp_path):
    _kalp(tmp_path, 15)
    g = nabiz.govde_uret(SIMDI, True, False, tmp_path)
    assert g["durum"] == "paper_sorunlu" and g["neden"] == "kalp bayat 15 dk"


def test_servis_kapali_sorunlu(tmp_path):
    _kalp(tmp_path, 1)
    g = nabiz.govde_uret(SIMDI, False, False, tmp_path)
    assert g["durum"] == "paper_sorunlu" and "aktif değil" in g["neden"]


def test_kalp_dosyasi_yok_veya_bozuk(tmp_path):
    assert nabiz.govde_uret(SIMDI, True, False, tmp_path)["durum"] == "paper_sorunlu"
    (tmp_path / "kalp_atisi.json").write_text("{bozuk")
    assert nabiz.govde_uret(SIMDI, True, False, tmp_path)["durum"] == "paper_sorunlu"


def test_canli_bilgisi_eklenir(tmp_path):
    _kalp(tmp_path, 1)
    assert nabiz.govde_uret(SIMDI, True, True, tmp_path)["canli"] == "aktif"


class _Yanit:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_anahtar_basliktadir_urlde_degil():
    gorulen = {}

    def acici(istek, timeout):
        gorulen["url"], gorulen["basliklar"] = istek.full_url, dict(istek.header_items())
        gorulen["govde"] = json.loads(istek.data)
        return _Yanit()

    assert nabiz.gonder({"durum": "iyi"}, "https://x.workers.dev/", "GIZLI-ANAHTAR", acici)
    assert gorulen["url"] == "https://x.workers.dev/nabiz" and "GIZLI" not in gorulen["url"]
    assert gorulen["basliklar"]["X-nabiz-anahtar"] == "GIZLI-ANAHTAR"
    assert "GIZLI" not in json.dumps(gorulen["govde"])


def test_ag_hatasi_false_doner_ve_loga_sir_yazmaz(caplog):
    def acici(istek, timeout):
        raise OSError("https://x.workers.dev GIZLI-ANAHTAR")

    assert nabiz.gonder({}, "https://x.workers.dev", "GIZLI-ANAHTAR", acici) is False
    assert "GIZLI" not in caplog.text and "workers.dev" not in caplog.text


def test_main_ortam_yoksa_0(monkeypatch):
    assert nabiz.main({}) == 0


def test_main_ag_hatasinda_0(monkeypatch, tmp_path):
    monkeypatch.setattr(nabiz, "servis_aktif_mi", lambda ad: False)
    monkeypatch.setattr(nabiz, "gonder", lambda *a, **k: False)
    assert nabiz.main({"NABIZ_URL": "https://x", "NABIZ_ANAHTAR": "a", "NABIZ_DURUM_DIZIN": str(tmp_path)}) == 0


# ---------------------------------------------------------------- Worker (node)
NODE_KOD = r"""
import { pathToFileURL } from "node:url";
const w = (await import(pathToFileURL(process.argv[1]).href)).default;
function kv() { const m = new Map(); return { m, get: async (k) => m.get(k) ?? null, put: async (k, v) => { m.set(k, v); } }; }
function ortam(extra = {}) { return { NABIZ: kv(), NABIZ_ANAHTAR: "dogru-anahtar", TELEGRAM_BOT_TOKEN: "123456:SAHTE-TOKEN-ABCDEFGHIJKLMNOP", TELEGRAM_CHAT_ID: "42", ...extra }; }
const mesajlar = [];
globalThis.fetch = async (url, o) => { mesajlar.push({ url, metin: JSON.parse(o.body).text }); return new Response("{}", { status: 200 }); };
const post = (e, anahtar, govde = { durum: "iyi" }) => w.fetch(new Request("https://x.test/nabiz", { method: "POST",
  headers: anahtar ? { "X-Nabiz-Anahtar": anahtar } : {}, body: JSON.stringify(govde) }), e);
const DK = 60000, T0 = 1_800_000_000_000;
const r = {};
let e = ortam();
r.yanlis = (await post(e, "yanlis")).status;
r.baslik_yok = (await post(e, null)).status;
r.secret_yok = (await post(ortam({ NABIZ_ANAHTAR: undefined }), "")).status;
r.get404 = (await w.fetch(new Request("https://x.test/"), e)).status;
r.get_nabiz404 = (await w.fetch(new Request("https://x.test/nabiz"), e)).status;
r.kayitsiz = e.NABIZ.m.size;
// ilk kurulum: kayıt yok -> uyarı yok
await w.kontrol(e, T0); r.ilk_uyari = mesajlar.length;
// nabız geldi, 19 dk -> uyarı yok; 21 dk -> uyarı
r.dogru = (await post(e, "dogru-anahtar")).status;
const son = JSON.parse(e.NABIZ.m.get("nabiz")); son.son = T0; e.NABIZ.m.set("nabiz", JSON.stringify(son));
await w.kontrol(e, T0 + 19 * DK); r.esik19 = mesajlar.length;
await w.kontrol(e, T0 + 21 * DK); r.esik21 = mesajlar.length; r.mesaj21 = mesajlar[0]?.metin;
// 2 saat sınırı: +60 dk yok, +125 dk var
await w.kontrol(e, T0 + 80 * DK); r.tekrar_erken = mesajlar.length;
await w.kontrol(e, T0 + 145 * DK); r.tekrar_gec = mesajlar.length;
// geri geldi
son.son = T0 + 150 * DK; e.NABIZ.m.set("nabiz", JSON.stringify(son));
await w.kontrol(e, T0 + 151 * DK); r.geri = mesajlar[mesajlar.length - 1].metin; r.geri_say = mesajlar.length;
await w.kontrol(e, T0 + 152 * DK); r.geri_tekrar_yok = mesajlar.length;
// paper_sorunlu
mesajlar.length = 0; e = ortam();
await post(e, "dogru-anahtar", { durum: "paper_sorunlu", neden: "kalp bayat 15 dk" });
const s2 = JSON.parse(e.NABIZ.m.get("nabiz")); s2.son = T0; e.NABIZ.m.set("nabiz", JSON.stringify(s2));
await w.kontrol(e, T0 + 5 * DK); r.sorunlu1 = mesajlar.map((m) => m.metin);
await w.kontrol(e, T0 + 10 * DK); r.sorunlu_tekrar_yok = mesajlar.length;
r.token_mesajda = mesajlar.some((m) => m.metin.includes("SAHTE-TOKEN"));
console.log(JSON.stringify(r));
"""


@pytest.fixture(scope="module")
def js():
    if not shutil.which("node"):
        pytest.skip("node yok")
    r = subprocess.run(["node", "--input-type=module", "-e", NODE_KOD, str(WORKER)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_worker_yetki(js):
    assert js["yanlis"] == 401 and js["baslik_yok"] == 401 and js["secret_yok"] == 401
    assert js["kayitsiz"] == 0 and js["dogru"] == 200


def test_worker_diger_istekler_404(js):
    assert js["get404"] == 404 and js["get_nabiz404"] == 404


def test_worker_ilk_kurulumda_uyari_yok(js):
    assert js["ilk_uyari"] == 0


def test_worker_esik_20dk(js):
    assert js["esik19"] == 0 and js["esik21"] == 1
    assert "🚨 1L3A sunucusu 21 dk'dır ses vermiyor" == js["mesaj21"]


def test_worker_tekrar_siniri_2saat(js):
    assert js["tekrar_erken"] == 1 and js["tekrar_gec"] == 2


def test_worker_geri_gelme_bir_kez(js):
    assert js["geri"].startswith("✅ 1L3A sunucusu yeniden ses veriyor (kesinti ~150 dk)")
    assert js["geri_say"] == 3 and js["geri_tekrar_yok"] == 3


def test_worker_paper_sorunlu(js):
    assert len(js["sorunlu1"]) == 1 and "paper sorunlu" in js["sorunlu1"][0] and "kalp bayat" in js["sorunlu1"][0]
    assert js["sorunlu_tekrar_yok"] == 1 and js["token_mesajda"] is False
