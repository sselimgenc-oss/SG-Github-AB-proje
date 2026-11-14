# New discoveries: autonomous LLM trading-agent repos missed by the earlier survey

Research date: 2026-11-15. Star counts, push dates and licenses are as returned by `gh search repos` on that date.

## Method and scope

- Searches: `gh search repos` (sorted by stars, limit 30) over the requested phrases, plus `topic:` text queries (`topic:trading-agent`, `topic:llm-trading`, `topic:mcp-trading`, `topic:ai-trading`). Roughly 75 queries were run in total. Some queries returned zero results: "ai trading agent alpaca", "interactive brokers llm agent", "ib_insync llm", "forex llm agent", "claude trading agent robinhood mcp". Interactive Brokers, forex and MetaTrader coverage is therefore thin. "metatrader llm" returned only one 0-star repo, but MT5 Claude-agent repos surfaced through other queries (see below).
- Exclusions applied as instructed. Derivative forks of excluded projects (TradingAgents-CN-lite, TradingAgents-astock, TradingAgents-AShare, TradingGoose, FinMem forks, Open-Finance-Lab AgenticTrading) were not counted as new.
- Shallow clones (`GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1`) were made for 15 repos into `/home/claude/repos/OWNER__NAME`. Only README files and a few specific source files were read. No repo code was run or installed.
- Suspicious-sign checks were keyword greps over the clones, not a code audit.
- Environment note: `gh auth status` reported a GH_TOKEN login failure, but search queries still returned results.

## Top 15 (by stars and recency), README skim

Execution classification: **REAL** = README or code states orders are placed with a live venue. **GATED** = real execution exists but needs explicit user approval, a mode switch, or is beta. **RESEARCH** = no autonomous execution claimed.

| # | Repo | Stars | License | Last push | Execution | Broker / venue | Summary |
|---|------|-------|---------|-----------|-----------|----------------|---------|
| 1 | [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 38,234 | MIT | 2026-11-14 | GATED | Any supported broker the user authorizes (Robinhood named as example) | "Your Personal Trading Agent". Research reports, backtests, paper portfolios. README says you can authorize a broker to execute live trades within a user-set mandate. A later line says it "runs no execution venue", which is consistent: it routes to a broker the user authorizes. |
| 2 | [OpenByteInc/QuantDinger](https://github.com/OpenByteInc/QuantDinger) | 13,763 | Apache-2.0 | 2026-11-14 | REAL (strategy engine) | Binance, OKX, Bitget, Bybit, Gate, HTX, IBKR, Alpaca | "AI research -> strategy code -> backtest -> paper/live execution". Hyper AI is a coordinator for research and config. README does not show that an LLM places each order autonomously. Not verified in code. |
| 3 | [TraderAlice/OpenAlice](https://github.com/TraderAlice/OpenAlice) | 7,450 | AGPL-3.0 | 2026-11-10 | GATED | Brokers via "Unified Trading Account" | "The AI orchestrator for trading." Agents stage proposed operations and commit rationale. The user approves execution through "Trading as Git". README calls execution beta and says to start with paper or testnet accounts. |
| 4 | [The-Swarm-Corporation/AutoHedge](https://github.com/The-Swarm-Corporation/AutoHedge) | 6,692 | MIT | 2026-05-11 | REAL | Solana only (Jupiter Ultra swap API). Coinbase "coming soon". | "Autonomous agent hedge fund". Code check: `autohedge/tools/ultra_tools.py` builds Jupiter swap orders and signs them with `SOLANA_PRIVATE_KEY` from `.env`. Real on-chain execution exists, but the README is thin (about 4 KB). Last push about six months ago. Star count is high relative to the docs. |
| 5 | [chrisleekr/binance-trading-bot](https://github.com/chrisleekr/binance-trading-bot) | 5,607 | Apache-2.0 | 2026-11-12 | REAL (rule-based) | Binance spot (testnet or live) | Mainly rule-based (trailing, momentum, rebalance). README says Claude Code can connect over MCP, which is off by default and needs approval. Not an LLM-decides bot by default. |
| 6 | [Lumiwealth/lumibot](https://github.com/Lumiwealth/lumibot) | 2,235 | GPL-3.0 | 2026-11-14 | REAL | 12 brokers (Alpaca paper example shown) | "Build AI trading agents. Backtest them. Trade with the same strategy." `self.agents.create(... allow_trading=True)` lets an agent place orders. Also has a vendor-hosted BotSpot MCP and cloud tie-in. |
| 7 | [chrisworsey55/atlas-gic](https://github.com/chrisworsey55/atlas-gic) | 2,446 (README says 944) | "other" | 2026-09-22 | RESEARCH (claimed live) | Not identified in public tree | ATLAS: 25+ Claude agents debate daily; "Now running live with real capital." The `src/` tree has no broker adapter. The README's "NOT included" list says live portfolio positions and trained prompts are withheld. Live claim unverifiable from code. Star count mismatch between API and README. |
| 8 | [ygwyg/MAHORAGA](https://github.com/ygwyg/MAHORAGA) | 871 | "other" | 2026-02-17 | REAL | Alpaca (ALPACA_PAPER recommended) | Autonomous LLM agent on Cloudflare Workers. Reads StockTwits and Reddit sentiment, executes via Alpaca. Multi-provider LLM. Last push about nine months before the search date. |
| 9 | [kyky2347/ALTA](https://github.com/kyky2347/ALTA) | 1,078 | Apache-2.0 | 2026-11-05 | GATED / research | Six connectors, "live-account acceptance not established" | "Autonomous LLM Trading Asterism", labelled "research only". Default Shadow mode. Broker API mode needs verified account and separate authorization. Includes vendored OpenAI Codex code. |
| 10 | [HammerGPT/Hyper-Alpha-Arena](https://github.com/HammerGPT/Hyper-Alpha-Arena) | 1,200 | Apache-2.0 | 2026-11-03 | REAL | Hyperliquid (testnet and mainnet), Binance Futures | "Multi-exchange AI trading platform." AI Trader mode lets LLMs decide and trade. Hosted login service has been shut down, so self-hosters must supply their own auth. Marketing language is strong ("Essential tool", "Hyper Insight ... 70,000 tracked addresses") and unverified. |
| 11 | [caiovicentino/polymarket-mcp-server](https://github.com/caiovicentino/polymarket-mcp-server) | 750 | MIT | 2026-09-20 | REAL | Polymarket (clob.polymarket.com, data-api) | "Enable Claude to autonomously trade" through 45 MCP tools, including limit and market orders and cancellation. Very heavy doc load (dozens of summary files), which is a weak quality signal. Key handling not audited. |
| 12 | [ryanfrigo/kalshi-ai-trading-bot](https://github.com/ryanfrigo/kalshi-ai-trading-bot) | 658 | MIT | 2026-11-09 | REAL (paper mode default in examples) | Kalshi (signed API), LLM via OpenRouter | README is candid: "NO MEASURED EDGE" verdict on the author's own live account (n=55). Says there is no offline backtest. Good transparency, though it also means the example strategies lose money in some markets. |
| 13 | [YizhiSong/FriesTrader](https://github.com/YizhiSong/FriesTrader) | 312 | MIT | 2026-11-07 | GATED (dry_run default) | Robinhood Agentic Trading MCP | Two scheduled Claude Code sessions per weekday. Thesis, then order. Deterministic risk scripts for sizing and stops. Starts in `dry_run`; only the user can set `execution.mode` to live. |
| 14 | [Oft3r/agentic-trading-desk](https://github.com/Oft3r/agentic-trading-desk) | 336 | MIT | 2026-10-19 | GATED (user approves) | Robinhood MCP | AI fetches data; Python scripts score; user approves execution. Has a PreToolUse guard on `place_equity_order` and a SessionStart hook (see flags). Ships a binary `gemini-spark-skill.zip` that was not inspected. |
| 15 | [jackson-video-resources/claude-tradingview-mcp-trading](https://github.com/jackson-video-resources/claude-tradingview-mcp-trading) | 621 | **none (no LICENSE file)** | 2026-05-15 | REAL | BitGet (`api.bitget.com /api/v2/spot/trade/placeOrder`) | Claude reads TradingView and places BitGet orders. `PAPER_TRADING` defaults to true; setting it to false places real orders. Several flags, listed below. |

Also seen, not read: [alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server) (1,085 stars, MIT, pushed 2026-11-13) is an official broker MCP server, not an agent. It was not read. Treat as infrastructure.

## Suspicious signs and flags

Items below are red flags or things to verify, not confirmed malice. No repo in the scanned set asked for a seed phrase. Grep hits for "seed phrase" and "mnemonic" were safety warnings, not solicitations.

1. **jackson-video-resources/claude-tradingview-mcp-trading**
   - No LICENSE file, so default copyright applies.
   - The BitGet sign-up link in the README has mismatched text and target. Displayed text is a `partner.bitget.com` URL; the link points to `bonus.bitget.com` with an affiliate code. Affiliate-driven promotion.
   - Clone or fork farm: at least six other repos in search results share this name, with 0 to 1 stars (for example `rhys-stack`, `gsalazar8474`, `PKGOLDENBOY`, `knowledgeispower1715-sketch`, `vhasselt/...`, `azmax7434/trading-view`). Pattern is consistent with a template being mass-forked for distribution.
   - Committed `trades.csv` and personal `.env` template. No malicious code found in the portions read.
2. **Oft3r/agentic-trading-desk**
   - `.claude/settings.json` SessionStart runs `scripts/session-setup.sh`. That script runs `apt-get install jq` with root or `sudo -n`. Read it before running a session.
   - The PreToolUse order guard is a positive safety control.
   - A `gemini-spark-skill.zip` binary archive is committed. Contents (SKILL.md and scripts) were listed, not extracted or reviewed.
3. **The Polymarket "polymarket-ai-agent" cluster**
   - About 18 repos with the same name, most with 0 stars and no or generic descriptions, created 2025 to 2026.
   - One is named by its URL: `franklin24567-cyber/https-polymarket-ai-agent.vercel.app-`.
   - Not read. Treat as low-quality or possibly spam; do not run.
4. **Keyword-stuffed descriptions**
   - `dexoryn-china/polymarket-arbitrage-bot` (42 stars) and `dexorynlabs/polymarket-AI-agent-trading-bot` have long, Chinese-SEO-style keyword descriptions. Typical of spam.
5. **AutoHedge** (6,692 stars)
   - Star count is high for a 4 KB README with last push about six months ago. Code does real swaps with a private key from `.env`. Verify before storing any key.
6. **ATLAS (chrisworsey55/atlas-gic)**
   - "Running live with real capital" claim is unverifiable from the public tree. Star count differs between README (944) and API (2,446).
7. **ALTA** (`kyky2347/ALTA`)
   - Vendored OpenAI Codex tree with many hook and plugin files. These appear to be upstream test fixtures, but the vendored tree is large and was not audited.
8. **Keyword scan false positives (not flagged)**
   - `ast.literal_eval` in Vibe-Trading, `atob` in a Vibe-Trading desktop loader, and `curl ... | sh` in ALTA's vendored Codex docs were reviewed and appear benign.
   - Hyper-Alpha-Arena's "guaranteed profitable" strings are prohibitions in its system prompt, not claims.

## Also seen (not read, metadata from search only)

Listed for follow-up. Descriptions are from search results and were not verified.

- **valory-xyz/trader** (88 stars, Apache-2.0, pushed 2026-11-13): AI agent for prediction markets (Omen on Gnosis, Polymarket on Polygon).
- **Julian-dev28/pathiel** (36, MIT, pushed 2026-11-14): Claude trades Hyperliquid perps through MCP with stops and targets. Worth reading next.
- **BijectiveLabs/bitra** (47, MIT, pushed 2026-11-14): "agents propose, the system decides" deterministic execution.
- **mogons/noraz-agent** (170, MIT, pushed 2026-10-03): Robinhood trading agent infrastructure with MCP, autonomous trading, copy-trading.
- **millw14/merrymen** (55, no license, pushed 2026-11-11): autonomous agents for Robinhood Chain, "use it from Claude".
- **EUGMsub/RobinhoodAgenticTrader** (1, MIT, pushed 2026-08-13): Guardrailed Claude + Robinhood MCP trader.
- **SamsonCukor06/agentic-trader** (0, pushed 2026-11-13): Claude + Robinhood MCP, with an evaluation reporting it did not beat the S&P 500. Honest negative result.
- **satyamdas03/alpaca-trading-agent** (2, pushed 2026-11-13): Claude Code + Alpaca MCP, 24/7 swing trading.
- **gacord1213-arch/alpaca-ai-trading-agent** (0, MIT, pushed 2026-08-24): Claude tool-calling plus official Alpaca MCP (74 tools), paper only.
- **El-Bach/claude-trader** (31, MIT, pushed 2026-04-06): 14 Claude agents trading FX and gold via MetaTrader 5.
- **flukelaster/ai-trading-agent** (79, pushed 2026-05-03): Claude + FastAPI + Next.js + MetaTrader 5, multi-symbol.
- **terryso/nof1-tracker** (762, MIT, pushed 2025-11-28): tracks nof1 signals and auto-executes Binance futures. Stale.
- **hypurrquant/perp-cli** (42, MIT, pushed 2026-11-13): multi-DEX perp CLI plus MCP server for AI agents (Hyperliquid, Pacifica, Lighter, Aster, and others).
- **krakenfx/kraken-cli** (812, MIT, pushed 2026-10-29): vendor CLI and MCP for Kraken. Infrastructure, not an agent.
- **ZhangJinHaHaHa/AgentLens** (1,014, AGPL-3.0, pushed 2026-08-24): agent marketplace-style trading platform. Not read.
- **mamawai/wtfibought** (145, MIT, pushed 2026-11-12): LLM agents trade with virtual money. Paper arena.
- **HKUDS/AI-Trader** and **wquguru/nof0** are excluded as known.
- **OctoBot** (Drakkar-Software, 6,943, GPL-3.0, pushed 2026-11-02): crypto bot with AI features. Not LLM-first; not read.
- **affaan-m/dprc-autotrader-v2** (41, MIT): autonomous trading agent in Rust, **archived**.
- **mnemox-ai/tradememory-protocol** (1,447, MIT, pushed 2026-10-23): memory and audit layer for trading agents. Infrastructure, not an executor.
- **Lots of 0-star "Claude trading agent" repos** pushed in 2026: `kaoi-cyber/ai-trader`, `tiramisuice/ai-trader`, `DaX-523/ai-trading-agent`, `AlexandreLamure/auto-trade`, `lukesophiie/winbot`, `mad1kow-cloud/crypto-intelligence-agent` (claims live real money on Bitget). Low-star and new; not read.

## Gaps

- No results for IBKR, forex, or ib_insync queries. Interactive Brokers and MetaTrader LLM agents may be underrepresented in this search tool's index.
- Did not read code for most top-15 repos beyond README and targeted greps. Execution claims are taken from docs unless a file is named above.
- Did not verify any star counts beyond the search response, nor any claim of real-money performance.
- The `topic:` searches largely returned repos already found by keyword search.
