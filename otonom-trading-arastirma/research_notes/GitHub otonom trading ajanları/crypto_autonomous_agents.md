# Open-source autonomous AI/LLM crypto trading agents on GitHub (as of 2026-11-15)

Method note: Stars / last-push / description were pulled live on 2026-11-15 via the GitHub search API (`gh api search/repositories`). Source for all "repo table" rows is that API listing (https://github.com/search). The API returned `license: null` for every repo, which is NOT evidence of "no license" (search endpoint does not reliably return it) - license is "unverified" unless another source is cited. Direct github.com page fetches and repo-API calls were blocked in this session, so READMEs were NOT read: architecture/risk details below come from repo descriptions/topics and secondary sources and are flagged accordingly. Stars are a weak credibility signal (see scam section: star-inflation is a known attack technique).

## 1. Which are genuinely autonomous end-to-end AND actively maintained (Nov 2026)?

### Takeaway
Active (pushed within ~2 weeks of 2026-11-15) and describing LLM-driven autonomous execution: NoFx (13.3k stars), CloddsBot (3.1k), hypergrok-trading-desk (518, but execution gated by approved tickets), Senpi skills (144), OKX agent-trade-kit (MCP tooling, not an agent itself), TradingAgents (122k, research framework, not an exchange executor). Most Nof1 replicas (nof0, open-nof1.ai, 195440/nof1.ai) went quiet between Dec 2025 and May 2026. No repo here has independently verified live performance; I could not read any README to confirm autonomy claims.

### Cited Findings

**A. Full "trading OS" / Alpha-Arena-style live agents**
- NoFxAiOS/nofx - 13,282 stars, last push 2026-11-04; description now "AI trading terminal assistant for US stocks, commodities, forex, and crypto" - [GitHub search](https://github.com/NoFxAiOS/nofx)
  - License AGPL-3.0; open-sourced 2025-10-28; named exchanges Binance and Hyperliquid (others "platforms like"); models DeepSeek, Qwen, Claude; features: unified order execution, backtesting engine, containerized microservices, parallel multi-model evaluation/ensemble decisions, dashboards/alerts - [Jimmy Song landscape](https://landscape.jimmysong.io/projects/nofx/)
  - ~9.2k stars in ~2 months (as of 2025-12-22); self-hosted full loop data->reasoning->execution->monitoring; CEX API keys and DEX private keys are the credentials at risk - [OneKey blog](https://onekey.so/blog/ecosystem/the-achilles-heel-of-open-source-nofxs-9000-stars-in-2-months-and-its-hackgate-infightinggate-and-opensourcegate) (promotional source: OneKey's author says they built a competing project, nof0)
  - Security: Oct 31 2025 commit introduced a "default admin mode" that could bypass protected API routes; hard-coded JWT secrets and sensitive API responses could expose exchange API keys/DEX private keys with default deployments; SlowMist analysis published 2025-11-17 - same OneKey post (single secondary source, not independently verified here)
  - Governance dispute mid-Dec 2025: contributor accused ChainOpera AI Foundation testnet of running older NoFx code without attribution - same OneKey post
  - Many forks/clones exist (e.g. nofx-go 1 star, nofx-trading, "nofx-user", "https-github.com-NoFxAiOS-nofx" mirrors) - [GitHub search](https://github.com/search?q=nofx). Treat unofficial forks as high-risk (see section 3). Also fork/derivative: jeffeehsiung/nofxplus (12 stars, push 2026-09-23, "Chain of Trade").
- alsk1992/CloddsBot - 3,109 stars, created 2026-01-26, last push 2026-11-13, TypeScript; "autonomous across 1000+ markets - Polymarket, Kalshi, Binance, Hyperliquid, Solana DEXs, 5 EVM chains... manages risk while you sleep... Built on Claude", agent commerce protocol (x402) - [GitHub search](https://github.com/search?q=CloddsBot). Very fast star growth in <10 months, claims very broad; no verified results found. Treat with caution (see inference).
- olaxbt/ai-market-maker (AIMM) - 2,117 stars, push 2026-08-20, Python, "Agentic AI Hedge Fund OS", openclaw topics - [GitHub search](https://github.com/search?q=ai-market-maker)
- 0xethanq/astra-quant-agent - 422 stars, created 2026-08-30, push 2026-10-03, Python; "multi-LLM analysis, deterministic Python risk control & OKX execution"; topics include binance, okx, orderflow, self-evolving, risk-management - [GitHub search](https://github.com/search?q=astra-quant-agent). Design pattern (LLM proposes, deterministic code risk-gates) is the sound one; unverified in practice.
- galleonlabs/hypergrok-trading-desk - 518 stars, created 2026-08-16, push 2026-11-12, Python; Hyperliquid desk for AI agents (7 roles, 17 skills); "research first; execution requires your API wallet and approved tickets" (human approval gate = NOT fully autonomous) - [GitHub search](https://github.com/search?q=hypergrok-trading-desk)
- Senpi-ai/senpi-skills - 144 stars, push 2026-11-14; "80+ strategy templates for autonomous trading on Hyperliquid", two-phase trailing-stop (DSL) exits - [GitHub search](https://github.com/search?q=senpi-skills)
- moss-site/moss-trade-bot-skills - 396 stars, push 2026-10-20; natural language -> five-pillar strategy (more strategy-generator than autonomous decider) - [GitHub search](https://github.com/search?q=moss-trade-bot-skills)
- Gajesh2007/ai-trading-agent - 553 stars, last push 2025-10-27 (stale ~13 months); "AI Trading Agent on Hyperliquid" - [GitHub search](https://github.com/search?q=hyperliquid+ai+agent)
- Smaller 2026 newcomers (all <100 stars, unverified): QuantiaAI/helm-agents 88 (13 AI analysts debate, risk stress test), mocasus/trade-agent 14 (LLM analyzes market+news+indicators -> decision -> execution, 100+ exchanges via CCXT), ma-pony/cryptotrader-ai 13 (LangGraph multi-agent debate + hard risk limits + decision log), IslamBaraka90/Super-Agent-Trading-Bot 1 (push 2026-11-09, event-driven TS agent), p20090504-dotcom/qs-bot (LLM decisions with hard risk gate, OKX copy trading), deuteriumZzz/BitbotBY (Bybit futures, Claude/DeepSeek/GPT/Gemini + SAC RL), aithos-rr/AI-Agent-for-Trading (Sapienza thesis, 4 LLMs on Hyperliquid TESTNET), Codeptor/peri (autonomous LLM perp trader for Hyperliquid), muzafferkadir/claude-crypto-trader-public (10 stars, fake-money, 3 risk-profile personas) - [GitHub search](https://github.com/search?q=autonomous+crypto+trading+agent+llm)

**B. Nof1 Alpha Arena replicas (see section 2)**
- wquguru/nof0 - 2,754 stars, last push 2025-12-07 (stale ~11 months), "full reproduction of NOF1 Alpha Arena" - [GitHub search](https://github.com/search?q=nof1)
- SnowingFox/open-nof1.ai - 805 stars, created 2025-10-20, last push 2026-04-01 - same search
- terryso/nof1-tracker - 762 stars, last push 2025-11-28; CLI that tracks nof1.ai agent signals and auto-executes Binance futures (copy-trading Nof1, not independent decisions) - same search
- 195440/nof1.ai - 693 stars, last push 2026-05-15; "Autonomous AI Trading Agent"; topics incl. nofx, openclaw, moltbot - same search
- etrobot/open-alpha-arena - 601 stars, push 2026-08-03; PAPER trading, ccxt quotes - same search
- oficcejo/alpha-arena-okx - 347 stars, push 2026-07-27; BTC auto-trading with DeepSeek or Qwen3-Max on OKX (Chinese README) - same search
- kojott/LLM-trader-test 143 (last push 2025-12-29); okay456okay/nof1.ai.monitor 57 (notifier); qingshungLI/Super-nof1.ai 39; Scodive/alpha-arena-prompt 13 (prompt analysis); kukapay/awesome-alpha-arena 31 (curated list - best index of replicas); dontbesideline/Open-Nof1-AlphaArena 3 (UI clone) - same search

**C. ElizaOS / ai16z / Solana agent kits**
- elizaOS/eliza - 19,873 stars, push 2026-11-14; now described as "Open source agentic operating system" (general agent framework, not a trading bot) - [GitHub search](https://github.com/search?q=elizaOS). Trading is via community plugins; ones found are tiny: Okay-Bet/plugin-polymarket 10 stars, pranavjadhav1363/plugin-ccxt 2 (push 2025-02), milady-ai/plugin-bsc-memes 1, openpump 10 - [GitHub search](https://github.com/search?q=elizaos+trading+plugin). I found no popular, maintained ElizaOS crypto-trading agent (gap).
- sendaifun/solana-agent-kit - 1,764 stars, last push 2026-05-14 (6 months stale); toolkit connecting any AI agent to Solana protocols (tool layer, not a decision-maker; strategy/risk is up to the LLM/dev) - [GitHub search](https://github.com/search?q=solana-agent-kit). Look-alike repos (teraus111/web3-agent-kit-solana-trading 179 stars, davidpc007 fork 130) are unverified - see section 3.
- Memecoin/pump.fun "autonomous agents" (zetryn-ai/ai-agent 11, alaika-cyber/pumpfun 6, "Jito MEV, multi-model AI brain", 0xMerl99/Agent-World-Protocol 47) are tiny/new and exactly the profile of repos that are scam bait - [GitHub search](https://github.com/search?q=ai+trading+agent+solana+autonomous)

**D. Frameworks/tooling (LLM layer present, but mostly research/analysis or tool access)**
- TauricResearch/TradingAgents - 122,589 stars, push 2026-11-04; multi-agent LLM financial trading framework (equities-focused research framework; execution is generally paper/simulated) - [GitHub search](https://github.com/search?q=TradingAgents). Forks: hsliuping/TradingAgents-CN 32,955 (push 2026-11-14), TradingAgents-astock 3,978 (A-shares). Crypto-specific forks found are tiny.
- virattt/ai-hedge-fund crypto derivatives: 51bitquant/ai-hedge-fund-crypto 628 (last push 2025-09-05, stale), AI-Brokers/AIBrokers 129 (2025-01, stale), DaviddTech/ai-trading-agent 97, Drakkar-Software/OctoBot-AI 12 - [GitHub search](https://github.com/search?q=ai-hedge-fund+crypto)
- okx/agent-trade-kit - 511 stars, push 2026-11-13; official OKX MCP server (spot/swap/futures/options/grid) so any LLM agent can trade; the LLM is external - [GitHub search](https://github.com/search?q=okx+agent+trade+kit)
- Polymarket/agents - 3,819 stars, last push 2024-11-05 (abandoned); "Trade autonomously on Polymarket using AI Agents" - [GitHub search](https://github.com/search?q=polymarket+ai+agent). Lumiwealth/lumibot 2,235 (push 2026-11-14, "AI agents that place the trade", 12 brokers).
- FreqAI (brief, as requested): ML-adaptive model layer inside Freqtrade; the repos found are third-party strategies (jerome-benoit/freqai-strategies 64 stars, push 2026-11-14; Netanelshoshan/freqAI-LSTM 326, 2025-04) - [GitHub search](https://github.com/search?q=FreqAI). It is statistical ML retraining, not an LLM reasoning agent.
- MCP exchange servers: nirholas/Binance-MCP 40, python-kraken-sdk 89 (has MCP server), perp-cli 42 (Hyperliquid + multi-DEX CLI/MCP) - [GitHub search](https://github.com/search?q=mcp+crypto+trading+exchange)
- CryptoTrade (EMNLP 2024 paper, LLM reflective agent): I found no maintained official repo in search (only vnavanee/cryptotrader-llm, 0 stars) - gap.

### Inferences
- "Autonomous + active + large community" narrows to NoFx and CloddsBot; both have thin independently verified performance evidence, and NoFx has a documented security incident.
- Common architecture across serious entrants (astra, cryptotrader-ai, qs-bot): LLM proposes -> deterministic code enforces hard risk limits (position size, leverage, stop) -> exchange API. Pure "LLM sets its own stops" (Alpha Arena style) is shown below to be error-prone (LLMs made arithmetic errors in stop-loss calculations).
- Star counts of 2026-born repos (CloddsBot 3.1k in <10 months) cannot be used as quality evidence given documented star-farming (section 3).
- TradingAgents' 122k stars reflects interest in stock research, not crypto execution proof.

### Gaps
- READMEs/licenses/risk-management code were not read (github.com not fetchable; repo API blocked), so per-repo stop-loss/sizing logic, live-vs-paper defaults and actual license are unverified except where cited.
- No independent track record (audited PnL) found for any open-source repo.
- ElizaOS dedicated trading agents and Bybit-specific LLM bots: no notable maintained repo located.

## 2. What did Nof1 Alpha Arena show, and which open-source replicas exist?

### Takeaway
Season 1 (Oct 18 - Nov 3, 2025; $10k real money each, six LLMs, six Hyperliquid perps) ended with Qwen3-Max +22% and DeepSeek +5% while four models lost 42-59% - a noisy, short, leverage-heavy sample that shows LLMs are poor at risk handling more than it proves any model's skill. Season 1.5 (US stocks, late Nov - Dec 2025) was won by Grok 4.2 (~+12% avg). Replicas exist (nof0, open-nof1.ai, NoFx lineage, etc.) but most are stale.

### Cited Findings
- Season 1 dates Oct 18 - Nov 3 2025; $10,000 start each. Final: Qwen3 Max $12,231 (+22.3%), DeepSeek $10,489 (+4.9%), Claude Sonnet 4.5 $5,799 (-42.0%), Gemini 2.5 Pro $5,445 (-45.6%), Grok $4,208 (-57.9%), GPT-5 $4,126 (-58.7%); DeepSeek briefly led above $13k - [Forklog](https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/) (percentages computed by the fetch tool from balances; founder Jay A. Zhang)
- Design: six Hyperliquid perps (BTC, ETH, SOL, BNB, DOGE, XRP); real funds; leverage allowed (Claude opened a 20x BTC long using 40% of margin); quantitative data only (prices, volumes, indicators), no news; each cycle (~every 2-3 min) models output decision, quantity, leverage, justification, 0-1 confidence and an exit plan (profit target, stop-loss, invalidation) - [BestHub write-up](https://www.besthub.dev/articles/can-llms-trade-crypto-profitably-inside-the-alpha-arena-competition-ace3b75ceaa5)
- Behavior: Grok 4, GPT-5, Gemini favored shorts; Claude rarely shorted; Gemini traded most, Grok least; Qwen3-Max took largest positions with narrow exit bands; Claude and Qwen held 1-2 assets - same source
- Weaknesses noted by the organizers/analysis: input-order misreads, inconsistent "available cash" vs "free collateral" use, no memory, short context, arithmetic errors in stop-loss calculation, self-reported confidence did not correlate with performance; Season 2 promised "stronger statistical rigor" - same source
- Season 1.5: traded US stocks; models Grok 4.2 (mystery model), GPT-5.1, Gemini 3, Kimi K2; Grok 4.2 averaged ~12% over two weeks and was profitable in all four modes; as of Dec 8 2025 it was the only profitable model; GPT-5.1 second, Gemini 3 third - [Forklog](https://forklog.com/en/ai-model-grok-4-2-triumphs-in-trading-tournament/)
- Replicas (stars/last push, from [GitHub search](https://github.com/search?q=nof1)): wquguru/nof0 2,754 / 2025-12-07; SnowingFox/open-nof1.ai 805 / 2026-04-01; terryso/nof1-tracker 762 / 2025-11-28; 195440/nof1.ai 693 / 2026-05-15; etrobot/open-alpha-arena 601 / 2026-08-03 (paper); oficcejo/alpha-arena-okx 347 / 2026-07-27; NoFx (13.3k) is the dominant derivative/competitor, open-sourced days after Season 1 began.
- Index of replicas: kukapay/awesome-alpha-arena (31 stars) - [GitHub search](https://github.com/search?q=alpha+arena+clone)

### Inferences
- A 17-day, single-run, 6-model sample with leverage has no statistical power; the ranking likely reflects variance and risk appetite (Qwen's large positions in a trending window) more than model quality. Organizer's own "stronger rigor" promise supports this.
- The benchmark's lesson for builders: put sizing/stop logic in deterministic code, not in the LLM.
- Replica activity decayed after the Season 1 hype (Oct-Dec 2025).

### Gaps
- Alpha Arena Season 2 (2026) status/results: searches surfaced only Season 1 / 1.5 coverage; I could not confirm whether Season 2 ran or its outcome.
- Season 1.5 exact returns for 2nd-4th place and starting capital not found.
- nof1.ai primary site was not fetched; numbers come from press.

## 3. Known scams / malicious repos in this space

### Takeaway
Yes, multiple documented campaigns: fake Solana/Polymarket "trading bot" repos with malicious npm dependencies stealing .env/keypairs, hijacked GitHub orgs, star-farmed repos, and 386 malicious crypto-trading "skills" on OpenClaw's ClawHub. Plus a genuine-project vulnerability (NoFx default-admin issue). Never give a repo a withdraw-enabled key or main wallet key.

### Cited Findings
- solana-pumpfun-bot (account zldp2002, now deleted): fake Solana trading bot with many stars/forks; depended on npm package crypto-layout-utils (heavily obfuscated, jsjiami.com.v7) that scanned for wallet data/private keys and uploaded them; some forks also used bs58-encrypt-utils-1.0.3; attacker likely used multiple accounts to forge forks/stars; SlowMist report 2025-07-04; distribution since ~June 12 2025 - [Cointelegraph](https://regional-front.cointelegraph.com/news/solana-trading-bot-github-malware-scam)
- Polymarket bot campaign (claims by one dev.to author, not independently verified): `dev-protocol` verified Japanese DeFi org hijacked ~Feb 2026, 20+ repos (e.g. polymarket-copytrading-bot-sport) with typosquatted deps `ts-bign` (big.js) and `big-nunber` (bignumber.js); payload `levex-refa` steals .env, Solana id.json keypairs, config files to Vercel-hosted C2 disguised as Cloudflare; `lint-builder` postinstall adds persistent SSH backdoor; bot works against real Polymarket so victims don't notice - [DEV Community](https://dev.to/nevosaynevo/why-almost-every-polymarket-trading-bot-on-github-is-malicious-28o7)
- ClawHub/OpenClaw (formerly Moltbot): 386 malicious skills posing as crypto trading automation (impersonating ByBit, Polymarket, Axiom etc.) delivered infostealers to macOS/Windows; shared C2 91.92.242.30; stole exchange API keys, wallet private keys, SSH creds, browser passwords; top poster "hightower6eu" ~7,000 downloads; found by Paul McCarty, reported 2026-02-01 - [Infosecurity Magazine](https://www.infosecurity-magazine.com/news/malicious-crypto-trading-skills/)
- Older: Python package campaign disguised as trading tool targeting crypto wallets (Oct 2024) - [The Hacker News](https://thehackernews.com/2024/10/researchers-uncover-python-package.html), [Checkmarx](https://checkmarx.com/blog/cryptocurrency-enthusiasts-targeted-in-multi-vector-supply-chain-attack/) (titles only seen in search results; not fetched)
- Legitimate-project risk: NoFx default admin mode / hard-coded JWT secret exposure (SlowMist, 2025-11-17) - [OneKey blog](https://onekey.so/blog/ecosystem/the-achilles-heel-of-open-source-nofxs-9000-stars-in-2-months-and-its-hackgate-infightinggate-and-opensourcegate)
- Search-listing evidence of NoFx clone sprawl: dozens of unofficial forks/mirrors named "nofx", "https-github.com-NoFxAiOS-nofx", plus "ai-deployment-service" (pjl914335852-ux, "NOFX Trading OS & OpenClaw Agent | On-chain payment (USDT)") - [GitHub search](https://github.com/search?q=nofx). I did NOT analyze them; listed only as repos that warrant suspicion (paid "deployment service" asking for crypto payment is a red flag, not a proven scam).

### Inferences
- Red flags: new account, star/fork spike with thin history, unusual/obfuscated or off-registry npm deps, postinstall scripts, requests for private keys/.env, "Jito MEV / multi-model AI brain" marketing, unofficial forks of popular projects.
- Safer practice: dedicated sub-account, trade-only API keys with IP whitelist and no withdrawal, small capital, Hyperliquid API/agent wallet (not main key), run in isolated VM, audit dependencies/lockfiles. Agents that take an LLM prompt-injection surface (news, X posts) add an additional attack path (not evidenced in sources here).

### Gaps
- Specific malicious repos impersonating NoFx/Nof1 clones were not confirmed; no source tying named clones to theft.
- Full Checkmarx/THN details not read.
