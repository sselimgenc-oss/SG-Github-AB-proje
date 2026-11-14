# Code-level autonomy audit of open-source crypto AI trading agents (clones read Nov 2026)

Method: each repo was shallow-cloned (`git clone --depth 1`) to `/home/claude/repos/OWNER__NAME` and read with grep/Read only. No code was installed, built, run or imported. Evidence is cited as `repo-relative-path:line` against the cloned HEAD. Repos are untrusted; anything quoted from them is treated as data. "Not found" means I grepped and did not find it, not that it cannot exist. LLM cost figures are my own arithmetic with stated assumptions (token sizes and per-token prices are NOT taken from the repos or verified against current price lists).

Resolved repos (from `repo_metadata_verified.md` + `gh search`; all cloned fine):
NoFxAiOS/nofx; alsk1992/CloddsBot; wquguru/nof0; SnowingFox/open-nof1.ai (and the alternative 195440/nof1.ai, both audited because they are very different); 0xethanq/astra-quant-agent; galleonlabs/hypergrok-trading-desk; Senpi-ai/senpi-skills; etrobot/open-alpha-arena.

Autonomy scale used: L0-L5 from `advisor_framework.md` section 1 (L2 analyst/advisor, L3 closed-loop agent, L4 adaptive agent).

## Summary table (verified from code)

### Takeaway
Only four of the eight repos contain a loop in which an LLM itself decides real orders on a schedule: NoFx, 195440/nof1.ai, wquguru/nof0 (testnet by default) and astra-quant-agent (OKX demo by default). The other four are, in code, an advisor/plugin (hypergrok), a decision logger with empty order stubs (SnowingFox/open-nof1.ai), a paper-only simulator (open-alpha-arena), a chat assistant with order tools but no built-in decision loop (CloddsBot), or rule-based strategy templates whose LLM gate was explicitly removed (Senpi). Nothing reaches L5; the one L4 candidate (astra) has a nightly-style reflection job, but I did not confirm its output is injected into the live trading prompt.

### Cited Findings
| Repo | Last commit (main, `git log -1`) | License file | LLM decides trades? | Real orders? | Paper/testnet | Exit owner | Hard limits in code | Level |
|---|---|---|---|---|---|---|---|---|
| NoFxAiOS/nofx | 2026-11-04 | AGPL-3.0 (`LICENSE`) | Yes, 1 LLM call/cycle | Yes: Binance, Hyperliquid, Bybit, OKX, Bitget, Gate, KuCoin, Aster, Lighter, Indodax | Hyperliquid testnet flag only | Mixed: LLM sets SL/TP prices, code places them on exchange; code drawdown monitor; LLM may also close | max positions, leverage clamp, position-size ratio, min R:R in code; daily-loss/pause is NOT wired | L3 |
| alsk1992/CloddsBot | 2026-09-12 (main; V2 branch same day) | MIT | Only if user lets the chat agent act (heartbeat/cron); no built-in decision loop | Yes via tool handlers (Binance futures, Hyperliquid, Polymarket, Kalshi, Solana DEX...) | `DRY_RUN=true` opt-in; live by default if keys present | Not defined; LLM-invoked close tools; separate rule-based bracket/trigger modules exist | per-order notional cap ($1000 default) + circuit breaker/kill switch gate; no leverage cap found in agent path | L2 as shipped (L3 only via user-authored HEARTBEAT/cron) |
| wquguru/nof0 | 2025-12-07 | none | Yes, 1 call per trader per 3-5 min | Yes: Hyperliquid (go SDK client) | Hyperliquid testnet default; sim provider exists | LLM sets SL/TP, code submits best-effort and ignores errors | leverage cap, min R:R, min confidence, max positions, margin cap, per-trade USD cap | L3 |
| SnowingFox/open-nof1.ai | 2025-10-28 (metadata said push 2026-04-01; not seen on main) | none in tree (README says MIT, links missing `LICENSE`) | Yes, but only logs decision to DB | No: `buy()`/`sell()` are empty stubs | n/a (ccxt sandbox flag defined, never used for orders) | n/a | schema only: leverage 1-20 | L2 |
| 195440/nof1.ai | 2026-05-15 | AGPL-3.0 (`LICENSE`) | Yes (default strategy `ai-autonomous`), multi-step tool loop | Yes: Gate.io futures, OKX | Gate testnet via `GATE_USE_TESTNET` (example file sets true) | Dual: LLM can close; code SL, trailing, partial-profit monitors every 10 s | max leverage, max positions, exposure cap, drawdown no-new-entry, account stop-loss that closes all and exits process | L3 |
| 0xethanq/astra-quant-agent | 2026-10-04 | present (`LICENSE`) | Yes, 1 decision run/15 min + optional council | Yes: OKX only | OKX demo default (`ASTRA_OKX_ENV=demo`) | Mixed: exchange-attached TP/SL, code ratchet/time stop, LLM tighten/close commands | leverage clamp, risk-per-trade, min R:R, confidence gate, daily-loss breaker, black-swan sentinel | L3 (L4 partly) |
| galleonlabs/hypergrok-trading-desk | 2026-11-12 | MIT | Agents propose tickets; human approves each by id | Not in repo: instructions for external agent to call Hyperliquid SDK | Testnet-first protocol | Mandatory exchange-resting stop (as instruction text) | Written in markdown as LLM Risk Manager rules; one regex "ask" hook | L2 |
| Senpi-ai/senpi-skills | 2026-11-13 | MIT | No in open code: 343 `decision_mode: rule` entries, 0 `llm` | Not in repo; proprietary `@senpi-ai/runtime` + MCP | not determinable | Deterministic DSL ratchet in runtime config | `risk.guard_rails` in YAML (daily loss, drawdown halt, max entries) enforced by closed runtime | L1 (open code) |
| etrobot/open-alpha-arena | 2026-08-03 | none in tree (README says MIT) | Yes, 1 call per account per 5 min | No: simulated in local SQLite | Paper only by design | Simulated | leverage bound 1..`CRYPTO_MAX_LEVERAGE`; margin monitor (simulated) | L2-equivalent (paper) |

### Inferences
- "Autonomous" in marketing is mostly L3 (closed loop, fixed prompt). Where risk limits exist they are hard-coded only in nof0, astra, 195440; NoFx enforces some and leaves daily-loss as a stub.
- Last-commit dates from `git log` on the default branch differ from the search-API "pushed" dates for CloddsBot (09-12 vs 11-13) and SnowingFox (10-28 vs 04-01); push dates likely reflect other branches or tags.

### Gaps
- No repo was executed, so none of the above is runtime-verified.
- No exchange-side confirmation of testnet/live endpoints beyond config flags.

---

## NoFxAiOS/nofx (Go, AGPL-3.0)

### Takeaway
A true closed-loop LLM trader (L3): one LLM call per cycle produces open/close decisions that code validates and sends to the exchange. Position count, leverage and size caps are enforced in code, but the "daily loss / pause" control is a dead variable, so there is no real kill switch beyond stopping the trader.

### Cited Findings
- (1) LLM decides: `kernel.GetFullDecisionWithStrategy` is called each cycle (`trader/auto_trader_loop.go:~119`) and does exactly one `mcpClient.CallWithMessages(systemPrompt, userPrompt)` (`kernel/engine_analysis.go:115`). User supplies a strategy config (candidate coin source, risk config), the model chooses symbol, direction, size, leverage, SL and TP.
- (2) Real orders: Binance futures `NewCreateOrderService()` (`trader/binance/futures_orders.go:46`, go-binance in `go.mod:6`); Hyperliquid `ex.Order(ctx, order, defaultBuilder)` (`trader/hyperliquid/execution.go:31`, sonirico/go-hyperliquid `go.mod:20`); also per-exchange adapters in `trader/{bybit,okx,bitget,gate,kucoin,aster,lighter,indodax}`. Open/close entry points: `executeOpenLongWithRecord` and siblings in `trader/auto_trader_orders.go`; close via `CloseLong/CloseShort` (`trader/auto_trader_risk.go:144`).
- Paper/testnet: only `HyperliquidTestnet` (`trader/auto_trader.go:120`, used at `:331`); Lighter testnet disabled (`:348`). No paper/simulation mode in the trader path. Live is the default for any configured exchange.
- (3) Exit ownership: model must supply `stop_loss > 0` and `take_profit` (`kernel/engine_position.go:94-141`); after entry, code places exchange SL/TP orders (`trader/auto_trader_orders.go:162-168`, `:286-292`). Separately a deterministic drawdown monitor runs every minute and closes a position once price has moved +5% in favour and 40% of peak profit is given back (`trader/auto_trader_risk.go:15-22,34-60,100`). The model can also issue close decisions each cycle. A "signal-managed exit" mode removes the fixed TP (`trader/auto_trader_signal_policy.go`).
- (4) Hard limits in code: `enforceMaxPositions` marked "CODE ENFORCED" (`trader/auto_trader_risk.go:343-358`, called `auto_trader_orders.go:62,186`); max positions clamped to 1..8 (`store/strategy.go:16,116-120`); leverage clamped to <=20x with silent auto-reduction (`store/strategy.go:21-22`; `kernel/engine_position.go:60-64`); position size vs equity ratio capped (`store/strategy.go:24`, `kernel/engine_position.go:81-90`); min R:R (`store/strategy.go:25`). NOT wired: `MaxDailyLoss`/`MaxDrawdown` are documented "only as hints" (`trader/auto_trader.go:152-154`); `stopUntil` is read at `trader/auto_trader_loop.go:62` and reported at `auto_trader_decision.go:101` but is never assigned anywhere in non-test code (grep of `stopUntil\s*=` returned nothing); `dailyPnL` is only reset (`auto_trader_loop.go:75`) and reported (`auto_trader_decision.go:225`), never accumulated or compared. Practical consequence: no automated daily-loss halt or kill switch.
- (5) Keys: exchange API keys and private keys are stored via `crypto.EncryptedString` in the DB (`store/exchange.go:28-40`); `ENCRYPTION_README.md` describes RSA-4096 + AES-256-GCM transport/storage. JWT secret: server refuses to start with the old default `default-jwt-secret-change-in-production` (`config/config.go:15,96-97`; `start.sh:134-138` and `install.sh:91` generate one). `.env.example:38` still ships a placeholder `your-jwt-secret-change-this-in-production`. Withdrawal permission is not required by any order path I read. An optional pay-per-call data/LLM route ("claw402") takes a wallet private key (`trader/auto_trader.go:~142` `Claw402WalletKey`, `kernel/engine.go:196-200`) - a hot wallet that pays in USDC.
- (6) Red flags: (a) hard-coded Hyperliquid builder fee address `0x891dc6f0...faaf0d`, 5 bps added to orders, users approve it at connect time (`trader/hyperliquid/trader.go:66-76`, test `builder_fee_test.go:9-15`); (b) telemetry enabled by default (`config/config.go:78`) posts per-trade events (symbol, amount_usd, user_id, leverage) to Google Analytics Measurement Protocol with embedded measurement id/secret (`telemetry/experience.go:13-15,83-95`); (c) `install.sh` is a `curl | bash` installer pulling from raw.githubusercontent.com (`install.sh:5-9`). No base64/eval blobs, no postinstall scripts found in the Go tree. Previously reported default-admin / JWT issue (SlowMist, per `crypto_autonomous_agents.md`) appears mitigated by the MustInit check, but I did not verify the web layer.
- (7) Cycle interval default 15 min (`store/trader.go:29`); 1 LLM call/cycle -> about 96 calls/day, 2,880/month per trader. Built-in runway estimator assumes the same (`store/ai_charge.go:236-240`).
- (8) License: AGPL-3.0 (`LICENSE`). Last commit 2026-11-04 21:46 +0900 (shallow clone, one commit visible).

### Inferences
- L3 closed-loop agent; evidence of L4 (self-adaptation) not found in the paths read (grep for memory/reflection matched prompt/loop files but I did not read them).
- Because the pause/daily-loss controls are stubs, risk containment relies on exchange SL orders plus the model's own SL; a failed SL placement or model SL error is the main tail risk.
- Cost estimate (assumption: ~15k input + 1.5k output tokens per cycle; cheap model ~$0.3/$1.1 per M tokens, frontier ~$3/$15): about 43M in + 4M out per month -> roughly $15-20 (cheap) to $190-200 (frontier) per trader per month, before data subscriptions.

### Gaps
- Did not read web/API auth handlers (`api/`), so dashboard exposure/default credentials not verified.
- Did not confirm what happens when `SetStopLoss` fails (error branch at `auto_trader_orders.go:162-170`).
- Real prompt size per cycle depends on strategy config (candidate count x timeframes); estimate is a guess.

---

## alsk1992/CloddsBot (TypeScript, MIT)

### Takeaway
Clodds is a very large (630 `.ts` files) chat-assistant framework: Claude with ~hundreds of trading tools. There is no built-in "LLM decides trades on a schedule" loop for crypto; autonomy exists only if the user writes a heartbeat/cron task. Live orders are the default when keys are set (dry-run is opt-in) and the agent path has an order-size cap and a circuit-breaker gate, but I found no leverage cap on that path.

### Cited Findings
- (1) Who decides: the system prompt is a reactive prediction-market chat assistant, not a trader (`src/agents/index.ts:217-231`). Autonomy mechanism: a heartbeat service reads `HEARTBEAT.md` and runs it through the agent, default every 30 minutes, quiet hours 22:00-08:00 (`src/automation/heartbeats.ts:1-14,26-30,66`). Rule-based modules (arbitrage opportunity executor `src/opportunity/executor.ts` default `dryRun: true` at `:140`; `src/strategies/crypto-hft`; copy-trading; DCA/TWAP/bracket in `src/execution/`) do not use the LLM to decide.
- (2) Orders: tool definitions `binance_futures_long/short/close` (`src/agents/index.ts:4349-4385`) route to handlers (`src/agents/handlers/binance.ts:109-142,223-225`) calling `binanceFutures.openLong(...)`; Hyperliquid equivalents `src/agents/handlers/hyperliquid.ts:158-162,333`; futures adapter `src/execution/futures.ts` (1,869 lines; Binance, Bybit, Hyperliquid, MEXC). Dry-run: `DRY_RUN === 'true'` opt-in (`binance.ts:24`, `hyperliquid.ts:30`); default is live whenever `BINANCE_API_KEY/SECRET` exist. A separate paper-trading handler exists (`src/agents/handlers/paper-trading.ts`, not read in depth).
- (3) Exits: no single owner. The agent can call `*_close` tools; deterministic bracket/trigger/position-manager modules exist (`src/execution/bracket-orders.ts`, `trigger-orders.ts`, `position-manager.ts`) but are not tied to the LLM decision flow in the handler path I read.
- (4) Limits: `guardTrade` -> `validatePreTrade` checks circuit breaker/safety-manager `canTrade()` and a notional cap (`src/agents/handlers/trading-guard.ts`; `src/trading/pre-trade.ts:44-80`); gateway installs gate with `maxOrderSize ?? 1000` USD (`src/gateway/index.ts:638,670-673`). Close orders skip the size cap (`skipSizeLimit`, `binance.ts:120`). Risk engine has kill-switch and daily-loss concepts (`src/risk/engine.ts:177`, `src/risk/dashboard.ts:36,48,132`; default daily loss limit 500). Leverage: tool schema says "1-125" (`src/agents/index.ts:4357`); I found no leverage cap in `execution/futures.ts` beyond `safeLeverage` sanitising >0 (`:1845`). README advertises "perpetual futures up to 200x" (`package.json:4`).
- (5) Keys: env vars (`BINANCE_API_KEY/SECRET`, `HYPERLIQUID_PRIVATE_KEY` at `src/skills/executor.ts:379-381`, `src/skills/bundled/dca/index.ts:194`); per-user credentials stored AES-256-GCM encrypted in the DB, requires `CLODDS_CREDENTIAL_KEY` (`src/credentials/*.ts:44,52-55`); also supports Solana wallet keys and EVM wallets. No withdrawal-key requirement seen, but Hyperliquid/Solana/Polymarket use raw private keys.
- (6) Red flags: `postinstall` runs two local patch scripts (read; benign: probe bigint-buffer native binary, patch anchor export) plus downloads a Hugging Face embedding model via `@xenova/transformers` (`package.json:19`, `scripts/fix-native-bindings.js`). Very broad dependency surface (Drift, Jupiter, Kamino, Bittensor, discord.js, puppeteer...). No eval/atob blobs in non-skill code (only a docs string in `src/skills/bundled/shield`). No hard-coded fee-recipient address found. Telemetry module posts only to user-configured OTLP/Jaeger/Zipkin endpoints (`src/telemetry/index.ts:388-463`). Star growth (3.1k in <10 months) is flagged in `crypto_autonomous_agents.md`; not a code finding.
- (7) Cost: if HEARTBEAT.md is used, at most ~28 heartbeats/day in the 14 h awake window (30 min x 14 h) -> about 840 agent turns/month, each possibly several tool-call rounds with a large skills prompt. Assumption 20k in/1k out per turn: ~17M in -> roughly $5-60/month. Reactive use costs per message.
- (8) License MIT (`LICENSE`, `package.json:57`). Last commit on `main` 2026-09-12 04:58 +0100 (`c930628`); `V2` branch tip also 2026-09-12; `gh search` push date 2026-11-13 not reproduced on branches I fetched.

### Inferences
- As shipped: L2 (assistant with live-order tools, human-triggered). Becomes L3 only when a user writes a standing instruction (HEARTBEAT.md/cron), at which point the LLM's own judgement drives orders with only the $1000/order cap and breaker as guardrails.
- Default-live-if-keys-present plus no leverage cap plus 200x marketing is a poor safety posture for an LLM-driven path.

### Gaps
- Did not trace `execution/position-manager.ts` into the agent flow; did not read `paper-trading.ts` or the Rust directory.
- Did not verify what `config.trading.maxOrderSize` defaults to outside the gateway (1000 in gateway).
- Official owner unconfirmed (several forks); I cloned alsk1992/CloddsBot only.

---

## wquguru/nof0 (Go backend + Next.js, no license)

### Takeaway
Real L3 agent (LLM decision every 3-5 min, per trader) wired to Hyperliquid with testnet on by default and a code-side validator that rejects over-leveraged or low-R:R decisions. Weakness: SL/TP placement errors are discarded, and there are no daily-loss/kill-switch controls. No license file and stale (Dec 2025).

### Cited Findings
- (1) LLM decides: `BasicExecutor.GetFullDecision` calls `e.llm.ChatStructured` once (`go/pkg/executor/executor.go:88,139`); output must match `go/schemas/decision_output.json`. Models via ZenMux gateway (`go/etc/llm.yaml:1,32`). Two example traders: 3 min and 5 min intervals (`go/etc/manager.yaml:19,42`; executor default `decision_interval: 3m` `go/etc/executor.yaml`).
- (2) Orders: `ExchangeProvider.PlaceOrder` (`go/pkg/manager/manager.go:810`) and `ClosePosition` (`:648`); Hyperliquid provider over a bespoke signed client (`go/pkg/exchange/hyperliquid/{client,order,provider}.go`, go-ethereum for signing `go.mod`). Testnet: `testnet: true` default (`go/etc/exchange.yaml:11`), traders use `exchange_provider: hyperliquid_testnet` (`manager.yaml`); an in-process simulator exists (`go/pkg/exchange/sim/provider.go`).
- (3) Exits: LLM provides `stop_loss` and `take_profit` and the validator checks geometry/R:R (`go/pkg/executor/validator.go:28-50`). Code then submits reduce-only trigger orders "best-effort" and ignores the returned errors: `_ = p.SetStopLoss(...)`, `_ = p.SetTakeProfit(...)` (`go/pkg/manager/manager.go:826-831`). A failed SL leaves a naked position with no alert in that path.
- (4) Limits in code: leverage cap per coin class and exchange asset max (`go/pkg/executor/validator.go:55-69`); min confidence 75 / min R:R 3.0 / max positions 4 (`executor.yaml`); `enforceSecondaryRisk` for `max_position_size_usd` and `max_margin_usage_pct` (`manager.go:1289-1311`); cap on new opens per cycle (`manager.go:504-513,1737`). Allocation between traders is "performance_based" with 10% reserve (`manager.yaml`). No daily-loss halt or kill switch found (grep for daily/kill/drawdown in `pkg/manager` only returned analytics fields).
- (5) Keys: `HYPERLIQUID_PRIVATE_KEY` read from env into config (`go/etc/exchange.yaml:7`); `.env.example` ships a dummy `ffff...` key and a sample main address (`go/.env.example`), plus Postgres creds `nof0:nof0@localhost` (default local DB credentials). Hyperliquid API-wallet pattern via `main_address`/`vault_address` supported, so a trade-only agent key can be used.
- (6) Red flags: none obfuscated found. Prompt submodule pulled from a personal gist (`.gitmodules`: `gist.github.com/wquguru/...`) - supply-chain note. README badges say backend 70%, engine 80% done. `.gitignore` excludes env. No `LICENSE` file in the tree (all rights reserved by default).
- (7) Cost: 3 min trader = 480 calls/day, 5 min trader = 288/day -> 768/day = ~23,000 calls/month for the two example traders. Assume 8k in + 1k out: 184M in + 23M out -> roughly $80 (cheap model) to $900 (frontier) per month. Default model `gpt-5` (`go/etc/llm.yaml:7`), traders configured to `deepseek-chat` (`manager.yaml`).
- (8) License: none. Last commit 2025-12-07 16:58 +0800.

### Inferences
- L3, testnet by default. The documented "performance-based allocation" is capital routing between configured traders, not self-modification; L4 not evidenced.

### Gaps
- Did not verify the Hyperliquid client's mainnet path or whether `UpdateLeverage` failure is handled (`manager.go:719` also uses `_ =`).
- ~11 months stale; no tests of live behaviour reviewed.

---

## SnowingFox/open-nof1.ai (Next.js) vs 195440/nof1.ai (Node/TS)

### Takeaway
These two share a name but not behaviour. SnowingFox/open-nof1.ai never places an order: the LLM output is stored in a database and `buy()`/`sell()` are empty functions (L2). 195440/nof1.ai is a full L3 trader with the most extensive code-level risk machinery of all eight repos, but ships aggressive defaults (25x in the example env) and an unauthenticated read-only dashboard API.

### Cited Findings
SnowingFox/open-nof1.ai
- (1) LLM decides BTC buy/sell/hold via `generateObject` with DeepSeek-R1 on OpenRouter (`lib/ai/run.ts:21-41`, `lib/ai/model.ts:15`); schema allows `leverage` 1-20 (`run.ts:~34`).
- (2) No orders: `export function buy() {}` (`lib/trading/buy.ts:1`) and `export function sell() {}` (`lib/trading/sell.ts:1`); the decision path only does `prisma.chat.create(...)` (`lib/ai/run.ts:77+`). `lib/trading/binance.ts:5-11` creates a ccxt Binance futures client with `setSandboxMode(process.env.BINANCE_USE_SANDBOX === "true")`, used for market/account data only; grep for `createOrder` in the tree found nothing.
- (3)/(4) Exits and limits: none implemented (stop-loss/take-profit values are written to DB as `adjustProfit`, `run.ts:~115-135`).
- (5) Keys: env (`BINANCE_API_KEY/SECRET`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`). Cron endpoints guard with a JWT signed by `CRON_SECRET_KEY` (`app/api/cron/3-minutes-run-interval/route.ts:5-18`); an unset secret makes `jwt.verify` throw, i.e. fails closed.
- (6) Red flags: none. Dependencies standard (`ai`, `ccxt`, prisma).
- (7) Cron every 3 min (`cron.ts:46`) plus metrics every 10 s (`cron.ts:24`, comment says 20 s). 14,400 R1 calls/month; assume 6k in/3k out -> ~86M in + 43M out -> roughly $140 on R1-class pricing. Moot since nothing trades.
- (8) No LICENSE file in tree though README line 209-211 says "MIT ... See LICENSE". Last commit 2025-10-28 18:14 +0800 (search API's 2026-04-01 push not on default branch).

195440/nof1.ai
- (1) LLM decides: VoltAgent `Agent` with tools `openPositionTool`, `closePositionTool`, `cancelOrderTool`, news, indicators, etc. (`src/agents/tradingAgent.ts:1925-1944`); 9 selectable strategies, default `TRADING_STRATEGY=ai-autonomous` ("no strategy advice, only hard risk bottom line", `src/strategies/aiAutonomous.ts:~20-40`, `.env.example`); multi-agent "aggressive-team" and "multi-agent-consensus" options; recent closed-trade summaries are fed back (`src/agents/tradeHistoryUtils.ts:1-48`) - shallow feedback, no self-modification found.
- (2) Orders: `GateClient.placeOrder` -> `futuresApi.createFuturesOrder` via gate-api (`src/services/gateClient.ts:185,321`) and an OKX client (`src/services/okxClient.ts`), abstracted in `src/services/exchangeClient.ts`. Tools in `src/tools/trading/tradeExecution.ts:122 (open), 759 (close), 1179 (cancel)`. Testnet: `GATE_USE_TESTNET=true` switches basePath to `api-testnet.gateapi.io` (`gateClient.ts:43-45`); `.env.example` defaults to true. OKX demo not checked.
- (3) Exits: dual. LLM can close; code-level monitors run `setInterval` every 10 s for stop-loss (`src/scheduler/stopLossMonitor.ts:642-644`) plus trailing stop (`trailingStopMonitor.ts:779`) and partial take-profit (`partialProfitMonitor.ts:555`), with per-strategy thresholds by leverage band (`stopLossMonitor.ts:81-100`). Strategy `ai-autonomous` declares `enableCodeLevelProtection = true` plus AI override allowed. `EXTREME_STOP_LOSS_PERCENT=-30` and `MAX_HOLDING_HOURS=36` in `.env.example`.
- (4) Limits in code: tool input schema caps leverage at `MAX_LEVERAGE` and takes min with strategy max (`tradeExecution.ts:128,151`); `MAX_POSITIONS` check (`:166`); total exposure <= equity x MAX_LEVERAGE (`:283-288`); drawdown from peak >= 15% blocks new opens (`:258`, `src/config/riskParams.ts:52`); account stop-loss/take-profit in USDT: `checkAccountThresholds` -> `closeAllPositions` then `process.exit(0)` (`src/scheduler/tradingLoop.ts:1094,1147-1156,1239`) - a real kill switch (example `ACCOUNT_STOP_LOSS_USDT=50` on a 1000 balance). `ACCOUNT_DRAWDOWN_FORCE_CLOSE_PERCENT` is defined (`riskParams.ts:55`) but referenced nowhere else (grep) - dead config. Example env sets `MAX_LEVERAGE=25`, code fallback 15 (`riskParams.ts:34`); defaults are aggressive.
- (5) Keys: `GATE_API_KEY/SECRET`, `OKX_*`, `OPENAI_API_KEY` in env (`.env.example`); no withdrawal call found in `src/services/*`. Dashboard: Hono routes `/api/account`, `/positions`, `/history`, `/trades`, `/logs`, `/stats`, `/prices`, `/strategy` are unauthenticated GETs (`src/api/routes.ts:66-405`); `POST /api/close-position` requires `CLOSE_POSITION_PASSWORD` env, fails if unset (`routes.ts:446-470`). An IP blacklist middleware exists (`src/middleware/ipBlacklist.ts`). Exposing the port leaks balances/positions/reasoning.
- (6) Red flags: `package.json` repository/homepage/bugs point to `github.com/yourusername/open-nof1.ai` (placeholder, not the real repo). News fetch from `https://api.gatemcp.ai/mcp/news` (`src/services/newsClient.ts:35`) - third-party host that receives requests but no secrets as far as read. No eval/base64 blobs found; no postinstall.
- (7) Cycle: `TRADING_INTERVAL_MINUTES` default 5 (`tradingLoop.ts:1170,1808-1820`; example 20 with swing strategy). Each cycle is one agent run with a multi-step tool loop; I could not read a `maxSteps` setting, so assume 5-8 model steps. At 5 min: 8,640 runs x ~6 steps = ~52k calls/month, avg ~10k input -> ~520M in + ~40M out -> roughly $200 (cheap) to $2,200 (frontier). At 20 min (swing), divide by 4. Default model `deepseek/deepseek-v3.2-exp` on OpenRouter (`tradingAgent.ts:1873,1925`).
- (8) AGPL-3.0 (`LICENSE`, `package.json`). Last commit 2026-05-15 09:49 +0800.

### Inferences
- SnowingFox/open-nof1.ai: L2 as shipped (decision logger / UI); it would need a developer to write the order code. Do not count it as an autonomous trader.
- 195440/nof1.ai: L3; closest to "LLM picks, code guards" among the Alpha-Arena clones, with a working account-level kill switch. Cost at 5 min cadence is the dominant concern.

### Gaps
- `maxSteps`/tool-loop bound not found (VoltAgent default unknown), so cost range is wide (>3x uncertainty).
- OKX demo-mode handling and `okxClient.ts` order path not read.
- Whether SnowingFox has later branch commits (search API push 2026-04-01).

---

## 0xethanq/astra-quant-agent (Python, FastAPI, OKX only)

### Takeaway
L3 with the most explicit "LLM proposes, deterministic Python gates" design: OKX demo by default, refuses to trade without keys, clamps leverage, enforces R:R/confidence/daily-loss gates, uses exchange-attached TP/SL. Reflection job (4x/day) suggests L4 intent but I did not confirm the memory is fed back into the live prompt. Notable red flags: documented default admin password on a 0.0.0.0-bound dashboard and hard-coded exchange referral links.

### Cited Findings
- (1) LLM decides: live script `scripts/ai_factor_trader.py` is respawned every 15 minutes (`astra_gateway/scheduler.py:35`, docstring `scripts/trader/__init__.py`); AI returns portfolio decisions with leverage and confidence; optional multi-role "council" debate (`astra_backend/council/debate.py`, `council_manager.py`, disabled by default `council_manager.py:155`). LLM endpoint is any OpenAI-compatible base URL (`astra_backend/config.py:45`, `env.example` `LLM_BASE_URL`).
- (2) Orders: `okx_rest.place_order` (`scripts/okx_rest.py:281`) called from the OKX adapter (`astra_backend/exchanges/okx.py:282-330`, call at `:314`); TP/SL carried as OKX `attachAlgoOrds` and verified afterwards (`astra_backend/okx_trade_service.py:125-231`, `exchanges/okx.py:25,44`); demo mode adds header `x-simulated-trading: 1` (`scripts/okx_rest.py:249`). Default `ASTRA_OKX_ENV=demo`, and "without a complete key trio ... the system is NOT READY and refuses to trade" (`env.example:12-22`).
- (3) Exits: mixed. Mechanical TP / three-stage trailing ratchet / ATR time stop with no LLM (`scripts/trader/position_exit.py:1-25`, `manage_position_tp_and_trailing` `:59`); LLM position commands (tighten stop / close) executed in `scripts/trader/position_mgmt.py:39 execute_ai_position_management`; exchange-resting protective orders (`scripts/trader/cloud_protection.py`, `venue_protection.py`).
- (4) Limits in code (env-overridable, single source `scripts/risk_constants.py`): leverage clamp 2x-5x applied to the AI's output and further tightened per instrument (`env.example:49`, `scripts/trader/leverage.py:28`, call `entry_execution.py:206`); per-order margin 20% of balance, per-asset 30%/600 USDT, risk per trade 2% of balance, min R:R 2.0, max 3.5, min confidence 68, daily loss cap min(150 USDT, 5% equity) (`env.example:35-67`, `risk_constants.py:82-84,181-185`); circuit breaker = black-swan sentinel + breaker file + daily-loss check (`scripts/trader/circuit_guard.py:92-150`, evaluated every cycle at `cycle_stages.py:343`). Note: this breaker gates new entries ("open-position breaker"); it is not an exchange-wide flatten.
- (5) Keys: OKX key/secret/passphrase for separate DEMO and LIVE sets via env or `/admin` UI stored Fernet-encrypted (`env.example:14-29`; Fernet usage `astra_backend/backup_secrets.py:8,30`); "V5 API Key signing is the ONLY connection method". Withdrawal permission not needed by order path. Default credentials: `env.example:160` sets `ASTRA_ADMIN_TOKEN=R20admin888888` with comment "Default superadmin password", `setup_wizard.py:127-129,278` defaults to `AstraAdmin888888`, and `DASHBOARD_HOST=0.0.0.0` (`env.example:155`). Anyone reaching the dashboard port of an unchanged install can authenticate as admin.
- (6) Red flags: hard-coded exchange referral/invite links (OKX, Binance, Gate) in `astra_backend/config.py:65-67,101-103` - revenue incentive, overridable by env; optional "strategy plaza" sharing to `https://hub.astraquant.tech` is disabled by default (`astra_backend/plaza_share.py:26,32`) and has a secrets scrubber (`:37-52`); outbound QQ bot calls (bots.qq.com) for notifications; OKX public-data host fallback list `www.okx.com -> aws.okx.com -> alt-venue` (`env.example` comment, `exchanges/okx.py:14`). No eval/exec/pickle/base64 blobs found in non-test code (the only `b64decode` is in `qq_bind.py:128-129` for QQ secret decryption). `requirements.txt` pinned/regular packages, no typosquats. Very large, heavily commented (Chinese) code base: 27.6k lines in the two packages scanned.
- (7) Cadence: trader every 15 min (`scheduler.py:35`) = 2,880 runs/month; news harvester every 10 min and factor library every 60 s run without LLM or with small LLM use (not measured); self-improvement LLM post-mortem 4x/day at 02/08/14/20 (`scheduler.py:41`, ~120 calls/month). Assume 12k in + 2k out per trader run: ~35M in + ~6M out -> roughly $15 (cheap) to $190 (frontier) per month; council mode multiplies by the number of roles.
- (8) License file present (`LICENSE`; type not read). Last commit 2026-10-04 04:02 +0800.

### Inferences
- L3, trending to L4: `scripts/self_improvement_engine.py` writes LLM post-mortem lessons to `data/ai_trading_memory.json` / `AI_TRADING_MEMORY.md` (`:31-40`; mirrored by `scripts/evolution_shield.py:52,330-397`), and the `evolution/` package reviews lessons (`lesson_health.py`, `memory_review.py`). Whether the live trader prompt consumes these files is unconfirmed (no match for "memory" in `ai_factor_trader.py`; `ai_brain_trader.py:161-162` defines the paths).
- The documented default admin token is the largest practical security issue for a self-hosted install.

### Gaps
- Did not read `scripts/ai_factor_trader.py` end-to-end or `routers/` auth code to confirm the admin token is enforced as documented.
- License type not read; which OKX endpoints (`okx_rest.py`) beyond order placement are used not exhaustively audited.

---

## galleonlabs/hypergrok-trading-desk (Markdown plugin, MIT)

### Takeaway
Not an autonomous bot in code at all: 17 skills, 7 role prompts and one Python hook for Claude Code/Grok/Cursor-style agents. Every exchange write needs a ticket, an LLM "Risk Manager" PASS and the user's approval by id, so effective autonomy is L2 (human-in-the-loop advisor/executor). Its risk limits are instructions to an LLM, not compiled controls.

### Cited Findings
- (1) Decision origin: agents (`agents/*.md`: desk-lead, market-analyst, research-analyst, strategist, risk-manager, execution-trader, trade-reviewer) propose; the user approves "by id, in chat, after the ticket was shown, inside the ticket's expiry" (`skills/desk-execution-protocol/SKILL.md:18`; "Never send without a PASS and approval by id" `:85`; routines/schedules may only alert and draft `:89`).
- (2) Orders: no order code in the repo. Skills tell the agent to use the `hyperliquid-python-sdk==0.24.0` (`skills/hyperliquid-setup/SKILL.md:37`); entry plus stop plus take-profit in one `normalTpsl` order (`desk-execution-protocol/SKILL.md:31`). Testnet-first: "Mainnet is never assumed" (`:26`), rehearse every new action type on testnet (`:77`). `package.json` description says "read-only Python tools"; the repo contains only `scripts/check_public_template.py` and `hooks/exchange_write_gate.py`.
- (3) Exits: "exchange-resting stop on every entry: mandatory" (`skills/desk-risk-limits/SKILL.md:~20`, section 0). Standing approval may cover reduce-only protective stops on any network, but never a mainnet send that can open or increase exposure (`skills/desk-operating-model/SKILL.md:83`).
- (4) Limits: ceilings table - max 2% risk/trade, 6% total open risk, 20x leverage, -10% daily loss stop (`skills/desk-risk-limits/SKILL.md` section 0); enforced by the Risk Manager LLM role plus a PreToolUse hook that regex-matches Hyperliquid write calls and returns "ask" (`hooks/exchange_write_gate.py:1-18,35-60`; `hooks/exchange-write-gate.json`). The hook's own docstring says it is a backstop that "does not follow imports, expand globs" so writes hidden in helper modules are missed. There is no deterministic position-size/leverage clamp in code.
- (5) Keys: trade-only Hyperliquid API wallet (separate agent key), read from `HYPERLIQUID_PRIVATE_KEY` env or a `chmod 600 ~/.hyperliquid/api-wallet.key` fallback (`skills/hyperliquid-setup/SKILL.md:68-95,103,135`); the account address is public. Skills forbid withdraw/transfer/builder-fee approval (`desk-execution-protocol/SKILL.md:87`). A Hyperliquid API wallet cannot withdraw by design (platform property, not verified here).
- (6) Red flags: none obfuscated. CI publishes to npm via OIDC trusted publishing (`.github/workflows/publish.yml:1-30`). `docs/GROK_BOT_TEMPLATE.md` and `template/grok-bot.json` target a hosted Grok Bot product.
- (7) No scheduled LLM loop in repo; cost is per user chat turn. Schedules/routines can only alert.
- (8) MIT (`LICENSE`, `package.json`). Last commit 2026-11-12 07:28 +0000; version 1.7.2.

### Inferences
- L2: a well-designed human-approval workflow. The 518 stars and activity are for documentation/prompt engineering; autonomy ceiling is set by the host agent's permissions, not this repo.

### Gaps
- Behaviour depends on the host (Grok Bot / Claude Code) honouring the hook and "native approval gate"; not testable from code.

---

## Senpi-ai/senpi-skills (Python skills + YAML strategies, MIT)

### Takeaway
The open repo is skills plus 169 strategy runtime configs whose entry decisions are deterministic `scan()` scripts (`decision_mode: rule`, 343 occurrences, 0 `llm`). The LLM chats, analyses, picks and deploys templates; the order engine, DSL exits and model are in a proprietary runtime/MCP backend, so autonomy and risk limits cannot be audited from source. Level in open code: L1 (rule executor with signal inputs), L2-L3 only for the chat layer if the platform lets an agent deploy without confirmation (not verified).

### Cited Findings
- (1) The README states "Nothing in this repo places an order directly - it goes through the supervised runtime" and "strategies export `scan(inputs, ctx)`; the runtime owns everything downstream" (`README.md:~50`). Strategies explicitly removed LLM gates: Hawk "v2 LLM entry ... gate was pass-through" -> `decision_mode: rule` (`strategies/hawk/main/runtime.yaml:~70`, `scanners/scan.py:46-48`); Jackal "v2 LLM gate (decision_mode: llm, min_confidence 7) is replaced by decision_mode: rule" (`strategies/jackal/main/runtime.yaml:7-10`). Counts: `grep decision_mode:` over `strategies/**/runtime.yaml` -> 343 `rule`; 169 runtime files. Inputs include Hyperliquid leaderboard / "smart money" data via Senpi MCP (`https://mcp.prod.senpi.ai`, `https://hyperliquid-traders.prod.senpi.ai`; host counts from a grep of `*.py`).
- (2) Orders: via closed `@senpi-ai/runtime` plugin installed with `openclaw plugins install @senpi-ai/runtime` (`README.md:167`, `senpi-trading-runtime/SKILL.md:78`); entry order type `FEE_OPTIMIZED_LIMIT` with taker fallback (`strategies/hawk/main/runtime.yaml` actions). Deploy/close scripts `senpi-strategy-ops/scripts/deploy.py`, `close.py` call the MCP. No exchange SDK in the repo; testnet/paper mode not determinable.
- (3) Exits: deterministic "DSL" (two-phase ratchet stop, hard timeout, weak-peak cut) declared in YAML, executed by the runtime, e.g. Hawk `max_loss_pct: 5.0`, `hard_timeout`, wide Phase 2 (`strategies/hawk/main/runtime.yaml:~88-135`). Not LLM-owned.
- (4) Limits (YAML, runtime-enforced, closed): `risk.guard_rails` daily_loss_limit_pct 15, max_entries_per_day 2, max_consecutive_losses 3, drawdown_halt_pct 20, cooldowns; `leverage_max: 5`, `max_slots: 1`, `margin_pct: 20` (`strategies/hawk/main/runtime.yaml:135-146`, `strategies/hawk/strategy.yaml:~25-30`). I cannot verify the closed runtime enforces them.
- (5) Keys/custody: client uses `SENPI_AUTH_TOKEN` env for MCP auth (`senpi-strategy-discover/scripts/mcp_client.py:7,21`). Wallets are Senpi-managed: the skill says the agent "trades only with their permission and can never withdraw, and only they hold the private key" (`senpi-deposit-withdraw-transfer/SKILL.md:138-139`) - a vendor claim, not verifiable from this repo. Money-in goes via a funding card; withdrawals are app-only (`:49,62`).
- (6) Red flags: none obfuscated (675 `.py` files grepped for eval/exec/base64: none outside tests). Closed runtime is the trust anchor. `CLAUDE.md:166-188` documents that `npm install @senpi/runtime` returns 404 if mis-named (name typosquat risk for users, not malware in repo). Outbound hosts in code: senpi.ai, mcp.prod.senpi.ai, hyperliquid-traders.prod.senpi.ai, agents.senpi.ai, api.hyperliquid.xyz, stats-data.hyperliquid.xyz, raw.githubusercontent.com. Fee model: "Senpi trading fee (none on a paid plan)" (`README.md`, `senpi-account-status`).
- (7) LLM cost: not in the decision loop for strategies (scan interval 300 s is plain Python, `runtime.yaml`); chat/tool turns consume Senpi plan "AI credits" (platform-priced, not in repo).
- (8) MIT (`LICENSE`, Senpi AI Inc, 2026). Last commit 2026-11-13 10:36 -0600.

### Inferences
- The "autonomous trading" here is rule-based copy/momentum strategies run by a vendor platform; the LLM is an interface and strategy picker. Under the framework this is L1 for the open strategies. Calling it "AI-autonomous" overstates what the code shows.

### Gaps
- Closed runtime, model ("Samurai") and MCP backend are not in the repo: order sizing, real leverage caps, testnet availability and kill-switch behaviour unverified.
- Did not read `senpi-strategy-author` to see whether LLM-authored strategies can be deployed without human confirmation.

---

## etrobot/open-alpha-arena (TypeScript, Hono + Vite)

### Takeaway
An Alpha-Arena-style arena that is paper-only: an LLM chooses open/close/hold for simulated accounts every 5 minutes; fills are simulated in a local SQLite DB using Hyperliquid prices from ccxt without credentials. No real orders can be sent. There is a random-trading fallback.

### Cited Findings
- (1) LLM decides: `callAIForDecision` posts a prompt to the account's configured OpenAI-compatible endpoint (`backend/src/services/aiDecision.ts:215-350`, `max_tokens: 1000`, 3 retries); decision `{operation: open|close|hold, symbol, direction, target_portion_of_balance, reason}` is parsed and executed (`backend/src/services/tradingCommands.ts:148-200`). Scheduler: AI job every 300 s (`services/startup.ts:35,86-107`), first run immediately.
- (2) Orders: simulated only. `services/hyperliquid.ts:60-63` builds `new ccxt.hyperliquid({sandbox:false, enableRateLimit:true})` with no key/wallet (market data only); orders go through `createOrder` in `services/orderMatching.ts:39` and `services/orderExecutorLeverage.ts` against DB balances; leverage 1..`CRYPTO_MAX_LEVERAGE` (`orderExecutorLeverage.ts:73-75`). README confirms "Paper Trading" and says real trading is left to the user to implement (`README.md:10,17`).
- (3) Exits: no SL/TP; LLM issues close; a 5 s margin monitor liquidates simulated positions (`services/startup.ts:61`, `scheduler.ts:129`).
- (4) Limits: only leverage bound and balance; no daily-loss/kill switch needed since no real funds.
- (5) Keys: LLM `api_key`/`base_url` stored per account in the `accounts` table in plaintext (`backend/src/db/schema.ts:57-58`); placeholder keys `default-key-please-update-in-settings` treated as demo (`aiDecision.ts:20-24`). A single `default` user is auto-created and all other users deleted at seed (`db/seed.ts:42-78`) - not a multi-user hardened service.
- (6) Red flags: none obfuscated. Outbound: news RSS `https://coinjournal.net/news/feed/` (`services/newsFeed.ts:7`). Fallback to random trades if AI job scheduling fails (`startup.ts:36-45`), which can produce misleading "AI" results.
- (7) Cost: one call per active account per 5 min = 8,640/month/account; assume 3k in + 1k out: ~26M in + 8.6M out -> roughly $15-20 (cheap) to $200 (frontier) per account per month.
- (8) No LICENSE file (README says MIT, `README.md:92`). Last commit 2026-08-03 15:52 +0800.

### Inferences
- Under the framework this is L2-equivalent (no real order path), useful as a safe testbed for prompts.

### Gaps
- Did not read the frontend or auth/ws handlers; `PORT` 5611 exposure and auth not verified.

---

## Cross-repo comparison: who owns exits, risk and keys

### Takeaway
Exit and risk control quality varies more than "autonomy level": 195440/nof1.ai and astra have deterministic exit monitors and account-level breakers; nof0 and NoFx rely on exchange-side SL/TP whose prices the LLM chose (nof0 ignores placement errors; NoFx has no wired daily-loss halt). No repo requires withdrawal rights; Hyperliquid-based ones use API/agent wallets, and the CEX-based ones need trade-only keys by design (not enforced in code).

### Cited Findings
- Exit owner: NoFx - LLM prices, code places, plus code drawdown giveback close (`trader/auto_trader_risk.go:15-22`); nof0 - LLM prices, best-effort placement (`pkg/manager/manager.go:826-831`); 195440 - code monitors every 10 s plus LLM (`src/scheduler/stopLossMonitor.ts:642-644`); astra - exchange attach orders plus code ratchet plus LLM commands (`scripts/trader/position_exit.py:1-25`); Senpi - runtime DSL (`strategies/hawk/main/runtime.yaml`); Hypergrok - mandatory resting stop by instruction (`skills/desk-risk-limits/SKILL.md`).
- Kill switch / daily loss in code: working in 195440 (`tradingLoop.ts:1147-1156,1239`) and astra (`scripts/trader/circuit_guard.py:92-150`); present for CloddsBot via gate (`src/trading/pre-trade.ts:44-80`); declared but unwired in NoFx (`trader/auto_trader_loop.go:62`, no assignment of `stopUntil`); absent in nof0; delegated to closed runtime in Senpi.
- Safe-default posture: astra demo-by-default (`env.example:22`); nof0 testnet-by-default (`go/etc/exchange.yaml:11`); 195440 example env testnet-true (`.env.example`); NoFx and CloddsBot live-by-default when credentials exist (`trader/auto_trader.go:331`; `src/agents/handlers/binance.ts:24`).
- Default credentials / secrets: astra admin token `R20admin888888` in `env.example:160`; nof0 sample key `ffff...` and Postgres `nof0:nof0` in `.env.example`; NoFx placeholder JWT with startup refusal of the old default (`config/config.go:15,96`).
- Monthly LLM cost (assumption-based, per instance, running 24/7): NoFx at 15 min ~$15-200; nof0 two traders at 3/5 min ~$80-900; 195440 at 5 min ~$200-2,200 (20-min swing ~$50-550); astra ~$15-190; CloddsBot heartbeat only ~$5-60; SnowingFox ~$140 for no trading; open-alpha-arena ~$15-200 per account; Senpi strategies $0 LLM in loop (platform credits); Hypergrok per-use. Low end = DeepSeek-class pricing, high end = frontier pricing, both my assumptions; token sizes per cycle were not measured.

### Inferences
- If running cost exceeds 1-2% of account per month (advisor_framework section 2E), nof0 (two traders) and 195440 at 5-minute cadence on a frontier model are uneconomic for a small account; NoFx at 15 min is the cheapest of the full-loop agents.
- Prompt-injection exposure: 195440 (news/events tools) and astra (news sentiment harvester) feed external text into an order-capable agent; their code-level caps are the mitigation. CloddsBot has broad external ingestion (Discord/Telegram/web) feeding an agent with order tools and no leverage cap found.

### Gaps
- Backtest integrity, live performance, and star authenticity were out of scope for this code audit.
- Pricing for models used in cost estimates was not looked up; treat as order-of-magnitude.
