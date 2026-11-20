"""Otomatik güncelleme (motor/canli/oto_guncelle.py): git, ağ, systemctl, telegram SAHTE. Ağ yok."""
import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from motor.canli import oto_guncelle as og
from testler.test_telegram_komut import CHAT, SahteIstemci, SabitRng, Saat, kur, mesaj, son  # noqa: F401

ESKI, YENI = "a" * 40, "b" * 40


class Sahte:
    """git/systemctl/pip/chown komutlarını taklit eder; çağrı sırasını kaydeder."""
    def __init__(self, yerel=ESKI, uzak=YENI, soyundan=True, geride=False, degisen=("motor/x.py",), aktif=("1l3a-paper", "1l3a-canli"),
                 duman_rc=0, pip_rc=0, dusen=()):
        self.yerel, self.uzak, self.soyundan, self.geride, self.degisen = yerel, uzak, soyundan, geride, list(degisen)
        self.aktif, self.duman_rc, self.pip_rc, self.dusen = set(aktif), duman_rc, pip_rc, set(dusen)
        self.cagrilar, self.yeniden_baslatildi = [], set()

    def __call__(self, args, cwd=None, env=None, timeout=0):
        a = list(args)
        self.cagrilar.append(a)
        if a[0] == "git":
            g = a[a.index("-C") + 2:]
            if g[0] == "rev-parse":
                return 0, (self.uzak if "refs/remotes" in g[1] else self.yerel) + "\n"
            if g[0] == "merge-base":
                ust, alt = g[2], g[3]                 # --is-ancestor <a> <b>
                if (ust, alt) == (self.uzak, self.yerel):
                    return (0 if self.geride else 1), ""
                return (0 if self.soyundan else 1), ""
            if g[0] == "merge":
                self.yerel = g[2]
                return 0, ""
            if g[0] == "reset":
                self.yerel = g[2]
                return 0, ""
            if g[0] == "diff":
                return 0, "\n".join(self.degisen)
            if g[0] == "log":
                return 0, "\n".join(f"commit {i}" for i in range(15))
            return 0, ""
        if a[0] == "systemctl":
            if a[1] == "is-active":
                s = a[-1]
                return (0 if (s in self.aktif and not (s in self.dusen and s in self.yeniden_baslatildi)) else 3), ""
            if a[1] == "restart":
                self.yeniden_baslatildi.add(a[2])
            return 0, ""
        if a[-2:-1] == ["-c"] or "-c" in a:
            return self.duman_rc, "import hata"
        if a[0].endswith("pip"):
            return self.pip_rc, "pip hata"
        return 0, ""

    def komutlar(self):
        return [" ".join(c[c.index("-C") + 2:]) if c[0] == "git" else " ".join(c[:3]) for c in self.cagrilar]


def ci(durum):
    def http(url):
        assert "check-runs" in url and url.startswith("https://api.github.com/repos/sselimgenc-oss/1L3A-Proje/commits/")
        if durum == "ag":
            return 0, None
        if durum == "bos":
            return 200, {"check_runs": []}
        st, so = ("completed", durum) if durum in ("success", "failure") else ("in_progress", None)
        return 200, {"check_runs": [{"name": "pytest", "status": st, "conclusion": so}, {"name": "baska", "status": "completed", "conclusion": "failure"}]}
    return http


def kur_g(tmp_path, sahte=None, http="success", dal="dal1"):
    sahte = sahte or Sahte()
    mesajlar, uykular = [], []
    ayar = og.Ayar(kok=tmp_path / "kok", dal=dal, durum=tmp_path / "durum", geri_al_dosya=tmp_path / "GERI_AL", systemd=tmp_path / "sd",
                   python="/py", bekleme=60)
    (tmp_path / "sd").mkdir(parents=True, exist_ok=True)
    (tmp_path / "kok" / "deploy").mkdir(parents=True, exist_ok=True)
    g = og.Guncelleyici(ayar, calistir=sahte, http=ci(http), gonder=lambda m: mesajlar.append(m) or True, uyku=uykular.append,
                        simdi=lambda: datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc))
    return g, sahte, mesajlar, uykular


def test_ayni_sha_hicbir_sey(tmp_path):
    g, s, m, _ = kur_g(tmp_path, Sahte(yerel=ESKI, uzak=ESKI))
    assert g.calistir() == "guncel" and m == []
    assert not any(c[0] in ("systemctl", "chown") or "merge" in c and "--ff-only" in c for c in s.cagrilar)


def test_catal_kurmaz_warn_bir_kez(tmp_path):
    g, s, m, _ = kur_g(tmp_path, Sahte(soyundan=False))
    assert g.calistir() == "catal" and g.calistir() == "catal"
    assert len(m) == 1 and "⚠️" in m[0] and not any(c.startswith("merge --ff") for c in s.komutlar())


def test_uzak_geride_sessiz(tmp_path):
    g, s, m, _ = kur_g(tmp_path, Sahte(geride=True))
    assert g.calistir() == "uzak_geride" and m == [] and not any(c.startswith("merge --ff") for c in s.komutlar())


def test_ci_pending_sessiz(tmp_path):
    for durum in ("pending", "bos", "ag"):
        g, s, m, _ = kur_g(tmp_path, http=durum)
        assert g.calistir() == "ci_bekle" and m == []
        assert not any(c.startswith("merge --ff") for c in s.komutlar())


def test_ci_failure_warn_bir_kez(tmp_path):
    g, s, m, _ = kur_g(tmp_path, http="failure")
    assert g.calistir() == "ci_basarisiz" and g.calistir() == "ci_basarisiz"
    assert len(m) == 1 and "⚠️" in m[0]


def test_basarili_sira_ve_info(tmp_path):
    g, s, m, u = kur_g(tmp_path)
    assert g.calistir() == "kuruldu"
    k = s.komutlar()
    mi = next(i for i, c in enumerate(k) if c.startswith("merge --ff-only"))
    ci_ = next(i for i, c in enumerate(k) if i > mi and c.startswith("chown"))
    di = next(i for i, c in enumerate(k) if c.startswith("/py -c"))
    ri = k.index("systemctl restart 1l3a-paper")
    assert mi < ci_ < di < ri
    assert k.index("systemctl restart 1l3a-paper") < k.index("systemctl restart 1l3a-canli")
    assert not any("1l3a-telegram" in c and "restart" in c for c in k)        # aktif değil: atlanır
    assert u == [60]
    assert m == []                                                            # başarılı kurulumda Telegram yok
    gec = [json.loads(x) for x in (tmp_path / "durum" / "gecmis.jsonl").read_text().splitlines()]
    assert gec[-1]["sonuc"] == "kuruldu" and gec[-1]["eski"] == ESKI and gec[-1]["yeni"] == YENI
    assert (tmp_path / "durum" / "son_iyi_sha").read_text().strip() == YENI
    assert oct((tmp_path / "durum").stat().st_mode & 0o777) == "0o755"


def test_duman_hatasi_reset_crit_restart_yok(tmp_path):
    g, s, m, u = kur_g(tmp_path, Sahte(duman_rc=1))
    assert g.calistir() == "basarisiz"
    k = s.komutlar()
    assert s.yerel == ESKI and any(c.startswith("reset --hard " + ESKI) for c in k)
    assert not any(c.startswith("systemctl restart") for c in k) and u == []
    assert len(m) == 1 and "🔴" in m[0]
    assert g.calistir() == "engelli"                                           # aynı sha tekrar denenmez


def test_restart_sonrasi_inactive_geri_al(tmp_path):
    g, s, m, _ = kur_g(tmp_path, Sahte(dusen=("1l3a-canli",)))
    assert g.calistir() == "basarisiz"
    assert s.yerel == ESKI and "🔴" in m[-1]
    k = s.komutlar()
    assert k.count("systemctl restart 1l3a-paper") == 2                        # geri aldıktan sonra yeniden başlatıldı
    assert (tmp_path / "durum" / "son_iyi_sha").exists() is False


def test_requirements_degisince_pip_ve_hata_geri_alir(tmp_path):
    g, s, m, _ = kur_g(tmp_path, Sahte(degisen=("requirements.txt",)))
    assert g.calistir() == "kuruldu" and any(c[0].endswith("pip") and "install" in c for c in s.cagrilar)
    g, s, m, _ = kur_g(tmp_path / "b", Sahte(degisen=("requirements.txt",), pip_rc=1))
    assert g.calistir() == "basarisiz" and s.yerel == ESKI and "🔴" in m[0]
    assert not any(c.startswith("systemctl restart") for c in s.komutlar())


def test_pip_gerekmezse_cagrilmaz(tmp_path):
    g, s, _, _ = kur_g(tmp_path)
    g.calistir()
    assert not any(c[0].endswith("pip") for c in s.cagrilar)


def test_birimler_yalniz_kuruluysa_kopyalanir(tmp_path):
    g, s, _, _ = kur_g(tmp_path, Sahte(degisen=("deploy/1l3a-paper.service", "deploy/1l3a-yeni.service")))
    kok, sd = tmp_path / "kok" / "deploy", tmp_path / "sd"
    (kok / "1l3a-paper.service").write_text("YENI")
    (kok / "1l3a-yeni.service").write_text("YENI")
    (sd / "1l3a-paper.service").write_text("ESKI")
    g.calistir()
    assert (sd / "1l3a-paper.service").read_text() == "YENI" and not (sd / "1l3a-yeni.service").exists()
    assert "systemctl daemon-reload" in " ".join(s.komutlar())


def kurulu_gecmis(g, s):
    assert g.calistir() == "kuruldu"
    s.cagrilar.clear()


def test_geri_al_ve_tekrar_kurulmaz(tmp_path):
    g, s, m, _ = kur_g(tmp_path)
    kurulu_gecmis(g, s)
    assert g.calistir(geri_al=True) == "geri_alindi"
    assert s.yerel == ESKI and any(c.startswith("reset --hard " + ESKI) for c in s.komutlar())
    assert "⚠️" in m[-1]
    s.cagrilar.clear()
    assert g.calistir() == "engelli"                                           # uzak uç hâlâ YENI: kurulmaz
    assert not any(c.startswith("merge --ff") for c in s.komutlar())
    s.uzak = "c" * 40                                                          # yeni commit: yeniden kurulur
    assert g.calistir() == "kuruldu"
    assert g.calistir(geri_al=True) == "geri_alindi" and s.yerel == ESKI


def test_geri_al_kayit_yoksa_uyarir(tmp_path):
    g, s, m, _ = kur_g(tmp_path)
    assert g.calistir(geri_al=True) == "kayit_yok" and "⚠️" in m[0]


def test_geri_al_istek_dosyasi_uygulanir_ve_silinir(tmp_path):
    g, s, m, _ = kur_g(tmp_path)
    kurulu_gecmis(g, s)
    (tmp_path / "GERI_AL").write_text("{}")
    assert g.calistir() == "geri_alindi"
    assert not (tmp_path / "GERI_AL").exists() and s.yerel == ESKI


def test_kilit_varsa_hicbir_sey_yapmaz(tmp_path):
    g, s, m, _ = kur_g(tmp_path)
    (tmp_path / "durum").mkdir()
    with open(tmp_path / "durum" / "kilit", "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert g.calistir() == "kilitli"
    assert s.cagrilar == [] and m == []


# ------------------------------------------------------------------ Telegram /geri_al ve /durum kod satırı
def test_geri_al_komutu_iki_adimli_istek_dosyasi_yazar(tmp_path):
    s, c, _ = kur(tmp_path)
    s.geri_al_dosya = tmp_path / "durum" / "GERI_AL"
    mesaj(s, "/geri_al")
    assert not s.geri_al_dosya.exists() and "Kod: 1234" in son(c)
    mesaj(s, "1111")
    assert not s.geri_al_dosya.exists()                                        # yanlış kod
    mesaj(s, "/geri_al")
    mesaj(s, "1234")
    assert s.geri_al_dosya.exists() and "Geri alma isteği" in son(c)
    mesaj(s, "/geri_al")                                                       # zaten istenmiş
    assert "zaten" in son(c)


def test_geri_al_yetkisiz_chat_yazmaz(tmp_path):
    s, c, _ = kur(tmp_path)
    mesaj(s, "/geri_al", chat=999)
    assert c.giden == [] and not s.geri_al_dosya.exists()


def test_durum_kod_satiri(tmp_path):
    s, c, _ = kur(tmp_path)
    s.sha_fn = lambda: "abc1234"
    s.guncelle = tmp_path / "gnc"
    assert "kod: abc1234, son güncelleme yok" in s.durum_metni()[1]
    s.guncelle.mkdir()
    (s.guncelle / "gecmis.jsonl").write_text(json.dumps({"zaman": "2026-11-19T12:00:00Z", "sonuc": "kuruldu"}) + "\n")
    assert "kod: abc1234, son güncelleme 19.11 15:00 TSİ" in s.durum_metni()[1]


def test_basarili_guncelleme_telegrama_gitmez(tmp_path):
    g, s, m, u = kur_g(tmp_path)
    eski_git = g.git
    g.git = lambda *a, **k: (0, "Telegram özeti sadeleştirildi (iç ayrıntı)\nöncekiler\n") if a[0] == "log" else eski_git(*a, **k)
    assert g.calistir() == "kuruldu"
    assert m == []
    g.mesaj("INFO", "başka bir bilgi")
    assert m == []                                                            # INFO hiçbir yolla gitmez
    g.mesaj("WARN", "Güncelleme kurulmadı.")
    assert len(m) == 1 and "⚠️" in m[0]                                       # uyarı gider


def test_guncelleme_cumlesi_genel_ifadeye_duser():
    from motor.canli.oto_guncelle import guncelleme_cumlesi as c
    assert c("Fix bug in paper_durum.py") == "iyileştirmeler"
    assert c("commit 3") == "iyileştirmeler"
    assert c("x" * 150) == "iyileştirmeler"
    assert c("Kasa formülü düzeltildi (net K/Z, 4f5dd72)") == "Kasa formülü düzeltildi"
