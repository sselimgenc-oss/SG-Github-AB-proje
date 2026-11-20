"""Paper trading (Aşama 4): canlı Binance herkese açık verisiyle, SANAL emirlerle.

VARSAYILAN SET = v2 (2026-11-10): 10 strateji, HER BİRİ KENDİ 10.000 USD sanal kasasında (motor/canli/paper_v2.py,
stratejiler/paper_v2_seti.json). Aşağıdaki "final set (7 strateji, tek hesap)" yolu `--set eski` ile hâlâ çalışır (yalnız geriye
uyumluluk; eski durum dosyasıyla v2 seti karıştırılmaz: v2, eski kaydı açık hatayla reddeder).
Eski (7 strateji) açıklama:

Gerçek emir YOK, API anahtarı YOK (yalnız herkese açık REST/WS). Limitler UYGULANIR: işlem başı %1 (grup özsermayesinde),
toplam stop riski %5, 3x, günlük -%3 (o gün yeni işlem yok + açıklar kapanır), kill %20 (her şey durur). İki kol (tek-grafik +
portföy) TEK hesapta ortak limit kontrolünden geçer (bkz. paper_motor.py).

Bu dosya: orkestrasyon (`Paper`), tekrar modu, CLI. Canlı veri: paper_canli.py. Durum yazımı: paper_durum.py.

CLI
  python -m motor.canli.paper --canli [--durum durum] [--ayar-guncelle]     # servis (systemd)
  python -m motor.canli.paper --tekrar BAS [BIT] [--ayar kilit|guncel]     # geçmişi canlıymış gibi besler (yerel veri)
  python -m motor.canli.paper --tek-sefer                                    # bir tur çalış, durum yaz, çık
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import time
import traceback
from decimal import Decimal
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from motor.backtest.motor import SembolKurallari
from motor.canli import kalp_atisi as kh
from motor.canli import karantina as kq
from motor.canli import paper_sinyal as psg
from motor.canli.durum_ek import kapanis_gunu as tsi_kapanis_gunu
from motor.canli.paper_kaynak import TekrarKaynagi
from motor.canli.paper_motor import Birim, PaperMotor, _dec, _enc
from motor.portfoy.motor import PortfoyAyarlari

log = logging.getLogger("paper")


def _kisalt(x, n: int = 80) -> str:
    t = str(x)
    return t if len(t) <= n else t[:n - 1] + "…"


def d_zaman(t) -> str:
    from motor.canli.durum import zaman_str
    return zaman_str(pd.Timestamp(t))
KOK = Path(__file__).resolve().parents[2]
SURUM = 1
BASLANGIC_SERMAYE = 10000.0
PENCERE = {"5m": 4000, "15m": 3000, "30m": 6000, "1h": 3000, "4h": 3000, "1d": 1500}      # canlıda son N bar (tekrar: None)


def paper_ayarlari(baslangic_sermaye: float = BASLANGIC_SERMAYE) -> PortfoyAyarlari:
    """Backtest maliyet modeli (varsayılanlar: taker %0.05, maker %0.02, kayma 2 bps, stop kayması 5 bps) + limitler UYGULANIR."""
    return PortfoyAyarlari(baslangic_sermaye=baslangic_sermaye, limit_modu="uygula")


class Paper:
    def __init__(self, tanimlar: list, kaynak: TekrarKaynagi, kurallar: dict, ayarlar: Optional[PortfoyAyarlari] = None,
                 durum_yolu: Optional[Path] = None, her_satir_kaydet: bool = False, islem_baslangic=None,
                 pf_sutunlar: Optional[dict] = None, tetikleyen_hemen_kapat: bool = True):
        self.tanimlar = [t for t in tanimlar if not t.veri_yok]
        self.veri_yok = [t for t in tanimlar if t.veri_yok]
        self.kaynak = kaynak
        self.ayarlar = ayarlar or paper_ayarlari()
        self.motor = PaperMotor(self.ayarlar, kurallar, tetikleyen_hemen_kapat)
        self.durum_yolu = Path(durum_yolu) if durum_yolu else None
        self.her_satir_kaydet = her_satir_kaydet
        self.pf_sutunlar = dict(pf_sutunlar or {})
        self.tanim_ad = {t.kimlik: t for t in self.tanimlar}
        self.birimler: list[Birim] = []
        self.baslatildi = False
        self.satir_sayisi = 0
        self.uyarilar: list = []                 # veri/motor uyarıları (saglik.json'a gider)
        self.olaylar: list = []                  # {zaman, tur, mesaj}; son 50'si olaylar.jsonl'e yazılır
        self.strateji_gun: dict = {}             # {kimlik: {"YYYY-MM-DD" (UTC günü): gün sonu kümülatif net K/Z (Decimal)}} (beklenti tabanı)
        self.strateji_gun_tsi: dict = {}         # aynısı TSİ günü kesimiyle (pano dönemsel getiri)
        self.bildirim = None                     # callback(tur, mesaj) (Telegram vb.); None: yok
        self._limit_gorulen = 0
        self._askida_kap_gorulen = 0
        self._son_gec = 0
        self.kayit = None                        # yalnız kayıt (kayit_ac)
        self.ayar_oto_kabul = False              # True: kayıtlı ayar guncel_ayarlar.csv'den farklıysa onay beklemeden yeni ayar kabul (yalnız PAPER servisi; canlıda False)
        self.ayar_degisenler: list = []          # oto-kabul edilenler: [(kimlik, eski, yeni)] (Telegram tek INFO için canli_calistir toplar)
        self.karar_onbellek: Optional[dict] = None   # tekrar modu hızlandırması (tek_evren): {(kol_kimligi, t): karar}; canlıda None
        # kalp atışı (kalp_atisi.py): düzenli zaman damgası; yeniden başlatmadaki kesinti süresi bundan ölçülür
        self.kalp_atisi: Optional[str] = None     # son kalp atışı (UTC ISO); paper_state.json'a da yazılır
        self.baslangic_zamani: Optional[str] = None
        self.onceki_kalp: Optional[str] = None    # bu süreç başlarken bulunan önceki kalp atışı
        self.son_kesinti: Optional[dict] = None   # bu süreç başlarken ölçülen kesinti (kalp_atisi.kesinti)
        self._kalp_yazilan = None
        self._askida_kayit: dict = {"ayarlar": {}, "pf_sutunlar": {}}   # kayıtta olup şimdi çalışmayan stratejilerin ayar/sütunları (geri yazılır)
        self.son_ozet: Optional[str] = None       # günlük Telegram özeti (21:00 TSİ) gönderilen son TSİ günü ("YYYY-MM-DD"; paper_state'e yazılır)
        self.son_haftalik: Optional[str] = None   # haftalık Telegram özeti (Pazar 21:10 TSİ) gönderilen son TSİ günü
        # kod hatası karantinası (motor/canli/karantina.py): {kimlik: {"zaman","sha","hata","durum": "aktif"|"deneme"}}; paper_state.json'da kalıcı
        self.karantina: dict = {}
        self.karantina_bildirim: dict = {}        # {kimlik: son CRIT bildirim epoch sn}: aynı strateji için en çok 6 saatte bir (kalıcı)
        self.saat = time.time                      # test için değiştirilebilir
        self.kod_sha_fn = kq.kod_sha
        for s in {x for t in self.tanimlar for x in t.veri_semboller}:
            if s not in kurallar:
                raise KeyError(f"{s}: sembol kuralı (tick/step/minNotional) yok")
            self.motor.sembol_ekle(s, kurallar[s])
        self._birimleri_kur()

    # ------------------------------------------------------------------ kurulum
    def _birimleri_kur(self):
        for t in self.tanimlar:
            if t.kol == "portfoy" and t.kimlik not in self.pf_sutunlar:
                continue                         # sütunlar ilk kararda (baslat) keşfedilir
            self._birim_ekle(t)

    def _birim_ekle(self, t):
        b = psg.birim_kur(t, self.pf_sutunlar.get(t.kimlik))
        self.motor.birim_ekle(b)
        self.birimler.append(b)

    def _mumlar_t(self, b: Birim, t) -> dict:
        return {s: self.kaynak.gecmis(s, b.tf, t) for s in b.semboller}

    def _motor_besle(self, b: Birim):
        for s in b.semboller:
            self.motor.fiyat_serisi(s, *self.kaynak.fiyat_dizisi(s))
            self.motor.funding_serisi(s, *self.kaynak.funding_dizisi(s))

    def _karar(self, b: Birim, t, mumlar: Optional[dict] = None) -> dict:
        td = self.tanim_ad[b.ad]
        if td.kol == "tek_grafik":
            m = self.kaynak.gecmis(td.sembol, td.tf, t)
            return psg.tek_karar(td, m, self.kaynak.funding_df(td.sembol))
        if td.kol == "tek_evren":
            if mumlar is None:
                raise RuntimeError(f"{b.ad}: tek_evren kararı için satır mumları gerekli")
            return psg.evren_karar(td, t, mumlar, lambda s: self.kaynak.gecmis(s, td.tf, t), self.kaynak.funding_df, self.karar_onbellek)
        k, _, son = psg.pf_karar(td, self._mumlar_t(b, t))
        if son != t:
            raise RuntimeError(f"{b.ad}: portföy ekseni son satırı {son} != işlenen satır {t}")
        return k

    # ------------------------------------------------------------------ kod hatası karantinası
    def _karantina_ad(self, kid: str) -> str:
        """Bildirimde strateji adı; gizli hesabın adı ASLA yazılmaz."""
        return kid if getattr(self, "gorunur", True) else f"{kq.GIZLI_AD} (1)"

    def _karantina_esitle(self) -> None:
        self.motor.karantina = {k for k, r in self.karantina.items() if r.get("durum") == "aktif"}

    def _karar_guvenli(self, b: Birim, t, mumlar: Optional[dict] = None) -> dict:
        """`_karar` + kod hatası izolasyonu. Karantinadaki birimde strateji kodu ÇAĞRILMAZ ({}; motor `_karantina_yonet`). YALNIZ programlama hatası
        (KOD_HATALARI) ve ValueError (STRATEJI_HATALARI) karantinaya alır; ağ/veri geçici hatası (GECICI_HATALAR) eski yolunda yükselir (TurKoruyucu)."""
        kid = b.ad
        r = self.karantina.get(kid)
        if r is not None and r.get("durum") == "aktif":
            return {}
        try:
            k = self._karar(b, t, mumlar)
        except Exception as e:  # noqa: BLE001
            self._karantinaya_al_ya_da_yukselt(kid, e)
            return {}
        if r is not None:                         # yeniden deneme (kod güncellendi / elle kaldırıldı): ilk başarılı karar = düzeldi
            self._karantina_duzeldi(kid)
        return k

    def _karantinaya_al_ya_da_yukselt(self, kid: str, e: BaseException) -> None:
        """Kod hatası kontrolünün TEK yeri: kod hatası + ValueError -> karantinaya al; ağ/veri geçici hatası eski yolda yükselir."""
        from motor.canli.paper_veri import strateji_hatasi_mi
        if not strateji_hatasi_mi(e):
            raise e
        self._karantinaya_al(kid, e)

    def _karantinaya_al(self, kid: str, e: BaseException) -> None:
        log.error("strateji kodu hata verdi, karantinaya alındı: %s", kid, exc_info=e)
        hata = f"{type(e).__name__}: {str(e)[:200]}"
        self.karantina[kid] = {"zaman": d_zaman(pd.Timestamp.now(tz="UTC")), "sha": self.kod_sha_fn(), "hata": hata, "durum": "aktif"}
        self._karantina_esitle()
        simdi = self.saat()
        son = self.karantina_bildirim.get(kid)
        gonder = son is None or simdi - son >= kq.BILDIRIM_ARALIK_SN        # ilk mesaj anında; sonrakiler 6 saatte bir (CRIT bile)
        if gonder:
            self.karantina_bildirim[kid] = simdi
        ad = kid if getattr(self, "gorunur", True) else "Diğer hesap"     # gizli hesap adı ASLA yazılmaz
        bm = f"{ad} stratejisi hata verdi, yeni işlem açmıyor; açık pozisyonlar stop/hedefle sürüyor"
        self.olay_ekle("karantina", f"{bm}: {hata}", None, bildir=gonder, bildirim_mesaji=bm)

    def _karantina_duzeldi(self, kid: str) -> None:
        self.karantina.pop(kid, None)
        self._karantina_esitle()
        bm = f"{self._karantina_ad(kid)} düzeldi, karantinadan çıktı"
        self.olay_ekle("karantina_cikis", bm, None, bildir=True, bildirim_mesaji=bm)

    def karantina_kaldir(self, kid: str, neden: str) -> bool:
        """Karantinayı kaldırır: strateji YENİDEN ÇALIŞIR ('deneme'); ilk başarılı karardan sonra INFO 'düzeldi'; yine hata verirse yeniden karantina."""
        r = self.karantina.get(kid)
        if r is None or r.get("durum") != "aktif":
            return False
        r["durum"] = "deneme"
        self._karantina_esitle()
        self.olay_ekle("karantina_kaldirildi", f"{kid}: {neden}", None, bildir=False)
        return True

    def karantina_sha_kontrol(self) -> None:
        """Kod SHA'sı kayıttakinden farklıysa (oto_guncelle yeni sürümle servisi yeniden başlattı) karantinadaki strateji BİR KEZ yeniden denenir."""
        sha = self.kod_sha_fn()
        if not sha:
            return
        for kid, r in list(self.karantina.items()):
            if r.get("durum") == "aktif" and r.get("sha") != sha:
                self.karantina_kaldir(kid, f"kod SHA değişti ({r.get('sha')} -> {sha}); yeniden denenecek")

    def karantina_anlik(self):
        return copy.deepcopy((self.karantina, self.karantina_bildirim))

    def karantina_geri(self, a) -> None:
        self.karantina, self.karantina_bildirim = copy.deepcopy(a)
        self._karantina_esitle()

    def karantina_ozeti(self) -> dict:
        """saglik.json `karantina`: {'gorunur': [kimlik...], 'gizli': N}. Gizli hesap adı yok."""
        akt = [k for k, r in self.karantina.items() if r.get("durum") == "aktif"]
        if getattr(self, "gorunur", True):
            return {"gorunur": sorted(akt), "gizli": 0}
        return {"gorunur": [], "gizli": len(akt)}

    def baslat(self, simdi):
        """İlk çalıştırma: her birim için kapanmış son barın kararları (bekleyen emirler) kurulur; dolum yok."""
        simdi = pd.Timestamp(simdi)
        for t in self.tanimlar:
            if t.kol == "portfoy" and t.kimlik not in self.pf_sutunlar:
                sr = self.kaynak.son_satir(Birim(t.kimlik, t.tf, pd.Timedelta(t.tf.replace("d", "D")) if t.tf.endswith("d")
                                                 else pd.Timedelta(t.tf), [], list(t.evren)), simdi)
                if sr is None:
                    raise RuntimeError(f"{t.kimlik}: başlangıç için kapanmış mum yok")
                _, sutun, _ = psg.pf_karar(t, self._mumlar_t(Birim(t.kimlik, t.tf, pd.Timedelta(0), [], list(t.evren)), sr[0]))
                self.pf_sutunlar[t.kimlik] = sutun
                self._birim_ekle(t)
        for b in self.birimler:
            sr = self.kaynak.son_satir(b, simdi)
            if sr is None:
                raise RuntimeError(f"{b.ad}: başlangıç için kapanmış mum yok")
            t, mumlar = sr
            if self.tanim_ad[b.ad].kol == "tek_evren":
                self._evren_baslat(b, self.tanim_ad[b.ad], simdi, t)
                continue
            self._motor_besle(b)
            self.motor.ilk_karar(b, t, mumlar, self._karar_guvenli(b, t, mumlar))
            b.son_t = t
        self.baslatildi = True

    def _evren_baslat(self, b: Birim, td, simdi, t) -> None:
        """tek_evren başlangıcı: her sembol KENDİ son kapanmış barının kararıyla başlar (ortak eksenin son satırında mumu olmayan
        sembol - ör. hafta sonu satırında hisse - Cuma kararını kaybetmesin). Dolum yok; bekleyen emirler kurulur."""
        mumlar, kararlar = {}, {}
        for s in b.semboller:
            sr = self.kaynak.son_satir(Birim(f"{b.ad}#{s}", b.tf, b.aralik, [], [s]), simdi)
            if sr is None:
                mumlar[s] = None
                continue
            ts, satir = sr
            mumlar[s] = satir[s]
            if b.ad in self.motor.karantina:
                continue
            try:
                kararlar.update(psg.evren_karar(td, ts, {s: satir[s]}, lambda x, ts=ts: self.kaynak.gecmis(x, td.tf, ts),
                                                self.kaynak.funding_df, self.karar_onbellek))
            except Exception as e:  # noqa: BLE001
                self._karantinaya_al_ya_da_yukselt(b.ad, e)
                kararlar = {}
        self._motor_besle(b)
        self.motor.ilk_karar(b, t, mumlar, kararlar)
        b.son_t = t

    # ------------------------------------------------------------------ işleme
    def isle(self, b: Birim, t, mumlar: dict, son_satir: bool = False):
        self._motor_besle(b)
        self.motor.acilis_fazi(b, t, mumlar)
        self.motor.kapanis_fazi(b, t, lambda: self._karar_guvenli(b, t, mumlar), son_satir)
        b.son_t = t
        self.satir_sayisi += 1
        self._satir_sonrasi(b, t)
        if self.her_satir_kaydet and self.durum_yolu:
            self.kaydet()

    # ------------------------------------------------------------------ yalnız kayıt (kayit_etiketleri.py)
    def kayit_ac(self, kayit) -> None:
        """Alınmayan sinyal + işlem etiketi kayıtlarını açar (varsayılan kapalı). Karar/emir/boyut/risk yoluna girmez."""
        self.kayit = kayit
        self.motor.kayit_kancasi = self._alinmadi_kaydet
        self.motor.etiket_kancasi = self._etiket_uret

    def _etiket_uret(self, t, kol) -> dict:
        return self.kayit.etiketler(kol.sembol, t, self.kaynak.funding_df(kol.sembol))

    def _alinmadi_kaydet(self, t, kol, yon, neden, fiyat, stop, hedef) -> None:
        td = self.tanim_ad.get(kol.birim)
        e = self.motor._emir_ctx.get(kol.kimlik)
        zc = getattr(e, "zc", None)
        f = lambda x: None if x is None or x != x else str(x)
        satir = {"zaman": d_zaman(t), "hesap": getattr(self, "kimlik", "paper"), "strateji": kol.sk or kol.strateji_ad, "kol": kol.kimlik,
                 "sembol": kol.sembol, "tf": td.tf if td is not None else None, "yon": "long" if yon == 1 else "short",
                 "fiyat": f(fiyat), "stop": f(stop), "hedef": f(hedef), "zaman_cikisi_mum": None if zc is None or zc != zc else int(zc), "neden": neden}
        satir.update(self.kayit.etiketler(kol.sembol, t, self.kaynak.funding_df(kol.sembol)))
        self.kayit.alinmadi(satir)

    # ------------------------------------------------------------------ kalp atışı
    def kalp_at(self, simdi, dizin: Optional[Path] = None, zorla: bool = False, durdu: bool = False) -> None:
        """Kalp atışını günceller (bellek + paper_state) ve en çok `kh.KALP_SN`'de bir `kalp_atisi.json`'a yazar. `simdi`: sunucu zamanı (UTC)."""
        simdi = pd.Timestamp(simdi)
        self.kalp_atisi = d_zaman(simdi)
        if dizin is not None and (zorla or durdu or self._kalp_yazilan is None
                                  or (simdi - self._kalp_yazilan).total_seconds() >= kh.KALP_SN):
            kh.yaz(dizin, simdi, self.baslangic_zamani or self.kalp_atisi, self.onceki_kalp, durdu)
            self._kalp_yazilan = simdi

    def surec_basla(self, simdi, dizin: Path, yuklendi: bool) -> None:
        """Servis başlangıcı: ÖNCEKİ kalp atışını (dosya ve paper_state'in yenisi) okur; yeniden başlatmaysa "son kalp atışı -> başlangıç"
        kesintisini süresiyle `yeniden_baslatma` olayına yazar; sonra yeni kalp atışını yazar. İlk çalışmada kesinti yoktur."""
        from motor.canli import durum as dr
        self.baslangic_zamani = d_zaman(simdi)
        if yuklendi:
            try:
                kd, hata = kh.oku(dizin), None
            except dr.DurumHatasi as e:
                kd, hata = None, str(e).replace("(", "[").replace(")", "]")
            k = kh.kesinti(kh.en_yeni(self.kalp_atisi, kd["zaman"] if kd else None), simdi)
            self.son_kesinti, self.onceki_kalp = k, k["onceki"]
            self.olay_ekle("yeniden_baslatma", kh.olay_mesaji(k) + (f"; kalp atışı dosyası okunamadı: {hata}" if hata else ""), simdi)
        self.kalp_at(simdi, dizin, zorla=True)

    def kalp_bilgisi(self) -> Optional[dict]:
        """saglik.json `kalp_atisi` bloğu (pano yalnız biçimler). Kalp atışı hiç atılmadıysa (tekrar modu) None."""
        if self.kalp_atisi is None:
            return None
        k = self.son_kesinti
        return {"son": self.kalp_atisi, "baslangic": self.baslangic_zamani, "aralik_sn": kh.KALP_SN,
                "onceki_kalp_atisi": self.onceki_kalp, "son_kesinti_sn": (k or {}).get("sn"),
                "son_kesinti_neden": (k or {}).get("neden") if k else "bu süreç ilk çalışmada başladı (yeniden başlatma yok)"}

    def olay_ekle(self, tur: str, mesaj: str, zaman=None, bildir: bool = True, bildirim_mesaji: Optional[str] = None):
        z = d_zaman(zaman if zaman is not None else self.motor.son_zaman or pd.Timestamp.now(tz="UTC"))
        self.olaylar.append({"zaman": z, "tur": tur, "mesaj": mesaj})
        self.olaylar = self.olaylar[-200:]
        log.info("olay %s: %s", tur, mesaj)
        if bildir and self.bildirim:
            self.bildirim(tur, bildirim_mesaji or mesaj)

    def _satir_sonrasi(self, b: Birim, t):
        from motor.canli.paper_durum import strateji_pnl
        m = self.motor
        gun = str(m.gun)
        tsi_gun = tsi_kapanis_gunu(t + b.aralik)
        for td in self.tanimlar:
            toplam = strateji_pnl(self, td.kimlik)["toplam"]
            self.strateji_gun.setdefault(td.kimlik, {})[gun] = toplam
            self.strateji_gun_tsi.setdefault(td.kimlik, {})[tsi_gun] = toplam
        for o in m.limit_olaylari[self._limit_gorulen:]:
            if o["tur"] == "kill_switch":
                self.olay_ekle("kill_switch", f"KILL SWITCH: zirveden düşüş %{o['dusus_yuzde']:.2f}; tüm işlemler durdu", o["zaman"])
            else:
                self.olay_ekle("gunluk_limit", f"Günlük kayıp limiti: gün başından %{o['dusus_yuzde']:.2f} kayıp; açıklar kapanıyor, "
                                              f"bugün yeni işlem yok", o["zaman"])
        self._limit_gorulen = len(m.limit_olaylari)
        for x in m.askida_kapanislar[self._askida_kap_gorulen:]:         # B11: askıdaki pozisyon limitte son bilinen fiyattan kapandı: ayrı alarm
            self.olay_ekle("askida_kapatma", f"{x['kol']} ({x['sembol']}) askıda açık pozisyon {x['cikis_nedeni']} ile {x['cikis_fiyati']:.6g}'dan kapatıldı "
                                             f"(fiyat kaynağı: {x['fiyat_kaynagi']}); net K/Z {x['net_pnl']:+.2f} USD", x["zaman"])
        self._askida_kap_gorulen = len(m.askida_kapanislar)

    def bekleyen(self, simdi) -> list:
        """İşlenecek (kapanış, birim sırası, t, mumlar) satırları, kapanış zamanına göre."""
        rows = []
        for bi, b in enumerate(self.birimler):
            for t, mumlar in self.kaynak.satirlar(b, b.son_t, simdi):
                rows.append((t + b.aralik, bi, t, mumlar))
        rows.sort(key=lambda r: (r[0], r[1]))
        return rows

    def _gec_barlari_isle(self) -> int:
        """Satırı zaman aşımıyla mumsuz işlenmiş sembolün mumu sonradan geldiyse o barın stop/hedef kontrolü yapılır (B07) ve olay yazılır."""
        n = 0
        for b in self.birimler:
            for t, s, mum in self.kaynak.gec_barlar(b):
                ol = self.motor.gec_bar_isle(b, t, s, mum)
                n += 1
                self.olay_ekle("gec_bar", f"{b.ad} {t}: {s} {b.tf} mumu bekleme süresinden sonra geldi; kaçırılan stop/hedef kontrolü yapıldı -> {ol['sonuc']}", t)
        return n

    def adim(self, simdi, son_satir_bayragi: bool = False) -> int:
        """Kapanmış tüm bekleyen satırları kronolojik işler. -> işlenen satır sayısı."""
        if not self.baslatildi:
            raise RuntimeError("önce baslat(simdi) ya da yukle()")
        self._son_gec = self._gec_barlari_isle()
        rows = self.bekleyen(simdi)
        for k, (kap, bi, t, mumlar) in enumerate(rows):
            b = self.birimler[bi]
            son = son_satir_bayragi and not any(r[1] == bi for r in rows[k + 1:])
            self.isle(b, t, mumlar, son_satir=son)
        return len(rows)

    # ------------------------------------------------------------------ kalıcılık
    def durum_sozlugu(self) -> dict:
        return {"surum": SURUM, "baslangic_sermaye": self.ayarlar.baslangic_sermaye,
                "ayarlar": {**self._askida_kayit["ayarlar"], **{t.kimlik: t.ayar for t in self.tanimlar}},
                "pf_sutunlar": {**self._askida_kayit["pf_sutunlar"], **self.pf_sutunlar},
                "satir_sayisi": self.satir_sayisi, "uyarilar": self.uyarilar, "olaylar": self.olaylar, "kalp_atisi": self.kalp_atisi,
                "strateji_gun": self.strateji_gun, "strateji_gun_tsi": self.strateji_gun_tsi, "son_ozet": self.son_ozet, "son_haftalik": self.son_haftalik,
                "karantina": self.karantina, "karantina_bildirim": self.karantina_bildirim,
                "motor": self.motor.durum_al()}

    def kaydet(self, yol: Optional[Path] = None):
        from motor.canli.durum import atomik_yaz_json
        yol = Path(yol or self.durum_yolu)
        atomik_yaz_json(yol, _enc(self.durum_sozlugu()))

    def _pf_sutun_guncelle(self, t, eski: list, d: dict) -> tuple:
        """--ayar-guncelle: portföy sütunları YENİ ayar nesnesinden (baslat'taki keşifle aynı yol; kayıtlı son satıra kadarki veriyle)
        yeniden türetilir. -> (sütunlar, atılan kol kimlikleri, uyarı metni | None). Çıkan sembolde AÇIK POZİSYON varsa AÇIK HATA
        (sessizce eski kümeyle devam edilmez, pozisyon da sahipsiz bırakılmaz)."""
        son_t = d["motor"]["birimler"].get(t.kimlik)
        if son_t is None:
            raise RuntimeError(f"{t.kimlik}: kayıtlı durumda son işlenen satır yok; portföy sütunları yeni ayardan türetilemez")
        _, yeni, _ = psg.pf_karar(t, self._mumlar_t(Birim(t.kimlik, t.tf, pd.Timedelta(0), [], list(t.evren)), son_t))
        if list(yeni) == list(eski):
            return list(eski), set(), None
        cikan, eklenen = [x for x in eski if x not in yeni], [x for x in yeni if x not in eski]
        acik_kollar = {q["kol"] for q in d["motor"]["acik"].values()}
        acik_cikan = [x for x in cikan if f"{t.kimlik}#{x}" in acik_kollar]
        if acik_cikan:
            raise RuntimeError(f"{t.kimlik}: yeni ayar şu sembolleri evrenden çıkarıyor ama bu sembollerde AÇIK POZİSYON var: {acik_cikan}. "
                               f"Yeni ayara bu pozisyonlar kapandıktan sonra geçin (ya da kullanıcı kararıyla elle karar verin).")
        msg = (f"{t.kimlik}: --ayar-guncelle ile portföy sembol kümesi değişti; eklenen {eklenen or '-'}, çıkan {cikan or '-'} "
               f"(çıkanlarda açık pozisyon yoktu)")
        log.warning(msg)
        return list(yeni), {f"{t.kimlik}#{x}" for x in cikan}, msg

    def yukle(self, yol: Optional[Path] = None, ayar_guncelle: bool = False, olay_yaz: bool = True) -> bool:
        """Kayıtlı durumu yükler (varsa). Ayar etiketleri kayıtla uyuşmuyorsa AÇIK HATA (sessizce yeni ayara geçilmez).
        Kayıtta olup şimdi 'veri yok' olan strateji yüklemeyi düşürmez: 'askıda' taşınır, uyarı + `askida` olayı yazılır.
        olay_yaz=False: hata sonrası geri yükleme (aynı uyarılar tekrar yazılmaz)."""
        yol = Path(yol or self.durum_yolu)
        if not yol.exists():
            return False
        d = _dec(json.loads(yol.read_text(encoding="utf-8")))
        self.sozlukten_yukle(d, ayar_guncelle, olay_yaz)
        return True

    def sozlukten_yukle(self, d: dict, ayar_guncelle: bool = False, olay_yaz: bool = True) -> None:
        """`yukle`nin dosya okumadan sonraki gövdesi (çok hesaplı paper_v2 her hesabın kayıt sözlüğünü buraya verir)."""
        if d["surum"] != SURUM:
            raise RuntimeError(f"durum dosyası sürümü uyumsuz: {d['surum']}")
        fark = {k: (d["ayarlar"].get(k), t.ayar) for k, t in self.tanim_ad.items() if d["ayarlar"].get(k) != t.ayar}
        oto_fark: dict = {}
        if fark and not ayar_guncelle and self.ayar_oto_kabul:       # PAPER'da onay beklenmez (2026-11-19 kullanıcı kararı); canlı yolda bayrak kapalı -> aşağıdaki hata
            ayar_guncelle = True
            oto_fark = dict(fark)
        if fark and not ayar_guncelle:
            raise RuntimeError(f"kayıtlı durumun ayarları guncel_ayarlar.csv ile farklı: {fark}. Açık pozisyonlar eski ayarla "
                               f"yönetilir; yeni ayara geçmek için kullanıcı onayıyla --ayar-guncelle verin.")
        atilan, notlar = set(), []
        self._askida_kayit = {"ayarlar": {k: v for k, v in d["ayarlar"].items() if k not in self.tanim_ad},
                              "pf_sutunlar": {k: v for k, v in d["pf_sutunlar"].items() if k not in self.tanim_ad}}
        for t in self.tanimlar:
            if t.kol == "portfoy" and t.kimlik not in self.pf_sutunlar:
                sutun = list(d["pf_sutunlar"][t.kimlik])
                if ayar_guncelle and t.kimlik in fark:
                    sutun, at, msg = self._pf_sutun_guncelle(t, sutun, d)
                    atilan |= at
                    notlar += [msg] if msg else []
                self.pf_sutunlar[t.kimlik] = sutun
                self._birim_ekle(t)
        self.satir_sayisi = d["satir_sayisi"]
        self.uyarilar = list(d.get("uyarilar", []))
        self.olaylar = list(d.get("olaylar", []))
        self.kalp_atisi = d.get("kalp_atisi")                       # eski durum dosyasında yok (None)
        self.strateji_gun = {k: dict(v) for k, v in d.get("strateji_gun", {}).items()}
        # eski durum dosyasında TSİ serisi yok: UTC günü serisi devralınır (en çok 3 saat kayma; motor.tsi_aktarildi notu)
        self.strateji_gun_tsi = {k: dict(v) for k, v in d.get("strateji_gun_tsi", d.get("strateji_gun", {})).items()}
        self.son_ozet = d.get("son_ozet")                           # eski durum dosyasında yok (None)
        self.son_haftalik = d.get("son_haftalik")
        self.motor.durum_yukle(d["motor"], atilan_kollar=frozenset(atilan))
        self.karantina = {k: dict(v) for k, v in d.get("karantina", {}).items()}            # eski durum dosyasında yok
        self.karantina_bildirim = dict(d.get("karantina_bildirim", {}))
        self._karantina_esitle()
        self.karantina_sha_kontrol()
        self._limit_gorulen = len(self.motor.limit_olaylari)
        self._askida_kap_gorulen = len(self.motor.askida_kapanislar)
        if olay_yaz:
            for k, (eski, yeni) in oto_fark.items():           # PAPER oto-kabul: olay + günlük; Telegram tek INFO'yu canli_calistir gönderir
                self.ayar_degisenler.append((k, eski, yeni))
                msg = f"Strateji ayarı güncellendi: {k} ({_kisalt(eski)} → {_kisalt(yeni)})"
                log.warning(msg)
                self.uyarilar.append(msg)
                self.olay_ekle("ayar_otomatik", msg, self.motor.son_zaman, bildir=False)
            for msg in notlar:
                self.uyarilar.append(msg)
                self.olay_ekle("ayar_guncelle", msg, self.motor.son_zaman, bildir=False)
            for a in self.motor.askida_ozeti():
                acik = "; ".join(f"{k} {s} {'long' if y == 1 else 'short'} {m}" for k, s, y, m in a["acik"])
                msg = (f"{a['birim']} ASKIDA: kayıtlı durumda var ama şu an çalıştırılamıyor (veri yok); durumu korunuyor, emir verilmiyor"
                       + (f"; açık pozisyon son bilinen fiyatla donduruldu: {acik}" if acik else "; açık pozisyon yok"))
                log.warning(msg)
                self.uyarilar.append(msg)
                self.olay_ekle("askida", msg, self.motor.son_zaman)
        for b in self.birimler:
            if b.son_t is None:
                raise RuntimeError(f"{b.ad}: kayıtlı durumda son işlenen satır yok")
            self._motor_besle(b)
        self.baslatildi = True


# ---------------------------------------------------------------------------- tekrar modu
def tekrar_veri_yukle(tanimlar: list, bas, bit=None, veri_dizini=None, kilit_ac: bool = False, gerekce: Optional[str] = None):
    """Yerel parquet'ten (araştırma katmanıyla AYNI yükleyiciler) çerçeveler. -> (mumlar {(s,tf)}, fundingler {s})."""
    from motor.portfoy import veri as pveri
    from motor.veri import depo
    mumlar, fund = {}, {}
    for t in tanimlar:
        for s in t.veri_semboller:
            if (s, t.tf) not in mumlar:
                df = pveri.mum_yukle(s, t.tf, None, bit, veri_dizini, kilit_ac=kilit_ac, gerekce=gerekce)
                mumlar[(s, t.tf)] = df.drop(columns="eksik") if "eksik" in df.columns else df
            if s not in fund and depo.funding_yolu(s, veri_dizini).exists():
                fund[s] = depo.funding_oku(s, None, bit, dizin=veri_dizini, kilit_ac=kilit_ac, gerekce=gerekce)
    return mumlar, fund


def tekrar_calistir(tanimlar: list, mumlar: dict, fundingler: dict, kurallar: dict, bas, bit=None,
                    ayarlar: Optional[PortfoyAyarlari] = None, pencere: Optional[dict] = None,
                    kapat: bool = True, tetikleyen_hemen_kapat: bool = True, kayit=None) -> Paper:
    """Geçmiş mumları SIRAYLA 'canlıymış gibi' besler: önce `bas` anına kadar olan kapanmış mumlarla başlangıç kararı,
    sonra bas..bit arasındaki mumlar kapanış sırasıyla işlenir. kapat=True: sonda açık pozisyonlar 'veri_sonu' ile kapanır
    (backtest ile aynı). Canlı yolla AYNI kod (Paper.baslat / Paper.adim)."""
    bas = pd.Timestamp(bas)
    bas = bas.tz_localize("UTC") if bas.tzinfo is None else bas.tz_convert("UTC")
    kaynak = TekrarKaynagi(mumlar, fundingler, pencere)
    p = Paper(tanimlar, kaynak, kurallar, ayarlar, tetikleyen_hemen_kapat=tetikleyen_hemen_kapat)
    if kayit is not None:
        p.kayit_ac(kayit)
    p.baslat(bas)
    if bit is None:
        from motor.veri.depo import aralik_suresi
        bit = max(df.index[-1] + aralik_suresi(k[1]) for k, df in mumlar.items())      # son barın KAPANIŞI
    p.adim(pd.Timestamp(bit), son_satir_bayragi=kapat)
    return p


# ---------------------------------------------------------------------------- evrenden düşen semboller (tek satır, sembole göre gruplu)
BEKLENEN_DISARIDA = ("DK_JNJ", "DK_MA")        # Binance TradFi perpetual envanterinde karşılığı yok (DURUM_SOZLESMESI; kalıcı). Başka sembol düşerse BEKLENMEYEN.
BILGI_ONEKI = "BİLGİ: "                         # saglik.uyarilar içinde bu önekle başlayan satır pano'da sarı uyarı değil bilgi olarak gösterilir


def disarida_gruplari(tanimlar: list) -> list:
    """Evrenden düşen semboller, SEMBOLE göre: [{sembol, neden, beklenen, stratejiler}] (sembol sıralı). Beklenen = sabit listede VE nedeni
    'exchangeInfo'da yok' (başka neden: TRADING değil, yerel veri yok... = yeni sorun, beklenen sayılmaz)."""
    g: dict = {}
    for t in tanimlar:
        for sembol, neden in (t.disarida or {}).items():
            x = g.setdefault(sembol, {"sembol": sembol, "neden": str(neden), "stratejiler": []})
            x["stratejiler"].append(t.kimlik)
    for x in g.values():
        x["beklenen"] = x["sembol"] in BEKLENEN_DISARIDA and "exchangeInfo'da yok" in x["neden"]
        x["kapali"] = (not x["beklenen"]) and "(TRADING değil)" in x["neden"]      # borsada işleme kapandı (SETTLING/BREAK...): uyarı değil, tek seferlik bilgi
    return [g[k] for k in sorted(g)]


def disarida_metinleri(gruplar: list) -> tuple:
    """-> (bilgi_satiri | None, [uyari_satirlari]). Beklenenler TEK satır ("DK_JNJ, DK_MA: Binance'te karşılığı yok -> 7 stratejinin evreninden
    çıkarıldı (beklenen, kalıcı)"); beklenmeyen her sembol kendi satırında ve nedeniyle (gizlenmez, uyarı düzeyinde)."""
    bek = [x for x in gruplar if x["beklenen"]]
    kap = [x for x in gruplar if x.get("kapali")]
    bilgi = None
    if bek:
        n = len({k for x in bek for k in x["stratejiler"]})
        bilgi = f"{', '.join(x['sembol'] for x in bek)}: Binance'te karşılığı yok → {n} stratejinin evreninden çıkarıldı (beklenen, kalıcı)"
    if kap:
        n = len({k for x in kap for k in x["stratejiler"]})
        kb = f"{', '.join(x['sembol'] for x in kap)}: borsada işleme kapandı → {n} stratejinin evreninden çıkarıldı"
        bilgi = f"{bilgi}; {kb}" if bilgi else kb
    uyari = [f"BEKLENMEYEN evren düşmesi: {x['sembol']}: {x['neden']} → {len(x['stratejiler'])} stratejinin evreninden çıkarıldı "
             f"({', '.join(x['stratejiler'])})" for x in gruplar if not x["beklenen"] and not x.get("kapali")]
    return bilgi, uyari


def _gorunur_hesap(p, kimlik: str) -> bool:
    """Hesap adı mesajda görünür mü (v2: gizli hesap "Diğer hesap" yazılır; tek hesapta hepsi görünür)."""
    ad = getattr(p, "gorunur_adlar", None)
    return True if ad is None else kimlik in ad


def durdu_durumu(p) -> str:
    """"Bot durdu" mesajı için: açık pozisyon sayısı + stopların yerinde olup olmadığı (kâğıt durumundan; okunamazsa "stoplar: bilinmiyor")."""
    try:
        acik = list(p.motor.acik.values())
        if not acik:
            return "Açık pozisyon: yok"
        stoplu = sum(1 for x in acik if getattr(x, "stop", None) is not None)
        return f"Açık pozisyon: {len(acik)} · stoplar: " + ("yerinde" if stoplu == len(acik) else f"{stoplu}/{len(acik)} yerinde")
    except Exception:  # noqa: BLE001
        return "Açık pozisyon: bilinmiyor · stoplar: bilinmiyor"


def veri_yok_bildir(p, simdi) -> None:
    """Servis başlangıcı: verisi olmayan her hesap için 'veri_yok' olayı (gizli hesaplar dahil; gizliler Telegram'a "[gizli]" önekiyle)."""
    for t in getattr(p, "tum_veri_yok", p.veri_yok):
        if t in p.veri_yok:
            p.olay_ekle("veri_yok", f"{t.kimlik}: {t.veri_yok}", simdi)
        else:                                          # GİZLİ hesap: günlükte "[kimlik] ..." (pano süzer), Telegram'a "[gizli]" önekiyle ve hesap adı verilmeden
            p.olay_ekle("veri_yok", f"[{t.kimlik}] {t.veri_yok}", simdi, bildir=True, bildirim_mesaji="Diğer hesaplar (1) için veri yok")


def disarida_bildir(p, tanimlar: list, simdi) -> None:
    """Servis başlangıcı: beklenen düşmeler TEK bilgi olayı (Telegram'a gitmez, uyarı listesine BİLGİ önekiyle girer); beklenmeyenler eskisi gibi
    uyarı + 'veri_yok' olayı (Telegram'a gider)."""
    bilgi, uyari = disarida_metinleri(disarida_gruplari(tanimlar))
    # Bu satırlar her başlangıçta yeniden üretilir: kayıtlı durumdan gelen eski kopyaları (eski strateji başına biçim dahil) at,
    # yoksa her yeniden başlatmada birikir.
    yeni = set(uyari) | ({BILGI_ONEKI + bilgi} if bilgi else set())
    p.uyarilar = [u for u in p.uyarilar if u not in yeni and ": evrenden düşen semboller (" not in u]
    if bilgi:
        p.uyarilar.append(BILGI_ONEKI + bilgi)
        p.olay_ekle("evren_bilgi", bilgi, simdi, bildir=False)
    for x in disarida_gruplari(tanimlar):
        if x.get("kapali"):                                # TON gibi TRADING dışı sembol: evrenden düşer, BİR KEZ INFO (kalıcı işaret Bildirimci'de)
            m = re.search(r"(\S+)\s+durumu\s+\w+\s+\(TRADING değil\)", x["neden"])
            p.olay_ekle("evren_kapali", f"{m.group(1) if m else x['sembol']} borsada işleme kapandı, listeden çıkarıldı", simdi)
    for msg in uyari:
        p.uyarilar.append(msg)
        p.olay_ekle("veri_yok", msg, simdi)


# ---------------------------------------------------------------------------- servis
def _tanimlara_veri_yok_isle(tanimlar: list, esl: dict) -> None:
    """Eşlemesi bulunamayan/TRADING olmayan sembol gerektiren stratejiler 'veri yok' işaretlenir (uydurma yok)."""
    for t in tanimlar:
        eksik = [f"{s}: {esl[s][1]}" for s in t.veri_semboller if esl.get(s, (None, "eşleme tablosunda yok"))[0] is None]
        if not eksik:
            continue
        if t.kol == "tek_evren":
            # çok sembollü tek-grafik stratejisi: eşlemesi olmayan semboller evrenden DÜŞER (görünür: disarida -> uyarı/olay/ozet.notlar);
            # hiçbiri kalmazsa strateji 'veri yok'. Portföyde (ortak evren bütünlüğü) tüm strateji 'veri yok' kalır.
            kalan = [s for s in t.veri_semboller if esl.get(s, (None, ""))[0] is not None]
            t.disarida = {s: esl.get(s, (None, "eşleme tablosunda yok"))[1] for s in t.veri_semboller if s not in kalan}
            if kalan:
                t.evren = tuple(kalan)
            else:
                t.veri_yok = "; ".join(eksik)
        else:
            t.veri_yok = "; ".join(eksik)


def _durum_yaz(p: "Paper", kaynak, dizin: Path, simdi, servis=None, kaynak_adi="paper", veri_dizini: Optional[Path] = None):
    from motor.canli import paper_durum as pdr
    p.uyarilar = p.uyarilar[-50:]
    sag = kaynak.saglik_veri() if hasattr(kaynak, "saglik_veri") else [
        {"sembol": s, "tf": tf, "son_mum_acilis": df.index[-1], "mum_indeksi": df.index} for (s, tf), df in kaynak.mumlar.items()]
    o = pdr.olustur(p, simdi, kaynak_saglik=sag, olaylar=p.olaylar, uyarilar=p.uyarilar, servis=servis, kaynak=kaynak_adi,
                    veri_yok_notlari=[f"VERİ YOK: {t.kimlik} — {t.veri_yok}" for t in p.veri_yok], veri_dizini=veri_dizini)
    o["saglik"]["karantina"] = p.karantina_ozeti()
    from motor.canli import durum as d
    d.yaz_hepsi(dizin, ozet=o["ozet"], stratejiler=o["stratejiler"], islemler=o["islemler"], saglik=o["saglik"],
                gecmis=o["gecmis"], ekstra=o["ekstra"])
    return o


KOD_HATASI_SINIRI = 5     # aynı programlama hatası art arda bu kadar olursa sonsuz_dene yükseltir (servis çıkar, görünür olur)


def sonsuz_dene(fn, ad: str, uyku=None, kalici=None, bildir=None, ilk_bekle: float = 10, en_cok_bekle: float = 300,
                uyari_aralik_sn: float = 1800, saat=None, kod_hatasi_siniri: int = KOD_HATASI_SINIRI):
    """O7: geçici hatada SINIRSIZ yeniden dene (ilk_bekle sn, ikiye katlanır, en çok en_cok_bekle); servis çıkıp systemd StartLimit'e takılmasın.
    `kalici(e)` True ise hata yükselir (anahtar/ayar hatası). Her deneme loglanır; `bildir` en fazla `uyari_aralik_sn` aralıkla çağrılır.
    Programlama hatası (TypeError, AttributeError, KeyError...) geçici SAYILMAZ: her görüşte traceback'le loglanır ve hemen bildirilir
    (aralık beklenmez); AYNI türde hata (mesaj değişse de) art arda `kod_hatasi_siniri` kez olursa yükselir (sonsuza dek gizli kalmaz, sonsuz da çökmez)."""
    import time
    from motor.canli import paper_veri as pv
    uyku, saat = uyku or time.sleep, saat or time.monotonic
    bekle, son_uyari, deneme, kod_imza, kod_sayi = ilk_bekle, None, 0, None, 0
    while True:
        deneme += 1
        try:
            return fn()
        except Exception as e:  # noqa: BLE001  (ağ/5xx/ayrıştırma: geçici say; mesajda gizli yok)
            if kalici is not None and kalici(e):
                raise
            kod = pv.kod_hatasi_mi(e)
            if kod:
                imza = f"{type(e).__name__}: {e}"
                kod_sayi = kod_sayi + 1 if type(e).__name__ == kod_imza else 1      # D6: aynı hata TÜRÜ (mesaj değişse de) art arda sayılır
                kod_imza = type(e).__name__
                log.error("%s KOD HATASI (geçici sayılmaz; art arda %d/%d): %s", ad, kod_sayi, kod_hatasi_siniri, imza, exc_info=True)
                if kod_sayi >= kod_hatasi_siniri:
                    raise
            else:
                kod_imza, kod_sayi = None, 0
                log.error("%s başarısız (deneme %d, %s): %s; %g sn sonra yeniden", ad, deneme, type(e).__name__, e, bekle)
            t = saat()
            if bildir is not None and (kod or son_uyari is None or t - son_uyari >= uyari_aralik_sn):
                son_uyari = t
                try:
                    if kod:
                        bildir(f"🔴 <b>1L3A</b>: {ad} KOD HATASI ({type(e).__name__}: {str(e)[:120]}); art arda {kod_sayi}/{kod_hatasi_siniri}, "
                               f"sınırda motor durur.")
                    else:
                        bildir(f"🟠 <b>1L3A</b>: {ad} başarısız ({type(e).__name__}); yeniden deneniyor (deneme {deneme}).")
                except Exception:  # noqa: BLE001
                    pass
        uyku(bekle)
        bekle = min(bekle * 2, en_cok_bekle)


KILIT_DENEME = 5          # D15: kilit alınamazsa kalıcı çıkış (2) yerine birkaç kez kısa bekle (eski süreç kapanırken yeniden başlatma yarışı)
KILIT_BEKLE_SN = 3.0


def _kilit_al(yol: Path, uyku=None, deneme: int = KILIT_DENEME, bekle: float = KILIT_BEKLE_SN):
    """-> açık dosya (kilitli) | None (alınamadı)."""
    import fcntl
    import time
    uyku = uyku or time.sleep
    for i in range(max(1, deneme)):
        kilit = open(yol, "w")
        try:
            fcntl.flock(kilit, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return kilit
        except OSError:
            kilit.close()
            if i < deneme - 1:
                uyku(bekle)
    return None


def ayar_degisimi_metni(liste: list) -> str:
    """[(kimlik, eski, yeni)] -> tek satırlık Telegram metni ("" = değişiklik yok)."""
    if not liste:
        return ""
    from motor.canli.hesap_adlari import hesap_adi
    ilk = ", ".join(hesap_adi(k) for k, _e, _y in liste[:3])          # ham ayar değerleri kayıtta; mesajda yalnız okunur ad
    return f"Strateji ayarı güncellendi: {ilk}" + (f" (+{len(liste) - 3} strateji daha)" if len(liste) > 3 else "") + ". Yalnız yeni işlemlere uygulanır."


def canli_calistir(durum_dizini: Path, tohum_dizin: Optional[Path] = None, ayar_guncelle: bool = False,
                   tek_sefer: bool = False, set_modu: str = "v2", tur_kancasi=None, strateji_filtre=None, telegram_sessiz=False) -> int:
    """`tur_kancasi(p, simdi)`: her turda `p.adim`dan sonra çağrılır (gerçek emir yürütücüsü, motor/canli/borsa); `strateji_filtre`: yalnız bu
    strateji kimlikleri kurulur (v2); `telegram_sessiz`: paper'ın kendi Telegram bildirimleri gitmez (canlı serviste yalnız 🔴 CANLI mesajları). Varsayılanlarda (paper servisi) davranış DEĞİŞMEZ."""
    import asyncio
    import signal
    from motor.canli import paper_canli as pc, paper_veri as pv, telegram as tg
    durum_dizini = Path(durum_dizini)
    durum_dizini.mkdir(parents=True, exist_ok=True)
    kilit = _kilit_al(durum_dizini / ".kilit")
    if kilit is None:
        log.error("durum dizini başka bir süreç tarafından kullanılıyor (%s/.kilit kilitli): çıkılıyor", durum_dizini)
        return 2
    try:
        return _canli_calistir_kilitli(durum_dizini, tohum_dizin, ayar_guncelle, tek_sefer, set_modu, tur_kancasi, strateji_filtre, telegram_sessiz)
    finally:
        kilit.close()      # kapanınca flock da düşer (süreç boyunca iş bitene dek açık kalır)


def _canli_calistir_kilitli(durum_dizini, tohum_dizin, ayar_guncelle, tek_sefer, set_modu, tur_kancasi, strateji_filtre, telegram_sessiz) -> int:
    import asyncio
    import signal
    from motor.canli import paper_canli as pc, paper_veri as pv, telegram as tg
    ist = pv.FapiIstemci(yasak_dosyasi=durum_dizini / "yasak.json")      # calistir.YASAK_DOSYASI ile aynı dosya
    simdi = sonsuz_dene(ist.sunucu_zamani, "sunucu_zamani")       # O7: ağ kesintisinde çıkma, geri çekilmeyle bekle
    bilgi = sonsuz_dene(ist.exchange_info, "exchange_info")
    v2_modu = set_modu == "v2"
    if v2_modu:
        from motor.canli import paper_v2 as v2
        set_v2 = v2.set_yukle()
        tanimlar = v2.tanimlari_yukle(set_v2)           # fail-closed: desteklenmeyen çıkış alanı -> burada açık hata (servis başlamaz)
        if strateji_filtre is not None:
            eksik = set(strateji_filtre) - {t.kimlik for t in tanimlar}
            if eksik:
                raise ValueError(f"sette olmayan strateji kimliği: {sorted(eksik)}")
            tanimlar = [t for t in tanimlar if t.kimlik in set(strateji_filtre)]
    else:
        tanimlar = psg.tanimlari_yukle(ayar_kaynagi="guncel")
    semboller = sorted({s for t in tanimlar for s in t.veri_semboller})
    esl = pv.esleme_dogrula(bilgi, semboller)
    _tanimlara_veri_yok_isle(tanimlar, esl)
    kurallar_b = pv.kurallar_cikar(bilgi)
    kurallar = {s: kurallar_b[b] for s, (b, _) in esl.items() if b is not None}
    olaylar_onbellek: list = []

    def gonder(metin):
        return False if telegram_sessiz else tg.gonder(metin)

    def _bilgi(satir):                                         # işlemi etkilemeyen bilgi: ayrı mesaj değil, saatlik nota satır
        return False if telegram_sessiz else tg.bilgi_ekle(satir)
    gonder.bilgi = _bilgi

    def olay(tur, mesaj):
        olaylar_onbellek.append((tur, mesaj))
        log.info("olay %s: %s", tur, mesaj)
    aktif = [t for t in tanimlar if not t.veri_yok]
    kaynak = pc.CanliKaynak(ist, aktif, PENCERE, tohum_dizin, olay)
    sonsuz_dene(lambda: kaynak.baslat(simdi), "kaynak.baslat")
    if v2_modu:
        p = v2.PaperKasalar(tanimlar, kaynak, kurallar, set_v2, durum_yolu=durum_dizini / "paper_state.json", her_satir_kaydet=True)
    else:
        p = Paper(tanimlar, kaynak, kurallar, durum_yolu=durum_dizini / "paper_state.json", her_satir_kaydet=True)
    if os.environ.get("L3A_KAYIT_KAPALI") != "1":          # yalnız kayıt: alınmayan sinyaller + işlem etiketleri (kayit_etiketleri.py); karara etkisi yok
        from motor.canli.kayit_etiketleri import Kayit
        from motor.canli.oi_istemci import OiIstemci
        from motor.canli import haber_etiketi            # haber tonu (RSS, 15 dk önbellek; hata -> null); L3A_HABER_KAPALI=1 ile kapalı
        p.kayit_ac(Kayit(durum_dizini, oi_fn=OiIstemci(yasak_dosyasi=durum_dizini / "yasak.json"),
                         haber_fn=None if haber_etiketi.kapali() else haber_etiketi.HaberEtiketi().etiket))     # OI: ortak host yasağı, 5 sn zaman aşımı, hata -> null
        from motor.canli import etiket_kurallari        # etiket kuralları: girişi yalnız ATLATIR; L3A_ETIKET_KURAL_KAPALI=1 ile kapalı
        etiket_kurallari.bagla(p)
    from motor.canli import ogrenme_adaptor        # ML filtre + ders: girişi yalnız ATLATABİLİR (gölgesiz); L3A_OGRENME_KAPALI=1 ile kapalı; hata -> paper öğrenmesiz sürer
    og_ = ogrenme_adaptor.bagla(p, durum_dizini, gonder)
    from motor.canli import cikis_karsi_olgu       # çıkış karşı-olgusu + otomatik çıkış uygulama + "alınsaydı" gece özeti (günde bir; L3A_CIKIS_KARSI_OLGU_KAPALI=1 ile kapalı)
    cikis_karsi_olgu.bagla(p, durum_dizini, gonder, ogrenme=og_, canli=(tur_kancasi is not None or strateji_filtre is not None))   # canlıda AÇIK (kullanıcı kararı 2026-11-20); yalnız canlının yürütebildiği çıkışlar
    from motor.canli import alinsaydi_gevsetme     # "alınsaydı" kârlı giriş filtresini KÂĞITTA otomatik gevşetir / kötü giderse geri alır (L3A_ALINSAYDI_GEVSETME_KAPALI=1 ile kapalı)
    alinsaydi_gevsetme.bagla(p, durum_dizini, gonder, ogrenme=og_, canli=(tur_kancasi is not None or strateji_filtre is not None))   # CANLI yürütücü servisinde HİÇ bağlanmaz
    bld = tg.Bildirimci(gonder_fn=gonder, ortak=tg.ortak_durum(), servis=tg.SERVIS_ADI,
                        ham_fn=(lambda m: False) if telegram_sessiz else tg.ham_gonder)
    bld.durdu_bilgi = lambda: durdu_durumu(p)
    if telegram_sessiz:                        # canlı servis: paper bildirimleri sessiz, AMA karantina uyarısı/"düzeldi" (gerçek para stratejisi girişi bırakır) gider
        bld.karantina_fn = tg.gonder
    p.bildirim = bld.olay                      # teknik olaylar gönderilmez; sorun sürerse tek uyarı; sel koruması
    canli_yol = tur_kancasi is not None or strateji_filtre is not None     # canlı yürütücü (borsa/calistir.py) ikisini de verir; paper/ct_paper/aday_paper vermez
    for h_ in (list(p.hesaplar.values()) if hasattr(p, "hesaplar") else [p]):
        h_.ayar_oto_kabul = not canli_yol                  # paper: yeni ayar onaysız kabul; canlı: onay (--ayar-guncelle) şartı aynen kalır
    yuklendi = p.yukle(ayar_guncelle=ayar_guncelle)
    ayar_notu = ayar_degisimi_metni([x for h_ in (list(p.hesaplar.values()) if hasattr(p, "hesaplar") else [p]) for x in h_.ayar_degisenler])
    if ayar_notu:
        log.info("%s", ayar_notu)                    # Telegram'a gitmez (kullanıcı kararı 2026-11-20), yalnız log
    if yuklendi and v2_modu and getattr(p, "arsivlenecek", None):
        arsiv = p.durdurulanlari_arsivle(durum_dizini)   # 20 -> 10 daralması (2026-11-14): durdurulan hesapların kaydı arşive taşınır (silinmez), sonra kayıt yeni imzayla yazılır
        p.kaydet()
        log.info("durdurulan hesaplar arşivlendi: %s", arsiv)
    p.surec_basla(simdi, durum_dizini, yuklendi)         # kalp atışı + yeniden başlatma kesintisi (süresiyle `yeniden_baslatma` olayı)
    if yuklendi and v2_modu and getattr(p, "yeni_hesaplar", None):
        yeni_h = p.yeni_hesaplari_baslat(simdi)          # set'e eklenen kapanış hesapları SIFIRDAN açılır; mevcut hesaplara dokunulmaz
        p.kaydet()
        log.info("yeni hesaplar sıfırdan açıldı: %s", yeni_h)
    if not yuklendi:
        p.baslat(simdi)
        p.olay_ekle("baslangic", f"Paper başlatıldı, başlangıç sermayesi {p.ayarlar.baslangic_sermaye}", simdi)
    veri_yok_bildir(p, simdi)
    disarida_bildir(p, p.tanimlar, simdi)                  # sembole göre TEK satır (7 benzer satır yerine); beklenmeyen düşmeler uyarı kalır
    for u in pv.tradfi_sinif_uyusmazliklari(bilgi, semboller):     # TradFi funding ayrımı (2026-11-09) sınıflamaya dayanır
        p.olay_ekle("tradfi_sinif", u, simdi)
    from motor.canli import paper_durum as pdr
    if not telegram_sessiz:                                # v2: yalnız görünür hesaplar (gizliler sayıya/kasaya girmez)
        tg.baslangic_kaydet(len(p.tanimlar), p.motor.ozsermaye(), birlestir=not tek_sefer, ortak=bld.ortak)   # birlikte yeniden başlayan servisler TEK mesaj (bld.kontrol yollar)
    def _anahtar(x):
        return (x["kol"], str(x["giris_zamani"]), str(x["cikis_zamani"]))
    bildirilen = {_anahtar(x) for x in p.motor.islemler}          # kimlikle izlenir (çok hesaplı toplam listede yeni işlem sona eklenmeyebilir)
    gorulen_acik = {(a["kimlik"], a["sembol"], a["giris_zamani"]) for a in pdr.acik_pozisyonlar(p)}
    if not yuklendi:
        p.son_ozet = dun_tsi(simdi)            # ilk çalışma: paper'dan önceki gün özetlenmez
        p.son_haftalik = bugun_tsi(simdi)      # ilk çalışma günü haftalık özet gitmez (tarihçe yok)
        p.kaydet()                             # hata sonrası geri yükleme için her zaman tutarlı bir kayıt bulunsun
    kiyas_son = [None]
    durdur_gorulen = [False]
    from motor.canli import sembol_izleme            # saatlik exchangeInfo: TRADING dışına düşen sembolde yeni giriş yok (açık pozisyon: CRIT, zorla kapatma yok)
    izleyici = sembol_izleme.kur(p, ist, sorted({s for t in p.tanimlar for s in t.veri_semboller if esl.get(s, (None,))[0] is not None}),
                                 bld=bld, sessiz=telegram_sessiz)
    durum_yazici = v2.durum_yaz if v2_modu else _durum_yaz

    def _koruma_kancasi(zaman) -> None:
        """Paper turu düştüyse yürütücü yine de KORUMA turu çalıştırır (hesap kill, kill kapatması, stop/mutabakat); kendi hatası asıl hatayı maskelemez."""
        if tur_kancasi is None:
            return
        try:
            tur_kancasi(p, zaman, yalniz_koruma=True)
        except Exception:  # noqa: BLE001
            log.exception("yalnız-koruma kancası başarısız")

    def tur() -> None:
        try:
            simdi = ist.sunucu_zamani()
        except Exception:
            _koruma_kancasi(pd.Timestamp.now(tz="UTC"))     # O2: sunucu saati alınamadı: yerel saatle yalnız koruma (kill/stop), sonra hata yukarı
            raise
        while olaylar_onbellek:
            t_, m_ = olaylar_onbellek.pop(0)
            p.olay_ekle(t_, m_, simdi)
        durdur = durdur_dosyasi().exists() or hepsini_kapat_dosyasi().exists()   # Telegram /durdur (ve /hepsini_kapat) bayrağı: her turda okunur
        if durdur != durdur_gorulen[0]:
            durdur_gorulen[0] = durdur
            if durdur:
                p.olay_ekle("giris_durduruldu", "Yeni girişler durduruldu (Telegram /durdur); açık pozisyonlar kendi stop/hedefiyle sürer.", simdi)
            else:
                p.olay_ekle("giris_devam", "Yeni girişler yeniden açıldı (Telegram /devam).", simdi)
        giris_durdur_uygula(p, durdur)
        try:
            izleyici.kontrol(simdi)                        # hata sessiz: bir sonraki saate kalır
        except Exception:  # noqa: BLE001
            log.exception("sembol izleme başarısız (yoksayıldı)")
        izleyici.uygula()
        try:
            karantina_kaldir_uygula(p, simdi, durum_dizini)   # Telegram /karantina_kaldir: karantinadaki strateji bu turda yeniden denenir
        except Exception:  # noqa: BLE001  istek hatası turu düşürmesin (dosya durur, sonraki turda yeniden denenir)
            log.exception("karantina_kaldir uygulanamadı")
        try:
            kaynak.guncelle(simdi)
            n = p.adim(simdi)
            giris_durdur_uygula(p, durdur)                 # adımda doğan bekleyen giriş emirleri (canlı yürütücü bunlardan niyet türetir) silinir
            izleyici.uygula()
            try:
                hepsini_kapat_uygula(p, simdi, durum_dizini)   # Telegram /hepsini_kapat: açık pozisyonlar piyasa fiyatından kapanır (canlı yürütücü kapanışı aynı turda görür)
            except Exception:  # noqa: BLE001  istek hatası motoru hata döngüsüne sokmasın (dosya durur, sonraki turda yeniden denenir)
                log.exception("hepsini_kapat uygulanamadı")
        except Exception:
            _koruma_kancasi(simdi)                           # O2: yarım güncellenmiş paper'dan giriş/motor_kapali türetilmez; yalnız koruma
            raise
        n_gec = p._son_gec
        if tur_kancasi is not None:
            tur_kancasi(p, simdi)              # canlı yürütücü: paper motorunun niyetlerini borsaya taşır (yürütücü kendi hatasını yutmadan raporlar)
        bld.kontrol()                          # WS 10 dk'dır kopuksa tek uyarı
        p.kalp_at(simdi, durum_dizini)         # tur başarıyla tamamlandı: kalp atışı (en çok 60 sn'de bir diske)
        for a in pdr.acik_pozisyonlar(p):
            if (a["kimlik"], a["sembol"], a["giris_zamani"]) not in gorulen_acik:
                gorulen_acik.add((a["kimlik"], a["sembol"], a["giris_zamani"]))
                gonder(tg.islem_acildi_metni(a, gorunur=_gorunur_hesap(p, a["kimlik"])))
        for x in p.motor.islemler:
            if _anahtar(x) not in bildirilen:
                bildirilen.add(_anahtar(x))
                satir = pdr._islem_satiri(p, x)
                gonder(tg.islem_kapandi_metni(satir, gorunur=_gorunur_hesap(p, satir["kimlik"])))
        if tohum_dizin is not None and (kiyas_son[0] is None or simdi - kiyas_son[0] >= pd.Timedelta(hours=1)):
            kiyas_son[0] = simdi
            kiyas_btc_guncelle(ist, tohum_dizin, simdi, p)
        o = durum_yazici(p, kaynak, durum_dizini, simdi, veri_dizini=tohum_dizin)   # kıyas/güven okuması = tohum dizini (sunucuda StateDirectory)
        from motor.canli import bosluk_maruziyet   # boşluk riski: yalnız ölçüm + Telegram uyarısı (limit/emir değişmez); hata içeride yutulur
        bosluk_maruziyet.tur_kancasi(p, simdi, durum_dizini, None if telegram_sessiz else bld)
        if n or n_gec:
            p.kaydet()
        if not telegram_sessiz:
            tg.limit_yaklasma_kontrol(o, bld, bugun_tsi(simdi))      # gün içi kayıp limitin %80'inde tek uyarı (yalnız bildirim)
        ozet_an = ozet_zamani(p, simdi)
        if v2_modu and not telegram_sessiz:                 # ortak günlük özet JSON'u (saatlik + 21:00 TSİ) ve Pazar 21:10 haftalık Telegram özeti
            from motor.canli import gunluk_ozet
            if gunluk_ozet.paper_kancasi(p, durum_dizini, simdi, ozet_an, gonder):
                p.kaydet()
        if ozet_an:
            bugun = bugun_tsi(simdi)
            from motor.canli import gunluk_ozet as _go
            gonder(tg.ozet_metni(o, itibaren="%02d:%02d" % OZET_SAAT_TSI, diger=_go.diger_hesaplar(durum_dizini)))      # gün içi özet (kısmi gün: "21:00 itibarıyla")
            p.son_ozet = bugun                  # gönderim başarısız olsa da işaretlenir (her turda yeniden deneme seli olmasın; log'da görünür)
            p.kaydet()                         # yeniden başlatmada aynı gün tekrar gitmesin

    if tek_sefer:
        tur()
        p.kaydet()
        return 0

    def geri_yukle():
        """Hata sonrası: bellekteki (yarım işlenmiş olabilecek) durum atılır, son tutarlı kayıt yüklenir; olay/uyarı listesi korunur."""
        olaylar, uyarilar, karantina = list(p.olaylar), list(p.uyarilar), p.karantina_anlik()
        p.motor._acil = False
        if not p.yukle(ayar_guncelle=True, olay_yaz=False):
            raise RuntimeError("geri yüklenecek kayıtlı durum yok")
        p.olaylar, p.uyarilar = olaylar, uyarilar
        p.karantina_geri(karantina)                        # karantina kontrol durumudur (muhasebe değil): yarım tur geri alınsa da korunur (6 saat bildirim kuralı bozulmasın)

    def kalici_yaz():
        p.kaydet()
        durum_yazici(p, kaynak, durum_dizini, pd.Timestamp.now(tz="UTC"), veri_dizini=tohum_dizin)

    koruyucu = TurKoruyucu(p, geri_yukle, kalici_yaz, binance_hata=pv.BinanceHata)

    async def ana() -> int:
        durdur = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, durdur.set)
        tetik = asyncio.Event()

        def mesaj(m):
            k = m.get("data", {}).get("k")
            if k and k.get("x"):
                tetik.set()
        ws = asyncio.create_task(pc.ws_dongu(pc.ws_url(pc.akislar(kaynak)), mesaj,
                                             lambda t_, m_: olaylar_onbellek.append((t_, m_)), durdur))
        try:
            while not durdur.is_set():
                if not await loop.run_in_executor(None, koruyucu.calistir, tur):
                    break                                                   # aynı hata art arda HATA_TEKRAR_SINIRI kez: kontrollü dur
                try:
                    await asyncio.wait_for(tetik.wait(), timeout=pc.YOKLAMA_SN)
                except asyncio.TimeoutError:
                    pass
                tetik.clear()
                await asyncio.sleep(pc.GRACE_SN)
        finally:
            ws.cancel()
            p.kalp_at(pd.Timestamp.now(tz="UTC"), durum_dizini, durdu=True)      # kapanış: kapanış ile açılış arası ölçülür
            if koruyucu.tutarli:
                p.kaydet()
            else:
                log.error("bellekteki durum tutarsız (geri yükleme başarısız): kayıt YAZILMADI, son tutarlı kayıt diskte duruyor")
        return koruyucu.cikis_kodu
    return asyncio.run(ana())


# ---------------------------------------------------------------------------- servis yardımcıları (hata koruması, günlük özet, kıyas)
HATA_TEKRAR_SINIRI = 5


class TurKoruyucu:
    """Servis turunu sarar. Sessiz yutma YOK: her hata loga (traceback ile) ve olaylar'a yazılır, Telegram'a 'motor hatası' gider.
    BinanceHata: geçici sayılır (olay + log, tur tekrar denenir; eski davranış). Diğer her istisna: bellekteki durum son tutarlı
    kayda geri döner (yarım işlenmiş satır iki kez uygulanmasın), olay + bildirim; AYNI hata art arda `sinir` kez olursa kontrollü
    durulur (calistir False döner, cikis_kodu=1 -> systemd yeniden başlatır / OnFailure bildirir). Geri yükleme de başarısızsa hemen durulur."""

    def __init__(self, p: "Paper", geri_yukle, kalici_yaz=None, sinir: int = HATA_TEKRAR_SINIRI, binance_hata=None):
        self.p, self.geri_yukle, self.kalici_yaz, self.sinir = p, geri_yukle, kalici_yaz, sinir
        self.binance_hata = binance_hata or ()
        self.imza: Optional[str] = None
        self.sayi = 0
        self.cikis_kodu = 0
        self.tutarli = True

    def calistir(self, tur_fn) -> bool:
        from motor.canli.telegram import maskele
        try:
            tur_fn()
        except self.binance_hata as e:
            self.p.olay_ekle("binance_hata", maskele(str(e))[:300])
            log.error("tur başarısız: %s", maskele(str(e)))
            return True
        except Exception as e:  # noqa: BLE001  (sessiz değil: log + olay + Telegram; tekrarda kontrollü dur)
            imza = maskele(f"{type(e).__name__}: {e}")[:300]
            from motor.canli.paper_veri import kod_hatasi_mi
            anahtar = f"kod:{type(e).__name__}" if kod_hatasi_mi(e) else imza     # D6: programlama hatası mesaj değişse de (aynı tür) art arda sayılır
            self.sayi = self.sayi + 1 if anahtar == self.imza else 1
            self.imza = anahtar
            iz = traceback.extract_tb(e.__traceback__)
            yer = f" @ {Path(iz[-1].filename).name}:{iz[-1].lineno} ({iz[-1].name})" if iz else ""
            log.error("tur başarısız (motor hatası, art arda %d/%d): %s\n%s", self.sayi, self.sinir, imza,
                      maskele("".join(traceback.format_exception(e))))
            try:
                self.geri_yukle()
                geri = "bellek son tutarlı kayda döndürüldü"
            except Exception as e2:  # noqa: BLE001
                self.tutarli = False
                log.error("geri yükleme başarısız: %s", maskele("".join(traceback.format_exception(e2))))
                geri = f"GERİ YÜKLEME BAŞARISIZ ({maskele(type(e2).__name__ + ': ' + str(e2))[:150]})"
            simdi = pd.Timestamp.now(tz="UTC")
            self.p.olay_ekle("motor_hatasi", f"{imza}{yer}; art arda {self.sayi}/{self.sinir}; {geri}", simdi)
            dur = (not self.tutarli) or self.sayi >= self.sinir
            if dur:
                self.cikis_kodu = 1
                self.p.olay_ekle("motor_durdu", (f"aynı hata art arda {self.sayi} kez" if self.tutarli else "durum geri yüklenemedi")
                                 + f": {imza[:200]}. Motor durdu (çıkış kodu 1); systemd yeniden başlatır.", simdi)
            if self.tutarli and self.kalici_yaz is not None:
                try:
                    self.kalici_yaz()
                except Exception as e3:  # noqa: BLE001
                    log.error("hata sonrası durum yazılamadı: %s", maskele(f"{type(e3).__name__}: {e3}"))
            return not dur
        self.imza, self.sayi = None, 0
        return True


def dun_tsi(simdi) -> str:
    """Sunucu zamanına (UTC) göre bir önceki TSİ günü 'YYYY-MM-DD'."""
    from motor.canli import durum_ek as ek
    return str((pd.Timestamp(simdi).tz_convert(ek.TSI) - pd.Timedelta(days=1)).date())


OZET_SAAT_TSI = (21, 0)                       # günlük özet (standart): TSİ 21:00'de o günün (TSİ) gün içi özeti, günde bir kez


def bugun_tsi(simdi) -> str:
    """Sunucu zamanına (UTC) göre TSİ günü 'YYYY-MM-DD'."""
    from motor.canli import durum_ek as ek
    return str(pd.Timestamp(simdi).tz_convert(ek.TSI).date())


def ozet_zamani(p: "Paper", simdi) -> bool:
    """Günlük özet gönderilmeli mi: TSİ saati >= 21:00 ve bugünün (TSİ) özeti henüz gönderilmedi (p.son_ozet = son özetlenen TSİ günü, state'te)."""
    from motor.canli import durum_ek as ek
    yer = pd.Timestamp(simdi).tz_convert(ek.TSI)
    return (yer.hour, yer.minute) >= OZET_SAAT_TSI and p.son_ozet != bugun_tsi(simdi)


# ---------------------------------------------------------------------------- yeni giriş durdurma bayrağı (Telegram /durdur)
DURDUR_VARSAYILAN = "/var/lib/1l3a-paper/durum/DURDUR"


def durdur_dosyasi(env=None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("L3A_DURDUR_DOSYA") or DURDUR_VARSAYILAN)


class _HerZamandanSonra:
    """`t < islem_baslangic` her zaman doğru (motorun mevcut 'ısınma' engeli: yeni pozisyon açılmaz, açıklar kendi stop/hedefinde sürer)."""
    def __gt__(self, diger): return True
    def __ge__(self, diger): return True
    def __lt__(self, diger): return False
    def __le__(self, diger): return False
    def __repr__(self): return "<durdur>"


_DURDUR_ISARETI = _HerZamandanSonra()


def _motorlar(p) -> list:
    h = getattr(p, "hesaplar", None)
    return [x.motor for x in h.values()] if h else [p.motor]


def giris_durdur_uygula(p, aktif: bool) -> None:
    """Bayrak varken YENİ GİRİŞ YOK: motorun `islem_baslangic` engeli (yeni pozisyon reddedilir) + bekleyen giriş emirleri silinir
    (canlı yürütücü niyetleri `kol.giris_emri`'nden türetir: paper girişi durunca canlı girişi de durur). Açık pozisyonlar, stop/hedef ve
    çıkış emirleri DOKUNULMAZ. Bayrak kalkınca eski değer geri gelir. Her turda (adımdan önce ve sonra) çağrılır."""
    for m in _motorlar(p):
        if aktif:
            if m.islem_baslangic is not _DURDUR_ISARETI:
                m._islem_baslangic_onceki = m.islem_baslangic
                m.islem_baslangic = _DURDUR_ISARETI
            for kol in getattr(m, "tum_kollar", []):
                kol.giris_emri = None
        elif m.islem_baslangic is _DURDUR_ISARETI:
            m.islem_baslangic = getattr(m, "_islem_baslangic_onceki", None)


# ---------------------------------------------------------------------------- acil kapatma isteği (Telegram /hepsini_kapat)
HEPSINI_KAPAT_AD = "HEPSINI_KAPAT"
HEPSINI_KAPAT_SIL_SN = 120          # istek dosyası bu süre sonra silinir (aynı dizini izleyen paper / ct / aday süreçlerinin hepsi turlarında görmüş olsun)
HEPSINI_KAPAT_ACK = "hepsini_kapat_islendi.json"


def hepsini_kapat_dosyasi(env=None) -> Path:
    """İstek dosyası DURDUR ile aynı dizinde (komut servisi yazar). L3A_HEPSINI_KAPAT_DOSYA ile değişebilir."""
    env = os.environ if env is None else env
    return Path(env.get("L3A_HEPSINI_KAPAT_DOSYA") or (durdur_dosyasi(env).parent / HEPSINI_KAPAT_AD))


def _istek_zamani(dosya: Path):
    try:
        z = json.loads(dosya.read_text(encoding="utf-8")).get("zaman")
        if z:
            ts = pd.Timestamp(z)
            return str(z), (ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC"))
    except (OSError, ValueError, AttributeError):
        pass
    try:
        t = pd.Timestamp(dosya.stat().st_mtime, unit="s", tz="UTC")
        return str(t), t
    except OSError:
        return None, None


def hepsini_kapat_uygula(p, simdi, durum_dizini, env=None) -> Optional[int]:
    """İstek dosyası varsa her motorun açık pozisyonlarını motorun mevcut acil kapatma yoluyla (`_acil_kapat`: son bilinen piyasa fiyatı, stop kayması,
    komisyon; kill/günlük limit kapatmasının aynısı) kapatır, yeni giriş açılmasın diye bekleyen giriş emirlerini siler, WARN olayı yazar.
    Her süreç isteği BİR kez işler (kimlik = isteğin zamanı; `hepsini_kapat_islendi.json`); dosya HEPSINI_KAPAT_SIL_SN sonra silinir.
    -> kapatılan pozisyon sayısı (istek yok / bu süreç zaten işlemişse None). Canlı yürütücü paper'ı izlediği için niyet kapanış olur (canlı modda borsadaki pozisyonlar da mutabakatla kapanır)."""
    dosya = hepsini_kapat_dosyasi(env)
    if not dosya.exists():
        return None
    kimlik, ist = _istek_zamani(dosya)
    ack = Path(durum_dizini) / HEPSINI_KAPAT_ACK
    try:
        islendi = json.loads(ack.read_text(encoding="utf-8")).get("istek") == kimlik
    except (OSError, ValueError, AttributeError):
        islendi = False
    sayi = None
    if not islendi:
        sayi = 0
        for m in _motorlar(p):
            sayi += len(m.acik) + len(m.askida["acik"])
            t = m.son_zaman if m.son_zaman is not None else pd.Timestamp(simdi)
            if m.acik or m.askida["acik"]:
                m._acil_kapat(t, "hepsini_kapat")
        giris_durdur_uygula(p, True)
        if hasattr(p.motor, "yenile") and getattr(p, "hesaplar", None):
            p.motor.yenile()
        try:
            ack.write_text(json.dumps({"istek": kimlik, "zaman": d_zaman(simdi), "kapanan": sayi}), encoding="utf-8")
        except OSError:
            log.exception("hepsini_kapat işlendi işareti yazılamadı")
        if getattr(p, "durum_yolu", None):
            p.kaydet()
        p.olay_ekle("hepsini_kapat", f"Telegram /hepsini_kapat: {sayi} açık pozisyon piyasa fiyatından kapatıldı; yeni girişler durduruldu (açmak için /devam).", simdi)
    if ist is not None and (pd.Timestamp(simdi) - ist).total_seconds() >= HEPSINI_KAPAT_SIL_SN:
        dosya.unlink(missing_ok=True)
    return sayi


def _kasalar(p) -> list:
    h = getattr(p, "hesaplar", None)
    return list(h.values()) if h else [p]


def karantina_kaldir_uygula(p, simdi, durum_dizini, env=None) -> Optional[int]:
    """Telegram /karantina_kaldir isteği (istek dosyası DURDUR ile aynı dizinde): eşleşen karantinadaki stratejiler YENİDEN denenir (ilk başarılı karardan
    sonra INFO 'düzeldi'; yine hata verirse yeniden karantina). Her süreç isteği BİR kez işler (kimlik = isteğin zamanı; `karantina_kaldir_islendi.json`).
    -> kaldırılan sayı (istek yok / zaten işlenmiş: None)."""
    dosya = kq.istek_dosyasi(durdur_dosyasi(env).parent, env)
    if not dosya.exists():
        return None
    kimlik, ist = _istek_zamani(dosya)
    ack = Path(durum_dizini) / kq.ISTEK_ACK
    try:
        islendi = json.loads(ack.read_text(encoding="utf-8")).get("istek") == kimlik
    except (OSError, ValueError, AttributeError):
        islendi = False
    sayi = None
    if not islendi:
        try:
            hedef = str(json.loads(dosya.read_text(encoding="utf-8")).get("strateji", ""))
        except (OSError, ValueError, AttributeError):
            hedef = ""
        sayi = 0
        for k in _kasalar(p):
            for kid in list(k.karantina):
                if kq.hedef_eslesir(hedef, kid, getattr(k, "gorunur", True)) and k.karantina_kaldir(kid, "Telegram /karantina_kaldir; yeniden denenecek"):
                    sayi += 1
        try:
            ack.write_text(json.dumps({"istek": kimlik, "zaman": d_zaman(simdi), "kaldirilan": sayi}), encoding="utf-8")
        except OSError:
            log.exception("karantina_kaldir işlendi işareti yazılamadı")
        if sayi and getattr(p, "durum_yolu", None):
            p.kaydet()
    if ist is not None and (pd.Timestamp(simdi) - ist).total_seconds() >= HEPSINI_KAPAT_SIL_SN:
        dosya.unlink(missing_ok=True)
    return sayi


def dun_ozeti(p: "Paper", gun: str) -> dict:
    """Biten TSİ günü `gun` için tam gün K/Z: o günün son özsermayesi - önceki TSİ gününün son özsermayesi (pano ile aynı tanım,
    motor.gun_kapanis_tsi). -> {gun, pnl, getiri, not}."""
    gk = p.motor.gun_kapanis_tsi
    bas = Decimal(str(p.ayarlar.baslangic_sermaye))
    onceki = [g for g in gk if g < gun]
    e0 = Decimal(gk[max(onceki)]) if onceki else bas
    son = [g for g in gk if g <= gun]
    e1 = Decimal(gk[max(son)]) if son else e0
    pnl = e1 - e0
    notu = None if gun in gk else "o gün işlenen mum yok (değişim 0)"
    return {"gun": gun, "pnl": pnl, "getiri": float(pnl / e0) if e0 > 0 else 0.0, "not": notu}


KIYAS_SEMBOL, KIYAS_TF = "BTCUSDT", "1h"


def kiyas_btc_guncelle(ist, tohum_dizin: Path, simdi, p: Optional["Paper"] = None) -> Optional[int]:
    """BTC al-tut kıyası (kiyas.py, tohum dizinindeki BTCUSDT 1h dosyasını okur) bayatlamasın: Binance'ten kapanmış 1h mumları alınır,
    mevcut dosyaya eklenip ATOMİK yazılır (geçici dosya + replace). kiyas.py değişmez. Araştırma veri dizini (depo içi veri/mumlar)
    REDDEDİLİR (araştırma verisine yazılmaz). Hata (Binance/disk): log + uyarı, tur düşmez (sonraki saatte yeniden denenir).
    -> eklenen mum sayısı | None (yazılmadı)."""
    from motor.veri import depo
    try:
        if Path(tohum_dizin).resolve() == (KOK / "veri" / "mumlar").resolve():
            log.info("kıyas BTC güncellemesi atlandı: tohum dizini araştırma veri dizini (yazılmaz)")
            return None
        yol = depo.mum_yolu(KIYAS_SEMBOL, KIYAS_TF, Path(tohum_dizin))
        eski = pd.read_parquet(yol) if yol.exists() else None
        if eski is not None and len(eski):
            bas = eski.index[-1] + pd.Timedelta(hours=1)
        else:
            ilk = min(p.motor.gun_kapanis_tsi) if (p is not None and p.motor.gun_kapanis_tsi) else None
            bas = (pd.Timestamp(ilk, tz="UTC") if ilk else pd.Timestamp(simdi)) - pd.Timedelta(days=30)
        if pd.Timestamp(simdi) < bas + pd.Timedelta(hours=1):
            return 0
        yeni = ist.klines(KIYAS_SEMBOL, KIYAS_TF, bas, None, pd.Timestamp(simdi))
        if not len(yeni):
            return 0
        df = yeni if eski is None else pd.concat([eski, yeni[~yeni.index.isin(eski.index)]]).sort_index()
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_name(yol.name + ".tmp")
        df.to_parquet(gecici)
        gecici.replace(yol)
        return len(df) - (0 if eski is None else len(eski))
    except Exception as e:  # noqa: BLE001  (sessiz değil: log + uyarı; kıyas yalnız gösterge, motoru durdurmaz)
        msg = f"kıyas BTC 1h güncellenemedi: {type(e).__name__}: {str(e)[:200]}"
        log.error(msg)
        if p is not None:
            p.uyarilar.append(msg)
        return None


def tekrar_cli(bas, bit, ayar: str, durum_dizini: Path, veri_dizini=None) -> int:
    """Geçmişi canlıymış gibi besler (7 strateji TEK hesapta, kol payları ve ortak limitlerle) ve durum/ dosyalarını yazar."""
    from motor.arastirma import tarama
    from motor.portfoy.motor import sembol_kurali
    tanimlar = psg.tanimlari_yukle(ayar_kaynagi=ayar)
    bas = pd.Timestamp(bas, tz="UTC") if pd.Timestamp(bas).tzinfo is None else pd.Timestamp(bas)
    bit_ts = pd.Timestamp(bit, tz="UTC") if bit else None
    mumlar, fund = tekrar_veri_yukle(tanimlar, bas, bit_ts, veri_dizini, kilit_ac=True,
                                     gerekce="Aşama 4: paper tekrar modu (kilit kullanılmış sayılır)")
    kurallar = {s: tarama.SEMBOL_KURALLARI.get(s, tarama.VARSAYILAN_KURAL) for t in tanimlar for s in t.veri_semboller}
    p = tekrar_calistir(tanimlar, mumlar, fund, kurallar, bas, bit_ts, pencere={tf: PENCERE.get(tf, 1500) for tf in ("30m", "4h", "1d")},
                        kapat=False)
    simdi = bit_ts or max(df.index[-1] for df in mumlar.values())
    from motor.canli.paper_kaynak import TekrarKaynagi
    _durum_yaz(p, p.kaynak, durum_dizini, simdi, kaynak_adi="backtest")
    print(f"[tekrar] {p.satir_sayisi} satır işlendi; kapanan işlem {len(p.motor.islemler)}; özsermaye {p.motor.ozsermaye():.2f}")
    return 0


def tekrar_cli_v2(bas, bit, durum_dizini: Path, veri_dizini=None, surec: int = 4) -> int:
    """v2 seti (10 hesap): geçmişi canlıymış gibi besler, toplam + hesap başına durum dosyalarını yazar. Holdout dönemi verisi için onaylı
    kilit yolu kullanılır (kilit_acilis.jsonl'e yazılır). tek_evren kararları paralel önbellekle hesaplanır (aynı tek_karar; bkz. paper_v2)."""
    from motor.canli import paper_v2 as v2
    s = v2.set_yukle()
    tanimlar = v2.tanimlari_yukle(s)
    bas = pd.Timestamp(bas, tz="UTC") if pd.Timestamp(bas).tzinfo is None else pd.Timestamp(bas)
    bit_ts = pd.Timestamp(bit, tz="UTC") if bit else None
    mumlar, fund = v2.veri_yukle(tanimlar, veri_dizini, bit=bit_ts)
    tanimlar = [t for t in tanimlar if not t.veri_yok]
    son = bit_ts or max(df.index[-1] + pd.Timedelta(0) for df in mumlar.values())
    onb = v2.karar_onbellegi_olustur(tanimlar, mumlar, fund, bas, son, KOK / "sonuclar" / "paper_v2" / "onbellek", surec)
    p = v2.kos(v2.kasalar_kur(tanimlar, mumlar, fund, s, onbellek=onb), bas, son, kapat=False)
    v2.durum_yaz(p, p.kaynak, durum_dizini, son, kaynak_adi="backtest", hesaplari_yaz=True)
    print(f"[tekrar v2] {p.satir_sayisi} satır; hesap başına: " + ", ".join(
        f"{k} {len(h.motor.islemler)} işlem {float(h.motor.ozsermaye()):.2f}" for k, h in p.hesaplar.items()))
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="1L3A paper trading (gerçek emir yok)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--canli", action="store_true", help="servis: canlı Binance verisiyle paper")
    g.add_argument("--tek-sefer", action="store_true", help="bir tur çalış, durum yaz, çık")
    g.add_argument("--tekrar", nargs="+", metavar=("BAS", "BIT"), help="geçmiş tekrarı: BAS [BIT] (UTC tarih)")
    ap.add_argument("--set", default="v2", choices=["v2", "eski"], dest="set_modu",
                    help="v2: 10 stratejilik paper seti, her biri kendi kasasında (varsayılan); eski: 7'li final set (tek hesap; yalnız geriye uyumluluk)")
    ap.add_argument("--surec", type=int, default=4, help="tekrar v2: karar önbelleği için süreç sayısı")
    ap.add_argument("--durum", default=None, help="durum dizini (varsayılan: v2 için durum_v2/, eski set için durum/)")
    ap.add_argument("--tohum", default=None, help="yerel tohum veri dizini (veri/mumlar); yoksa yalnız REST")
    ap.add_argument("--ayar", default=None, choices=["guncel", "kilit"], help="tekrar modu ayar kaynağı (varsayılan: guncel)")
    ap.add_argument("--ayar-guncelle", action="store_true", help="kayıtlı durumdaki ayarlar csv'den farklıysa KULLANICI ONAYIYLA yeni ayara geç")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args(argv)
    logging.basicConfig(level=a.log, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    durum = Path(a.durum) if a.durum else KOK / ("durum_v2" if a.set_modu == "v2" else "durum")
    if a.tekrar:
        bit = a.tekrar[1] if len(a.tekrar) > 1 else None
        if a.set_modu == "v2":
            return tekrar_cli_v2(a.tekrar[0], bit, durum, surec=a.surec)
        return tekrar_cli(a.tekrar[0], bit, a.ayar or "guncel", durum)
    return canli_calistir(durum, Path(a.tohum) if a.tohum else None, a.ayar_guncelle, a.tek_sefer, a.set_modu)   # != 0: kontrollü hata durması


if __name__ == "__main__":
    raise SystemExit(main())
