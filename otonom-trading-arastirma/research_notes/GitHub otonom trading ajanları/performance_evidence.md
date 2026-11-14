# Performance evidence and operational risks of autonomous LLM trading agents (as of Nov 2026)

## Q1. Do autonomous LLM agents beat buy-and-hold in out-of-sample / live conditions?

### Takeaway
No consistent evidence. Live and forward-test results are mixed and regime-dependent: a few models beat passive benchmarks in short windows (often in rising or liquid markets), most do not, rankings flip between seasons/markets, and every live window found is short (2 to 10 weeks) and statistically weak. No live, long-horizon, net-of-cost evidence of reliable outperformance was found.

### Cited Findings

**Nof1 Alpha Arena (real money, $10k per model)**
- Season 1 ran Oct 18 to Nov 3, 2025 (17 days) on Hyperliquid crypto perpetuals, six models, $10,000 each, no human intervention. Qwen 3 Max won (+22%). — [GN Crypto](https://www.gncrypto.news/news/qwen-wins-alpha-arena-season-1-with-22-percent-returns/)
- Final Season 1 values per nof1 figures (as compiled by TradeRank, read Aug 2026): Qwen 3 Max $12,231 (+22.31%); DeepSeek V3.1 $10,489 (+4.89%); Claude Sonnet 4.5 $5,799 (-42.01%); Gemini 2.5 Pro $5,445 (-45.55%); Grok 4 $4,208 (-57.92%); GPT-5 $4,126 (-58.74%). Four of six lost money. — [TradeRank leaderboard](https://www.traderank.ai/alpha-arena-leaderboard) (secondary aggregator of nof1 data); "four out of six lose" also in [Forklog](https://forklog.com/en/four-out-of-six-ai-models-suffer-losses-in-trading-tournament/)
- Season 1 behavior observations: Grok 4, GPT-5, Gemini 2.5 Pro favored shorts; Gemini 2.5 Pro was most active; Grok 4 traded least; Qwen3-Max took largest positions; self-reported confidence did not correlate with performance; models misread chronological order of inputs unless corrected, were confused by "available cash" vs "free collateral," and made arithmetic errors in stop-loss math. — [BestHub write-up](https://www.besthub.dev/articles/can-llms-trade-crypto-profitably-inside-the-alpha-arena-competition-ace3b75ceaa5)
- Season 1.5 ran Nov 19 to Dec 3, 2025 on US equities (Tesla, Nvidia, Microsoft, Amazon, Nasdaq-100 names): eight models, four parallel formats (baseline with news, "Monk Mode", situational awareness, 20x max leverage). A "Mystery Model" (revealed as Grok 4.20) was the only model in positive territory (+12.11%, $4,844 profit across entries); GPT-5.1 and Gemini 3 placed 2nd/3rd with losses; Qwen 3 Max (S1 champion) lost up to ~70%. — [aiHola](https://aihola.com/article/grok-wins-alpha-arena-trading)
- Season 1 champion Qwen fell to near bottom in Season 1.5 (same source above), i.e. no persistence of rank across seasons.
- TradeRank states no public Nof1 season has run since Dec 3, 2025; alphaarena.ai showed Season 1.5 with models "no longer running" as of Nov 12, 2026; no Season 2 leaderboard was published. TradeRank also notes nof1's per-competition rows do not reconcile with the announced S1.5 figure. — [TradeRank leaderboard](https://www.traderank.ai/alpha-arena-leaderboard). (Other search hits for "Season 2" returned only S1/S1.5 coverage.)
- The 17-day crypto window in S1 coincided with a market selloff period; no buy-and-hold baseline was published in the sources I read (see Gaps).

**StockBench (arXiv 2510.02209)**
- Daily buy/sell/hold on 20 high-weight DJIA stocks, $100k start, Mar 3 to Jun 30, 2025 (82 trading days), 13 models, 3 seeds averaged. Abstract headline: most models struggle to outperform buy-and-hold. — [arXiv](https://arxiv.org/abs/2510.02209)
- Equal-weight passive baseline: +0.4% return, -15.2% max drawdown. Eight of 13 models exceeded 0.4% (top: Qwen3-235B-Think 2.5%, Qwen3-235B-Instruct 2.4%, GLM-4.5 2.3%, Claude-4-Sonnet 2.2%); GPT-5 0.3%, GPT-OSS-120B -0.9%, GPT-OSS-20B -2.8%. All models had smaller drawdowns than baseline (~-11% to -14%). Caveat: the paper's "rarely outperform" framing rests on a composite z-score, while raw returns show most beating the (very low) baseline; differences are small (a couple of percent over 4 months). — [arXiv](https://arxiv.org/abs/2510.02209) (as summarised by fetch tool; not independently checked against the PDF)
- Regime dependence: in a downturn period all LLM agents underperformed the passive baseline; in an upturn they outperformed. (Text/figure caption disagree on year, 2024 vs 2025.) — [arXiv](https://arxiv.org/abs/2510.02209)

**AI-Trader (HKUDS, arXiv 2512.10971)**
- Live benchmark across US stocks (Nasdaq-100, hourly), A-shares (SSE-50, daily), crypto (10 pairs, daily). Finding: general intelligence does not automatically translate into trading skill; risk control predicts robustness; liquid US market easiest to beat; no agent beat the A-share benchmark; cross-market generalization weak. — [arXiv](https://arxiv.org/abs/2512.10971)
- Cumulative returns (Table 1): US vs QQQ +1.87%: MiniMax-M2 9.56%, DeepSeek-v3.1 8.39%, Claude-3.7-Sonnet 3.11%, GPT-5 1.56%, Qwen3-Max 0.39%, Gemini-2.5-Flash -0.06%. A-share vs SSE-50 +1.65%: best was MiniMax-M2 1.31%, others lower/negative. Crypto vs CD5 -14.30%: only DeepSeek-v3.1 (-12.18%) beat it; GPT-5 -16.41%. DeepSeek-v3.1 beat benchmark in US and crypto but lagged in A-shares. — [arXiv](https://arxiv.org/abs/2512.10971) (figures from fetch-tool summary; benchmarks are index baselines, not explicitly labeled buy-and-hold)
- Companion press release by HKU Business School (Jul 14, 2026) describes a separate "Agentic Trader" FX live test: 10 LLM agents, $100k each, ~6 weeks. Reported Qwen strongest (~+9.9%), GLM and GPT near break-even, MiniMax and Claude larger losses, DeepSeek worst (-15.1%); more trades did not mean better returns; authors say results do not fully match their reasoning benchmarks and should not be read as long-term capability. The release is internally inconsistent about the top performer (Qwen vs Kimi K2.5). — [HKU Business School](https://www.hkubs.hku.hk/media/school-news/testing-ai-in-the-real-world-hku-business-school-released-ai-agents-trading-performance/). Note this is a different project from the AI-Trader GitHub repo; I did not verify they share a team beyond HKU affiliation. Also note the AI-Trader repo page (https://github.com/HKUDS/AI-Trader) appeared in search but I did not fetch it.

**LiveTradeBench (arXiv 2511.03628)**
- 21 LLMs, 50-day live evaluation (Aug 18 to Oct 24, 2025) on US stocks (15 stocks/ETFs plus cash) and Polymarket (10 contracts); agents output allocations. Key finding: high LMArena scores do not imply better trading; performance does not transfer between markets; reasoning models give no clear advantage. — [arXiv abstract](https://arxiv.org/abs/2511.03628), [HTML](https://arxiv.org/html/2511.03628v1)
- Example rows: Claude-Sonnet-3.7 US stocks +3.63% (Sharpe 1.45), Polymarket +20.54%; Claude-Sonnet-4 US stocks +2.45%, Polymarket -40.32% (Sharpe -2.40). Shows large cross-market and cross-model variance. — [HTML](https://arxiv.org/html/2511.03628v1) (partial table only; I could not read the full table or baseline comparison)

**Agent Market Arena (AMA, arXiv 2510.11695, "When Agents Trade")**
- Live multi-market benchmark (crypto and stocks), four agent architectures (InvestorAgent, TradeAgent, HedgeFundAgent, DeepFundAgent) on five backbones (GPT-4o, GPT-4.1, Claude-3.5-haiku, Claude-sonnet-4, Gemini-2.0-flash). Main finding: agent framework drove behavior (aggressive vs conservative) more than backbone model. — [arXiv](https://arxiv.org/abs/2510.11695). Return figures and buy-and-hold comparison not obtained (see Gaps).

**Long-horizon academic evidence**
- FINSABER (arXiv 2505.07078): backtest over ~two decades and 100+ symbols with delisted names; reports previously claimed LLM advantages "deteriorate significantly" in broader, longer tests; LLM strategies were too conservative in bull markets (underperform passive) and too aggressive in bear markets (heavy losses). Replication of FinMem (GPT-4o-mini) on TSLA Oct 2022 to Apr 2023 gave Sharpe 0.927 / return 19.94% vs originally reported 2.679 / 61.78%; buy-and-hold in that window was -20.48%. — [arXiv v5](https://arxiv.org/html/2505.07078v5)
- "The Alpha Illusion" (arXiv 2605.16895): reported gross Sharpe "is an upper bound, not a deployable number." In the authors' one-year, five-ticker reproduction, net buy-and-hold ($104.8K) beat TradingAgents ($102.3K net) and QuantAgent ($77.9K net) on 4 of 5 tickers (exception MSTR); TradingAgents Sharpe fell 0.43 to 0.22 after costs. — [alphaxiv summary](https://www.alphaxiv.org/abs/2605.16895.md)
- FinBen GPT-4 FinTrade Sharpe 1.51 ± 1.08 (standard error over half the mean); FinCon reports portfolio Sharpe 3.27 — both cited as examples of short-window, wide-CI claims. — [Alpha Illusion summary](https://www.alphaxiv.org/abs/2605.16895.md)

### Inferences
- Across live tests the modal result is "mixed, within noise": a few winners per test, different winners each time (Qwen won S1 and lost S1.5; DeepSeek wins crypto in AI-Trader but is worst in HKU FX), which is what random dispersion over short windows would look like.
- LLM agents appear to behave like noisy, regime-dependent beta/risk-taking engines (conservative in uptrends, aggressive in downtrends per FINSABER), so beating buy-and-hold in a rising window mostly reflects exposure choices.
- Equity results (StockBench, AI-Trader US) look better than crypto/leveraged venues, but margins vs passive are a few percent over 2 to 4 months and not demonstrably significant.

### Gaps
- No published buy-and-hold baseline for Alpha Arena S1/S1.5 found; no per-model S1.5 results beyond the winner; no confirmed Season 2 (TradeRank says none as of Nov 12, 2026).
- LiveTradeBench and AMA full numeric tables vs buy-and-hold were not retrieved.
- InvestorBench (arXiv 2412.18174), the original FinMem and FinBen papers were located but not read in detail; their original numbers are only known through critiques above.
- Statistical significance tests (e.g., bootstrap CIs vs index) are absent from the live benchmarks I read.
- The AI-Trader GitHub repo's current live leaderboard was not fetched.

## Q2. What methodological flaws make reported backtests unreliable?

### Takeaway
The main flaws are (1) look-ahead/memorization leakage from the LLM's training data, (2) short windows and tiny universes with survivorship and data-snooping bias, (3) ignoring costs/slippage, (4) single runs with high LLM nondeterminism and wide Sharpe confidence intervals, and (5) prompt/terminology fragility. Corrected replications shrink headline results substantially.

### Cited Findings
- Detecting lookahead (arXiv 2512.23847): "Lookahead Propensity" (a Min-K% Prob style familiarity score) interacts significantly with LLM predictions. Using Llama-3.3-70B on 91,361 Bloomberg headlines (1,587 firms, 2012 to 2023), a one-SD increase in LAP adds about 37% to the LLM's marginal predictive effect on next-day returns (small-cap effect stronger). A placebo with Llama-2 out of sample (Sep 2023 to Dec 2024) showed no such interaction. Conclusion: part of apparent forecasting power is memorization; bias is task-specific. — [arXiv HTML](https://arxiv.org/html/2512.23847v1)
- FinCAD / "Summoning the Oracle to Slay It" (arXiv 2605.24564): parametric look-ahead bias inflates in-sample backtests; the largest mean in-sample return correction was -67.1% across five 7-14B models and five mega-cap stocks; applying the correction raised in-sample/out-of-sample rank correlation (0.779 to 0.846). — [arXiv](https://arxiv.org/abs/2605.24564)
- Temporal contamination: when test window crosses pretraining cutoff, FinMem total return drops ~71.85% and QuantAgent Sharpe ~51.48% (attributed to Li et al.); LLM financial knowledge skews toward large and recent firms (Shah et al.). — [Alpha Illusion summary](https://www.alphaxiv.org/abs/2605.16895.md)
- Counterpoint: Chronologically consistent models (ChronoBERT/ChronoGPT, arXiv 2502.21206) found lookahead bias modest in a news-based long-short application: Sharpe ~4.8-4.9 for time-consistent models vs 4.90 for Llama 3.1, differences not significant; the authors argue bias is model- and application-specific. — [arXiv](https://arxiv.org/abs/2502.21206). (Note: this is predictive-signal research, not an agent backtest, and Sharpes of ~4.8 are themselves unusually high.)
- Survivorship bias and data snooping: backtests that use only currently active stocks and narrow windows overstate LLM advantage; FINSABER fixes with delisted names and historical constituents. — [arXiv v5](https://arxiv.org/html/2505.07078v5)
- Friction: of 40 system-by-friction-component cells across five frameworks, 35 are unmodeled; Sharpe of TradingAgents halves net of costs. — [Alpha Illusion summary](https://www.alphaxiv.org/abs/2605.16895.md)
- Statistical power: monthly stock-level R-squared rarely exceeds ~0.4%; a t-stat hurdle near 3.0 is argued for multiple testing; short windows give wide Sharpe CIs. — [Alpha Illusion summary](https://www.alphaxiv.org/abs/2605.16895.md)
- Parametric prior lock-in: across six LLMs, a Technology-vs-Defensive sector bias gap of 0.09 to 0.36; at 60% counter-evidence, Llama4-Scout reverses its view in ~8% of cases, GPT-4.1 in ~30%. — [Alpha Illusion summary](https://www.alphaxiv.org/abs/2605.16895.md)
- Multi-agent debate wins under 20% of 36 configurations (Zhang et al., as cited). — [Alpha Illusion summary](https://www.alphaxiv.org/abs/2605.16895.md)
- Benchmark-design issues observed in live contests: input ordering errors, ambiguous terms, rule-gaming, arithmetic errors, and prompt-format sensitivity; Alpha Arena used one prompt per model in S1, with parallel prompt variants only added in S1.5. — [BestHub](https://www.besthub.dev/articles/can-llms-trade-crypto-profitably-inside-the-alpha-arena-competition-ace3b75ceaa5), [GN Crypto](https://www.gncrypto.news/news/qwen-wins-alpha-arena-season-1-with-22-percent-returns/)
- StockBench itself uses a z-score composite whose headline conflicts with raw returns, and its period text/caption disagree (2024 vs 2025). — [arXiv](https://arxiv.org/abs/2510.02209)

### Inferences
- Any LLM backtest whose test window precedes the model's training cutoff should be treated as contaminated; only post-cutoff or live-forward results are admissible, which is why the live benchmarks (Alpha Arena, AI-Trader, LiveTradeBench, AMA) matter even though they are short.
- Live benchmarks have their own flaw: a single 2 to 10 week path is effectively one sample, so rank differences are not evidence of skill.
- Disagreement exists on severity: ChronoBERT-style evidence says leakage can be small for specific signal tasks, while LAP/FinCAD/replication evidence shows large inflation for agent backtests.

### Gaps
- No definitive paper quantifying memorization of exact historical prices by frontier models (GPT-5-class, Claude 4.x) was verified; findings above concern smaller/open models and news-return tasks.
- Original-numbers sources for the contamination stats (Li et al., Shah et al.) were not read directly; cited via the Alpha Illusion summary.

## Q3. What safeguards do serious projects implement, and what are the operational risks?

### Takeaway
Safeguards found are mostly design guidance and research prescriptions rather than documented production practice: least-privilege trade-only keys, input sanitization, human-in-the-loop, modular architecture with deterministic risk/execution layers, post-cutoff testing, and realistic cost modeling. Specific attack evidence shows LLM trading pipelines are vulnerable to poisoned news, tools and memory. Regulators (FINRA) flag autonomy, scope creep and auditability.

### Cited Findings

**Prompt injection / adversarial inputs**
- Adversarial headlines (arXiv 2601.13082): Cyrillic homoglyphs broke FinBERT stock-name mapping in 99.1% of 6,012 headlines; hidden HTML text flipped sentiment in 65.6%; a one-day attack cut cumulative return by 3.67 pp (homoglyph) / 3.18 pp (hidden text), worst case 17.7 pp; attacked systems stayed profitable, so losses could go unnoticed. O3 most robust; FinBERT, FinGPT, FinLLaMA, 4o-mini most vulnerable; best clean-return models were among the most affected. A simple Cyrillic-to-Latin sanitizer blocked the homoglyph attack (<0.1s per headline) but other variants could evade it. — [alphaxiv](https://www.alphaxiv.org/abs/2601.13082.md)
- TradeTrap: tested ~100 NASDAQ-100 stocks, Oct 2023, $5,000 per agent; attack modules: fake news/social data, MCP tool hijacking, prompt injection that reverses directional cues (return/Sharpe collapse, ~100% concentration), memory poisoning (forged trades, permanent divergence), state tampering (position API reports zero holdings; adaptive agent keeps buying, procedural agent builds huge short). Adaptive agents earn more but are more vulnerable to information-level attacks; procedural agents are steadier but fragile to corrupted state. — [BestHub review of TradeTrap](https://www.besthub.dev/articles/paper-review-tradetrap-evaluating-the-reliability-and-faithfulness-of-llm-based-trading-agents-d7f3806e23e5) (secondary review; no numeric results available)
- Other relevant work surfaced but not read: "Poisoning Agentic Alpha" (arXiv 2608.24069) and "SoK: Security of Autonomous LLM Agents in Agentic Commerce" (arXiv 2604.15367). — [arXiv](https://arxiv.org/pdf/2608.24069), [arXiv](https://arxiv.org/pdf/2604.15367)

**Hallucination / reliability**
- Alpha Arena S1 logs: arithmetic errors in stop-loss calculations, contradicting own prior plans, misreading time order, rule-circumvention. — [BestHub](https://www.besthub.dev/articles/can-llms-trade-crypto-profitably-inside-the-alpha-arena-competition-ace3b75ceaa5)
- One Claude Sonnet 4.5 position was a 20x leveraged BTC long in S1; S1.5 included a forced 20x stress format. — [BestHub](https://www.besthub.dev/articles/can-llms-trade-crypto-profitably-inside-the-alpha-arena-competition-ace3b75ceaa5), [aiHola](https://aihola.com/article/grok-wins-alpha-arena-trading)
- Overtrading: HKU FX test had models making over 1,000 trades with no return benefit; high-leverage models had bigger drawdowns. — [HKU](https://www.hkubs.hku.hk/media/school-news/testing-ai-in-the-real-world-hku-business-school-released-ai-agents-trading-performance/)

**API key / credential security**
- Practitioner guidance (vendor-ish blog, low authority): on Hyperliquid, agent/API wallets have Read-Only, Trade-Only, Full Access levels; keep withdrawals disabled (a trade-only key cannot move funds out of the protocol, so loss is bounded by margin already in the account); keep keys out of code in env vars/secret manager; IP-restrict if available; dedicated server; rotate keys; monitor and revoke fast. — [supa.is guide](https://supa.is/article/hyperliquid-api-agent-wallet-permissions-setup-2026). Note: "trade-only cannot withdraw" claim is from this guide, I did not verify against Hyperliquid docs. Trade-only keys can still lose the full account via bad or hijacked trades (see TradeTrap).

**Regulation**
- FINRA 2026 Annual Regulatory Oversight Report (GenAI section) flags agent risks: acting autonomously without human validation, acting beyond the user's intended scope/authority, multi-step reasoning hard to trace/explain; suggests supervisory processes specific to agent type, monitoring system access and data handling, deciding where human-in-the-loop is needed, tracking agent actions/decisions, and guardrails limiting behaviors/actions. — [FINRA](https://www.finra.org/rules-guidance/guidance/reports/2026-finra-annual-regulatory-oversight-report/gen-ai)
- Press coverage of lawmakers pressing the SEC on AI trading in retail investing appeared in search results but was not read. — [search hit](https://san-1510.aid.brainsum.com/news/top-news/us-lawmakers-push-sec-answers-ai-trading-moves-retail-investing)

**Design safeguards recommended in research**
- "Alpha Illusion" proposes a six-part reporting protocol (temporal integrity, dynamic universe, counterfactual robustness, calibration, realistic implementation, multi-agent disaggregation) and a modular design where LLMs act as auditable information extractors upstream of independent calibration, risk, and execution modules. — [alphaxiv](https://www.alphaxiv.org/abs/2605.16895.md)
- Benchmarks themselves implement: published prompts/decisions/trades (TradeRank), fixed identical tools and leverage across agents (HKU), multiple seeds (StockBench, 3 runs), parallel prompt variants (Alpha Arena 1.5), capital preservation ("Monk Mode") formats. — [TradeRank](https://www.traderank.ai/alpha-arena-leaderboard), [HKU](https://www.hkubs.hku.hk/media/school-news/testing-ai-in-the-real-world-hku-business-school-released-ai-agents-trading-performance/), [arXiv](https://arxiv.org/abs/2510.02209), [Forklog](https://forklog.com/en/new-season-of-ai-trading-tournament-kicks-off/)
- AI-Trader finding that risk control (MiniMax-M2 limiting downside, DeepSeek holding cash) predicted robustness supports hard-coded position/leverage limits. — [arXiv](https://arxiv.org/abs/2512.10971)

### Inferences
- The attack evidence implies news/social feeds and tool servers should be treated as untrusted input; sanitization alone is insufficient, so deterministic limits (max leverage, position size, daily loss kill-switch, trade-only keys) outside the LLM are the robust layer.
- Because attacked agents in the headline study stayed profitable, monitoring should compare against a clean/shadow baseline, not just absolute PnL.
- A trade-only key limits theft but not manipulation losses.

### Gaps
- Cost of LLM calls: no sourced per-trade/per-month inference cost figures found; only the qualitative finding that friction (trading costs) erodes returns. Needs a separate lookup (token pricing x decision frequency).
- No documented open-source project safeguard review (e.g., TradingAgents, FinRobot, ai-hedge-fund, AI-Trader repo) was completed; safeguards above are from papers and guides.
- SEC-specific rules for retail autonomous LLM trading (e.g., advisers act, market manipulation, CFTC for crypto), and non-US regimes (EU AI Act/MiFID, Turkey SPK/CMB) were not researched.
- Reuters/Bloomberg/CoinDesk reporting on Alpha Arena and any real-money losses by practitioners was not retrieved; practitioner reports are thin (mostly aggregator blogs).
- Source quality note: several sources (BestHub, aiHola, GN Crypto, TradeRank, supa.is, alphaxiv summaries) are secondary/aggregators; primary nof1 pages and PDFs were not fetched directly.
