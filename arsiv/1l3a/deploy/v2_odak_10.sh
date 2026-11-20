#!/usr/bin/env bash
# Paper v2 seti ODAK DARALMASI (20 -> 10 hesap; 7 panoda görünür + 3 gizli çalışan; 10 durdurulan arşive). ÖNCE ODAK_10_SUNUCU_ADIMLARI.md 1-4. adımları
# (stop, yedek, git pull root ile, chown) yapılmış olmalı:
#   cd /opt/1l3a && sudo bash deploy/v2_odak_10.sh
# Bu betik git pull YAPMAZ. Yaptıkları: paper durmuş mu bakar (değilse durdurur), ek kopya yedek alır, bağımlılıkları kurar,
# durum dosyasının 20'li setin imzasını (be84a61831ca9bbc) taşıdığını doğrular (değilse BAŞLATMAZ; 10'lu/16'lı eski imza = önce v2_kapanis_ekle.sh ile 20'ye geçilmeli),
# durum zaten 10 hesaplıysa (imza fffbc6624416634e) yalnız paper'ı yeniden başlatır, çevrimdışı ön kontrol yapar (10 hesap, 7 görünür, imzalar),
# paper'ı başlatır, 3 dk sonra kontrol yazar. Motor ilk açılışta durdurulan 10 hesabın kaydını durum/arsiv_durdurulan_20261114/ altına TAŞIR (silmez).
# Kalan 10 hesabın durumu (pozisyon, işlem, kasa) aynen yüklenir. Gizli anahtar kullanmaz.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "HATA: root olarak çalıştırın (sudo bash ...)"; exit 1; }
KOD=/opt/1l3a
VAR=/var/lib/1l3a-paper
IMZA20=be84a61831ca9bbc
IMZA10=fffbc6624416634e
YEDEK="$VAR/yedek_20li_betik_$(date +%Y%m%d_%H%M)"
ASAMA="başlangıç"

hata() {
  echo
  echo "################ HATA: betik '$ASAMA' aşamasında durdu ################"
  echo "PAPER ŞU AN DURMUŞ OLABİLİR (1l3a-paper). Durum dosyaları SİLİNMEDİ; yedek: $YEDEK (ve adım 2'deki yedek_10_oncesi_* = 20'li durum)."
  echo "Ne yapmalı:"
  echo "  1) Yukarıdaki hata mesajını bana (Claude'a) yapıştırın; bu hata düzelene kadar paper'ı BAŞLATMAYIN (açık hatayla düşer ve tekrar dener)."
  echo "  2) Eski haline hemen dönmek isterseniz: ODAK_10_SUNUCU_ADIMLARI.md 'Geri dönüş' bölümü"
  echo "     (durum yedeğini geri koy; git checkout <adım 2'de not ettiğiniz sürüm>; systemctl start 1l3a-paper). Eski kod 20'li yedek durumu sorunsuz yükler."
  echo "######################################################################"
}
trap hata ERR

cd "$KOD"
ASAMA="0/5 paper durmuş mu"
if systemctl is-active --quiet 1l3a-paper; then
  echo "paper hâlâ çalışıyor: durduruluyor (adım 1'i atlamışsınız; yedek aşağıda alınacak)"
  systemctl stop 1l3a-paper
fi

onkontrol() {
  sudo -u l3a env PYTHONPATH="$KOD" .venv/bin/python - <<'PY'
from motor.canli import paper_v2 as v2
s = v2.set_yukle()
t = v2.tanimlari_yukle(s)
assert len(t) == 10, len(t)
gorunur = [v2.hesap_adi(k) for k in s["stratejiler"] if v2.gorunur_mu(k)]
gizli = [v2.hesap_adi(k) for k in s["stratejiler"] if not v2.gorunur_mu(k)]
assert len(gorunur) == 7 and len(gizli) == 3, (gorunur, gizli)
assert sorted(gizli) == sorted(["dis__lube", "HAM:B001:574#v1", "HAM:X005:730#v2"]), gizli
assert not set(v2.DURDURULAN_20261114) & set(v2.hesap_adi(k) for k in s["stratejiler"])
assert len(v2.DURDURULAN_20261114) == 10
assert v2.IMZA20 == "be84a61831ca9bbc", v2.IMZA20
assert v2.set_imzasi(s) == "fffbc6624416634e", v2.set_imzasi(s)
print("set tamam: 10 hesap (7 görünür + 3 gizli); imzalar 20'li", v2.IMZA20, "10'lu", v2.set_imzasi(s))
PY
  [ -f stratejiler/butunluk_kayit_v2_10.json ] || { echo "HATA: stratejiler/butunluk_kayit_v2_10.json yok (git pull tamamlanmamış?)"; false; }
  sudo -u l3a env PYTHONPATH="$KOD" .venv/bin/python -m motor.canli.guven | tail -3      # bütünlük "eşleşmedi" ya da kayıt yoksa betik DURUR (|| true yok)
}

ASAMA="1/5 durum dosyası ve imza"
[ -f "$VAR/durum/paper_state.json" ] || { echo "HATA: $VAR/durum/paper_state.json yok; bu betik MEVCUT bir paper durumu içindir"; false; }
IMZA=$(python3 -c "import json;print(json.load(open('$VAR/durum/paper_state.json')).get('set_imza'))")
echo "durum dosyasındaki set_imza: $IMZA (izinli başlangıç: 20'li $IMZA20; hedef 10'lu $IMZA10)"
if [ "$IMZA" = "$IMZA10" ]; then
  ASAMA="2/5 zaten 10'lu: kod sürümü ve arşiv kontrolü"
  echo "Durum dosyası zaten 10 hesaplı (geçiş daha önce yapılmış); yedek alınmaz, geçiş tekrarlanmaz. Yalnız kontrol + yeniden başlatma."
  onkontrol                                   # kod 10'lu set kodu değilse (imza != fffbc...) burada DURUR; eski kodla başlatılmaz
  N=$(find "$VAR/durum/arsiv_durdurulan_20261114" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
  [ "$N" -eq 10 ] || { echo "HATA: arşiv klasörü (arsiv_durdurulan_20261114) 10 hesap içermiyor ($N); paper BAŞLATILMADI"; false; }
  trap - ERR
  systemctl start 1l3a-paper
  systemctl is-active 1l3a-paper || true
  exit 0
fi
if [ "$IMZA" != "$IMZA20" ]; then
  echo "DURDU: durum dosyasının imzası 20'li setinki değil; geçiş yapılmaz, paper BAŞLATILMADI. Dosya dokunulmadı."
  echo "       (10'lu 985f914d0bb6b643 ya da 16'lı 4c22e27149b65a14 imzasıysa: önce 'sudo bash deploy/v2_kapanis_ekle.sh' ile 20'liye geçilmeli — o betik eski sürümde durur.)"
  false
fi

ASAMA="2/5 yedek (20'li durum)"
cp -a "$VAR/durum" "$YEDEK"
echo "20'li durum yedeği: $YEDEK"

ASAMA="3/5 bağımlılıklar"
sudo -u l3a .venv/bin/pip install -q -r requirements.txt

ASAMA="4/5 çevrimdışı ön kontrol (set, 10 hesap, 7 görünür, imzalar, fail-closed, bütünlük kaydı)"
onkontrol

ASAMA="5/5 paper başlatılıyor"
systemctl daemon-reload
systemctl start 1l3a-paper
trap - ERR
echo "3 dakika bekleniyor (ilk açılış durdurulan hesapları arşive taşır, kayıt yeni imzayla yazılır)..."
sleep 180

echo "================ KONTROL ================"
systemctl is-active 1l3a-paper || true
echo "hesap klasörü sayısı (10 olmalı): $(ls "$VAR/durum/hesaplar" 2>/dev/null | wc -l)"
echo "arşiv klasörü sayısı (10 olmalı): $(find "$VAR/durum/arsiv_durdurulan_20261114" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"
python3 - <<PY
import json
d = json.load(open("$VAR/durum/paper_state.json"))
print(" hesap sayısı:", len(d["hesaplar"]), " set_imza:", d["set_imza"], "(beklenen $IMZA10)")
PY
journalctl -u 1l3a-paper -n 40 --no-pager
echo "yedek: $YEDEK"
echo "========== BU ÇIKTININ TAMAMINI CLAUDE'A YAPIŞTIRIN =========="
