"""1L3A sunucuda otomatik güncelleme (root; systemd zamanlayıcı `1l3a-guncelle.timer`, saatlik). Standart kütüphane + telegram.gonder.

Akış (yalnız İLERİ sarma): git fetch -> uzak uç = yerel HEAD ise çık -> uzak uç yerel HEAD'in torunu değilse KURMAZ (WARN) ->
GitHub genel API'de "testler" iş akışının check-run'ı success değilse kurmaz (pending: sessiz; failure: sha başına bir WARN) ->
git merge --ff-only, chown l3a, requirements değiştiyse pip, duman testi (hata: reset --hard + CRIT, servis yeniden başlatılmaz),
değişen deploy/*.service|*.timer'ın KURULU olanlarını kopyala + daemon-reload, aktif servisleri yeniden başlat, 60 sn sonra hepsi active mi
(değilse geri al + CRIT). Kayıt: /var/lib/1l3a-guncelle/gecmis.jsonl + son_iyi_sha. Kilit: fcntl.
Geri alma: `python -m motor.canli.oto_guncelle --geri-al` ya da /var/lib/1l3a-paper/durum/GERI_AL istek dosyası (Telegram /geri_al yazar;
l3a kullanıcısı root işini yapamaz). Geri alınan (ya da kurulamayan) sha bir daha kurulmaz; bir sonraki YENİ commit'e kadar bekler.
Ortam (isteğe bağlı): L3A_GUNCELLE_KOK, L3A_GUNCELLE_DAL (varsayılan: checkout'taki dal), L3A_GUNCELLE_DIZIN, L3A_GERI_AL_DOSYA.
Tüm dış etkiler (komut, ağ, telegram, uyku) enjekte edilebilir: testler/test_oto_guncelle.py sahte kullanır.
"""
from __future__ import annotations

import fcntl
import html
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("guncelle")
REPO = "sselimgenc-oss/1L3A-Proje"
CI_ISIMLERI = ("testler", "pytest")            # iş akışı adı "testler", iş (job) adı "pytest": check-run adı işin adıdır
SERVISLER = ("1l3a-paper", "1l3a-ct-paper", "1l3a-aday-paper", "1l3a-telegram", "1l3a-canli")
OTOMATIK_KURULACAK = ["1l3a-aday-paper.service"]   # deploy/'da yeni eklenince ilk kez KURULAN birimler (kopyala + enable --now); listede olmayan yeni birim kurulmaz
SYSTEMD = "/etc/systemd/system"
DUMAN = "import motor.canli.paper, motor.canli.telegram_komut, motor.canli.ct_paper, motor.canli.aday_paper, motor.canli.nabiz, motor.canli.borsa.calistir"
BEKLEME_SN = 60
MAKS_MESAJ = 3500
_ISARET = {"WARN": "⚠️ ", "CRIT": "🔴 "}      # seviye kelimesi yok: emoji (INFO sessiz)


def _varsayilan_calistir(args, cwd=None, env=None, timeout=900):
    try:
        e = dict(os.environ)
        e.update(env or {})
        p = subprocess.run(list(args), cwd=cwd, env=e, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr if p.returncode else "")
    except Exception as ex:  # noqa: BLE001
        return 99, f"{type(ex).__name__}: {ex}"


def _varsayilan_http(url: str):
    """-> (durum_kodu, json) ; ağ hatası: (0, None)."""
    try:
        istek = urllib.request.Request(url, headers={"User-Agent": "1l3a-guncelle/1.0", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(istek, timeout=15) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:  # noqa: BLE001
        return 0, None


def _varsayilan_gonder(metin: str) -> bool:
    try:
        from motor.canli.telegram import gonder
        return gonder(metin)
    except Exception as e:  # noqa: BLE001
        log.error("telegram gönderilemedi: %s", type(e).__name__)
        return False


_INGILIZCE = {"fix", "fixes", "bug", "test", "tests", "commit", "refactor", "feat", "merge", "config", "update", "add", "remove", "cleanup", "hotfix",
              "patch", "build", "lint", "debug", "api", "cli", "json", "csv", "html", "pytest", "main", "branch", "pr", "wip", "chore", "docs", "ci"}
GENEL_CUMLE = "iyileştirmeler"
CUMLE_MAKS = 100


def guncelleme_cumlesi(baslik: str) -> str:
    """Son commit başlığından kullanıcıya tek cümle: parantez içi atılır; sha/kod/dosya adı/alt çizgi/İngilizce teknik kelime ya da ~100 karakter
    aşımı varsa genel ifadeye düşer."""
    import re
    t = re.sub(r"\([^)]*\)", "", str(baslik or "").splitlines()[0] if str(baslik or "").strip() else "")
    t = re.sub(r"\s+", " ", t).strip(" .:;-—·")
    if not t or len(t) > CUMLE_MAKS:
        return GENEL_CUMLE
    if "_" in t or re.search(r"[0-9a-f]{7,}|\w\.\w{1,4}\b|[/\\]|→|\d{4}-\d{2}-\d{2}", t, re.I):
        return GENEL_CUMLE
    kelimeler = {w.lower() for w in re.findall(r"[A-Za-z]+", t)}
    if kelimeler & _INGILIZCE or re.search(r"[a-z][A-Z]", t):
        return GENEL_CUMLE
    return t[0].upper() + t[1:]


@dataclass
class Ayar:
    kok: Path = field(default_factory=lambda: Path(os.environ.get("L3A_GUNCELLE_KOK", "/opt/1l3a")))
    dal: Optional[str] = field(default_factory=lambda: os.environ.get("L3A_GUNCELLE_DAL") or None)
    durum: Path = field(default_factory=lambda: Path(os.environ.get("L3A_GUNCELLE_DIZIN", "/var/lib/1l3a-guncelle")))
    geri_al_dosya: Path = field(default_factory=lambda: Path(os.environ.get("L3A_GERI_AL_DOSYA", "/var/lib/1l3a-paper/durum/GERI_AL")))
    systemd: Path = field(default_factory=lambda: Path(SYSTEMD))
    python: str = ""
    bekleme: int = BEKLEME_SN
    servisler: tuple = SERVISLER

    def __post_init__(self):
        self.kok, self.durum, self.geri_al_dosya, self.systemd = Path(self.kok), Path(self.durum), Path(self.geri_al_dosya), Path(self.systemd)
        if not self.python:
            self.python = str(self.kok / ".venv" / "bin" / "python")


class Guncelleyici:
    def __init__(self, ayar: Optional[Ayar] = None, calistir=_varsayilan_calistir, http=_varsayilan_http, gonder=_varsayilan_gonder,
                 uyku=time.sleep, simdi: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.a, self.run, self.http, self._gonder, self.uyku, self.simdi = ayar or Ayar(), calistir, http, gonder, uyku, simdi

    # ------------------------------------------------------------- yardımcılar
    def git(self, *args, timeout=300):
        return self.run(["git", "-c", f"safe.directory={self.a.kok}", "-C", str(self.a.kok), *args], timeout=timeout)

    def mesaj(self, sev: str, metin: str) -> None:
        if sev not in ("WARN", "CRIT"):                    # INFO Telegram'a gitmez, yalnız log
            log.info("telegram (gönderilmedi, bilgi): %s", metin[:200])
            return
        try:
            self._gonder(f"[1L3A] {_ISARET.get(sev, '')}{metin}")
        except Exception as e:  # noqa: BLE001
            log.error("telegram hatası: %s", type(e).__name__)

    def chown(self) -> None:
        self.run(["chown", "-R", "l3a:l3a", str(self.a.kok)])

    def _dosya(self, ad: str) -> Path:
        return self.a.durum / ad

    def gecmis(self) -> list:
        yol, out = self._dosya("gecmis.jsonl"), []
        try:
            for s in yol.read_text(encoding="utf-8").splitlines():
                try:
                    out.append(json.loads(s))
                except ValueError:
                    pass
        except OSError:
            pass
        return out

    def kayit(self, eski: str, yeni: str, sonuc: str, sha: Optional[str] = None) -> None:
        satir = {"zaman": self.simdi().strftime("%Y-%m-%dT%H:%M:%SZ"), "eski": eski, "yeni": yeni, "sonuc": sonuc}
        if sha:
            satir["sha"] = sha
        self.a.durum.mkdir(parents=True, exist_ok=True)
        os.chmod(self.a.durum, 0o755)
        with open(self._dosya("gecmis.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False) + "\n")
        os.chmod(self._dosya("gecmis.jsonl"), 0o644)

    def son_iyi(self, sha: str) -> None:
        self._dosya("son_iyi_sha").write_text(sha + "\n", encoding="utf-8")
        os.chmod(self._dosya("son_iyi_sha"), 0o644)

    def engelli(self) -> set:
        """Bir daha kurulmayacak sha'lar (geri alınan ya da kurulamayan)."""
        return {g.get("sha") for g in self.gecmis() if g.get("sonuc") in ("geri_alindi", "basarisiz") and g.get("sha")}

    def bir_kez(self, anahtar: str) -> bool:
        """True: bu uyarı daha önce verilmemişti (şimdi işaretlendi)."""
        yol = self._dosya("uyari_kayit")
        try:
            var = set(yol.read_text(encoding="utf-8").split())
        except OSError:
            var = set()
        if anahtar in var:
            return False
        self.a.durum.mkdir(parents=True, exist_ok=True)
        with open(yol, "a", encoding="utf-8") as f:
            f.write(anahtar + "\n")
        return True

    def dal(self) -> str:
        if self.a.dal:
            return self.a.dal
        rc, out = self.git("rev-parse", "--abbrev-ref", "HEAD")
        return out.strip() if rc == 0 and out.strip() not in ("", "HEAD") else ""

    # ------------------------------------------------------------- CI
    def ci_durumu(self, sha: str) -> str:
        """-> 'basarili' | 'bekle' | 'basarisiz' (ağ hatası / henüz check-run yok = 'bekle')."""
        kod, veri = self.http(f"https://api.github.com/repos/{REPO}/commits/{sha}/check-runs")
        if kod != 200 or not isinstance(veri, dict):
            return "bekle"
        kosular = [c for c in veri.get("check_runs", []) if c.get("name") in CI_ISIMLERI]
        if not kosular or any(c.get("status") != "completed" for c in kosular):
            return "bekle"
        return "basarili" if all(c.get("conclusion") == "success" for c in kosular) else "basarisiz"

    # ------------------------------------------------------------- kurulum adımları
    def degisenler(self, a: str, b: str) -> list:
        rc, out = self.git("diff", "--name-only", a, b)
        return out.split() if rc == 0 else []

    def pip(self, degisen: list) -> bool:
        if "requirements.txt" not in degisen:
            return True
        rc, out = self.run([str(self.a.kok / ".venv" / "bin" / "pip"), "install", "-r", str(self.a.kok / "requirements.txt")], cwd=str(self.a.kok), timeout=1800)
        if rc != 0:
            log.error("pip hatası: %s", out[-300:])
        return rc == 0

    def duman(self) -> bool:
        rc, out = self.run([self.a.python, "-c", DUMAN], cwd=str(self.a.kok), env={"PYTHONDONTWRITEBYTECODE": "1"}, timeout=120)
        if rc != 0:
            log.error("duman testi hatası: %s", out[-300:])
        return rc == 0

    def birimleri_guncelle(self, degisen: list) -> list:
        """Değişen deploy/*.service|*.timer içinden /etc/systemd/system'de KURULU olanları kopyalar; yeni birim YALNIZ OTOMATIK_KURULACAK listesindeyse
        kurulur (kopyala + enable --now); diğer yeni birimler kurulmaz. daemon-reload."""
        kopyalanan, yeniler = [], []
        for f in degisen:
            p = Path(f)
            if p.parent.as_posix() == "deploy" and p.suffix in (".service", ".timer", ".path"):
                hedef = self.a.systemd / p.name
                if hedef.exists():
                    shutil.copyfile(self.a.kok / f, hedef)
                    kopyalanan.append(p.name)
                elif p.name in OTOMATIK_KURULACAK and (self.a.kok / f).exists():
                    shutil.copyfile(self.a.kok / f, hedef)
                    kopyalanan.append(p.name)
                    yeniler.append(p.name)
        if kopyalanan:
            self.run(["systemctl", "daemon-reload"])
        for ad in yeniler:
            rc, out = self.run(["systemctl", "enable", "--now", ad])
            if rc != 0:
                log.error("%s kurulamadı (enable --now): %s", ad, out[-200:])
                self.mesaj("WARN", f"Yeni bir servis kuruldu ama başlatılamadı. Senden: sunucuyu kontrol et.")
        return kopyalanan

    def aktifler(self) -> list:
        return [s for s in self.a.servisler if self.run(["systemctl", "is-active", "--quiet", s])[0] == 0]

    def yeniden_baslat(self, liste: list) -> None:
        for s in liste:
            self.run(["systemctl", "restart", s])

    def hepsi_aktif(self, liste: list) -> list:
        return [s for s in liste if self.run(["systemctl", "is-active", "--quiet", s])[0] != 0]

    def geri_sar(self, hedef: str) -> bool:
        rc, _ = self.git("reset", "--hard", hedef)
        self.chown()
        return rc == 0

    # ------------------------------------------------------------- güncelleme
    def guncelle(self) -> str:
        dal = self.dal()
        if not dal:
            self.mesaj("WARN", "Otomatik güncelleme yapılamadı (kod dalı belirlenemedi). Güncelleme kurulmadı. Senden: sunucuyu kontrol et.")
            return "dal_yok"
        rc, out = self.git("fetch", "origin", f"+refs/heads/{dal}:refs/remotes/origin/{dal}")
        if rc != 0:
            log.warning("git fetch başarısız: %s", out[-200:])
            return "fetch_hata"
        rc1, yerel = self.git("rev-parse", "HEAD")
        rc2, uzak = self.git("rev-parse", f"refs/remotes/origin/{dal}")
        yerel, uzak = yerel.strip(), uzak.strip()
        if rc1 != 0 or rc2 != 0:
            return "sha_hata"
        if uzak == yerel:
            return "guncel"
        self.chown()                                           # fetch root nesneleri yazmış olabilir
        if self.git("merge-base", "--is-ancestor", uzak, yerel)[0] == 0:
            return "uzak_geride"                               # yerel ileride (örn. geri alma sonrası): sessiz
        if self.git("merge-base", "--is-ancestor", yerel, uzak)[0] != 0:
            if self.bir_kez(f"catal:{uzak}"):
                self.mesaj("WARN", f"Otomatik güncelleme: yeni kod mevcut kodun devamı değil. Güncelleme kurulmadı. Senden: kodu kontrol et.")
            return "catal"
        if uzak in self.engelli():
            return "engelli"
        ci = self.ci_durumu(uzak)
        if ci == "bekle":
            return "ci_bekle"
        if ci == "basarisiz":
            if self.bir_kez(f"ci:{uzak}"):
                self.mesaj("WARN", f"Otomatik güncelleme: yeni kodun testleri başarısız. Güncelleme kurulmadı, eski kod çalışıyor. Senden bir şey gerekmiyor.")
            return "ci_basarisiz"
        return self.kur(yerel, uzak)

    def kur(self, eski: str, yeni: str) -> str:
        rc, out = self.git("merge", "--ff-only", yeni)
        if rc != 0:
            self.mesaj("WARN", f"Otomatik güncelleme: yeni kod birleştirilemedi. Güncelleme kurulmadı. Senden: kodu kontrol et.")
            return "ff_hata"
        self.chown()
        degisen = self.degisenler(eski, yeni)

        def basarisiz(neden: str, yeniden: bool = False) -> str:
            self.geri_sar(eski)
            if yeniden:
                self.yeniden_baslat(self.aktifler())
            self.kayit(eski, yeni, "basarisiz", sha=yeni)
            log.error("güncelleme geri alındı (%s←%s): %s", eski[:7], yeni[:7], neden)
            self.mesaj("CRIT", f"Güncelleme geri alındı, eski kod çalışıyor. Senden bir şey gerekmiyor (ayrıntı kayıtta).")
            return "basarisiz"

        if not self.pip(degisen):
            return basarisiz("pip install başarısız")
        if not self.duman():
            return basarisiz("duman testi (import) başarısız; servisler yeniden başlatılmadı")
        self.birimleri_guncelle(degisen)
        liste = self.aktifler()
        self.yeniden_baslat(liste)
        self.uyku(self.a.bekleme)
        dusen = self.hepsi_aktif(liste)
        if dusen:
            return basarisiz("yeniden başlatma sonrası aktif değil: " + ", ".join(dusen), yeniden=True)
        self.kayit(eski, yeni, "kuruldu")
        self.son_iyi(yeni)
        _, basliklar = self.git("log", "--format=%s", f"{eski}..{yeni}")
        satirlar = [html.escape(x, quote=False) for x in basliklar.splitlines()[:10]]
        govde = f"Güncelleme kuruldu: {eski[:7]}→{yeni[:7]}\n" + "\n".join(satirlar)
        log.info("güncelleme kuruldu: %s", govde[:MAKS_MESAJ - 20].replace("\n", " | "))
        # başarılı kurulumda Telegram yok (kullanıcı kararı 2026-11-20): yalnız log; hata/geri alma uyarıları gider
        log.info("Bot güncellendi: %s", guncelleme_cumlesi(basliklar.splitlines()[0] if basliklar.strip() else ""))
        return "kuruldu"

    # ------------------------------------------------------------- geri alma
    def geri_al(self) -> str:
        yigin = []
        for g in self.gecmis():
            if g.get("sonuc") == "kuruldu":
                yigin.append(g)
            elif g.get("sonuc") == "geri_alindi" and yigin:
                yigin.pop()
        if not yigin:
            self.mesaj("WARN", "Geri alınacak güncelleme yok. Senden bir şey gerekmiyor.")
            return "kayit_yok"
        hedef = yigin[-1]["eski"]
        rc, mevcut = self.git("rev-parse", "HEAD")
        mevcut = mevcut.strip()
        if mevcut == hedef:
            return "zaten"
        if not self.geri_sar(hedef):
            self.mesaj("CRIT", f"Geri alma başarısız. Senden: sunucuyu kontrol et.")
            return "hata"
        degisen = self.degisenler(hedef, mevcut)
        pip_ok = self.pip(degisen)
        self.birimleri_guncelle(degisen)
        self.yeniden_baslat(self.aktifler())
        self.kayit(mevcut, hedef, "geri_alindi", sha=mevcut)
        self.son_iyi(hedef)
        self.mesaj("WARN" if pip_ok else "CRIT",
                   "Güncelleme geri alındı; o sürüm bir daha kurulmaz, otomatik güncelleme yeni sürümle sürer."
                   + ("" if pip_ok else " Senden: bağımlılıkları kontrol et."))
        return "geri_alindi"

    # ------------------------------------------------------------- giriş
    def calistir(self, geri_al: bool = False) -> str:
        self.a.durum.mkdir(parents=True, exist_ok=True)
        os.chmod(self.a.durum, 0o755)
        kilit = open(self._dosya("kilit"), "a+")
        try:
            try:
                fcntl.flock(kilit, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                log.info("başka bir güncelleme çalışıyor; çıkılıyor")
                return "kilitli"
            istek = self.a.geri_al_dosya
            if istek.exists():
                try:
                    istek.unlink()
                except OSError:
                    pass
                geri_al = True
            if geri_al:
                return self.geri_al()
            return self.guncelle()
        finally:
            kilit.close()


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="1L3A otomatik güncelleme (root)")
    ap.add_argument("--geri-al", action="store_true", help="son başarılı güncellemeden önceki sürüme dön")
    a = ap.parse_args(argv)
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        sonuc = Guncelleyici().calistir(geri_al=a.geri_al)
    except Exception as e:  # noqa: BLE001
        log.exception("güncelleme hatası")
        _varsayilan_gonder(f"[1L3A] ⚠️ Otomatik güncelleme hata verdi. Senden: sunucuyu kontrol et.")
        return 1
    log.info("sonuç: %s", sonuc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
