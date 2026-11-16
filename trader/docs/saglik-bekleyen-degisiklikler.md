# Sağlık (madde 19): bekleyen değişiklikler (spec Bölüm 11) ve açık noktalar

Bu iş paketinde dokunulmadı; sonraki adımda ilgili sahibi yapacak.

1. `docker-compose.yml`: her servise `mem_limit` (öneri learner 700m, twin 500m) ve `memswap_limit`; `oom_kill_disable` kullanılmaz.
2. `docker-compose.yml`: `healthcheck` (python `urllib` ile `/api/v1/ping`; imajda `curl` var mı doğrula), `interval: 60s`, `retries: 3`.
3. `docker-compose.yml`: `stop_grace_period: 60s`.
4. `config/base.json` `api_server`: konteyner içi `listen_ip_address=0.0.0.0` (ana makineye yalnız 127.0.0.1 yayımlı); `username/password/jwt_secret_key` `.env`'den dolacak (runner `/api/v1/health`, `status`, `pair_candles` için Basic auth kullanır).
5. `ledger.py`: `Ledger.gate_status_readonly() -> Health` ve isteğe bağlı `Ledger.last_write_at()`. Runner şimdilik `probe_ledger` içinde salt okunur ham SQL (`max(probed_at/recorded_at)`, `param_activations`) ve `find_unledgered_trades/find_orphan_decisions` kullanıyor; bunlar eklenince `scripts/health_run.py::probe_ledger` bu API'ye geçirilmeli (botun bellekteki `degraded` bayrağı hâlâ görünmez).
6. Konteyner adları: runner `trader-learner` / `trader-twin` varsayar (`docker inspect`); compose `container_name` ile eşleşmeli.
7. freqtrade API uç noktaları (`/api/v1/ping|health|show_config|status|pair_candles`) ve Basic auth kabulü 2026.10 imajından doğrulanmalı; R7 (borsada koruyucu stop alan adı) henüz uygulanmadı (`UNKNOWN` döner).
8. Birimlerdeki yollar (`/opt/trader`, `/home/trader/trader/user_data`) kurulum belgesinde (madde 19 dağıtım) gerçek yollarla güncellenecek.
