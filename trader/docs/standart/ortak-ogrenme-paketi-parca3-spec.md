# Ortak paket — parça 3: Telegram çekirdeği (`ortak_ogrenme/telegram_cekirdek.py`, sürüm 1.2.0)

Amaç: Telegram standardını (`trader/docs/standart/telegram-standardi.md`) 1L3A ve CT'nin hazır kullanabilmesi. Kaynak: ML `trader/src/trader_core/telegram.py` (yalnız genel parçalar; ML'e özgü komut metinleri dışarıda).
Bağımlılık: yalnız standart kütüphane. Ağ çağrısı dışarıdan verilen `http_post(url, json=..., timeout=...)` fonksiyonuyla yapılır (test edilebilir); varsayılan `urllib`.

## Parçalar (ML ile aynı davranış)
- Sabitler: `MAX_TEXT=3500`, `CODE_TTL_S=120`, `INFO_MAX_AGE_S=86400`, `RATE_PER_MIN=15`, `SEVERITIES=("INFO","WARN","CRIT")`.
- `mask(text, token)`, `neutralize(text)`, `fit_text(body, pinned="", limit=MAX_TEXT)`: ML ile birebir.
- `etiketle(proje, text) -> str`: ilk satıra `[PROJE] ` öneki (proje ∈ ML, 1L3A, CT; aksi `ValueError`); zaten etiketliyse tekrar eklemez.
- `TelegramClient(token, http_post=None, sleep=...)`: `send_message`, `get_updates`, `answer_callback_query`, `edit_message_text`; ML ile aynı hata sınıfı/yeniden deneme (429 `retry_after`) davranışı.
- `Outbox(base, now_fn)`: `enqueue(item)`, `drain(client, chat_id, sleep)`, `sent_recently(key)`, `mark_sent(key, until_epoch)`, `pending_for`, `list`; limitler ve INFO yaşlanması ML ile aynı; atomik dosya yazımı.
- `TelegramNotifier(client, chat_id, outbox, now_fn, proje)`: `send_text(text, severity, dedup_key, ...)` — gönderilen her metin `etiketle(proje, ...)` ile etiketlenir; hız sınırı ve tekrar önleme ML ile aynı.
- İki adımlı onay: `OnayKapisi(dosya, now_fn, rng=secrets)`: `baslat(komut, ozet) -> kod (4 hane)`; `dogrula(komut, kod) -> bool` (120 sn içinde ve aynı komut için, tek kullanımlık; yanlış kodda bekleyen istek silinir); denetim kaydı JSONL'e (`zaman, olay, komut, sonuc`). Kod metinde değil yalnız mesajla gider; dosyada kodun sha256'sı tutulur.

## Eşdeğerlik
- `mask`, `neutralize`, `fit_text`, `Outbox` (enqueue/drain/limit/yaşlanma) ML ile aynı girdi → aynı çıktı (parite testleri).
