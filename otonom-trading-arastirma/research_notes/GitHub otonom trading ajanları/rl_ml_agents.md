# RL and Non-LLM ML Autonomous Trading Agents on GitHub

Snapshot date: 2026-11-15.

**Access caveat:** github.com and the GitHub API were blocked in this session (API returned 403; github.com pages were not on the WebFetch allowlist). Repo facts below come from third-party aggregators (sourcepulse, ecosyste.ms, ossinsight, relatedrepos), PyPI, official docs, and papers. Aggregators report activity as relative times ("3 weeks ago") with unknown crawl dates, and they disagree on several repos (flagged below). Treat star counts as order-of-magnitude and verify dates on GitHub before relying on them.

## Key Question 1: Which projects are maintained as of late 2026?

### Takeaway
RD-Agent (PyPI 1.0.0 dated 2026-09-23) and Qlib show the clearest recent activity. The FinRL family shows recent activity in some sources and stale activity in others, so its status is unresolved. gym-anytrading has no commits since March 2024. TensorTrade and Freqtrade have no dated activity in the sources I could reach.

### Cited Findings
- **Qlib (microsoft/qlib):** 49,704 stars, last commit "4 days ago" per [sourcepulse](https://www.sourcepulse.org/projects/741155); 49,414 stars and 7,812 forks per [ossinsight](https://ossinsight.io/analyze/microsoft/qlib). The newest entry in the [Qlib changelog](https://qlib.readthedocs.io/en/latest/changelog/changelog.html) is 0.8.0 with no date, while a [SourceForge mirror](https://sourceforge.net/projects/qlib.mirror/files/v0.9.6) lists v0.9.6. The latest release number is therefore unconfirmed.
- **RD-Agent (microsoft/RD-Agent):** latest PyPI release 1.0.0 on 2026-09-23, Python 3.10+, MIT, maintained by Microsoft Research Asia per [PyPI](https://pypi.org/project/rdagent/). Also 15,367 stars and last commit "3 weeks ago" per [sourcepulse](https://www.sourcepulse.org/projects/1237561).
- **FinRL (AI4Finance-Foundation/FinRL):** 11,605 stars, pushed "19 days ago" per [ecosyste.ms](https://repos.ecosyste.ms/hosts/GitHub/owners/AI4Finance-Foundation). A second listing shows 17,057 stars and a last commit "1 week ago" per [sourcepulse](https://www.sourcepulse.org/projects/1271579). The [README](https://cdn.jsdelivr.net/gh/AI4Finance-Foundation/FinRL@master/README.md) says the repo preserves the original framework and points new users to FinRL-X / FinRL-Trading.
- **FinRL-Trading (now positioned as FinRL-X):** 2,922 stars, last commit "2 weeks ago", Apache-2.0, per [sourcepulse](https://www.sourcepulse.org/projects/1247282). Ecosyste.ms lists 2,349 stars and a last push "11 months ago" for the same repo, per [ecosyste.ms](https://repos.ecosyste.ms/hosts/GitHub/owners/AI4Finance-Foundation). **Conflict; maintenance is unresolved.**
- **ElegantRL (AI4Finance-Foundation/ElegantRL):** 4,033 stars, pushed "16 days ago" per [ecosyste.ms](https://repos.ecosyste.ms/hosts/GitHub/owners/AI4Finance-Foundation). Another listing shows 4,375 stars, last update "8 months ago", and no license stated per [sourcepulse](https://www.sourcepulse.org/projects/1323088). **Conflict.** It is described as a "massively parallel DRL framework" for cloud use, not a trading system.
- **FinRL-Meta (AI4Finance-Foundation/FinRL-Meta):** 1,953 stars, last update "1 week ago", MIT, described as a "market environment for financial reinforcement learning research" per [sourcepulse](https://www.sourcepulse.org/projects/1649601). Ecosyste.ms gives 1,536 stars and "about 2 months" per [ecosyste.ms](https://repos.ecosyste.ms/hosts/GitHub/owners/AI4Finance-Foundation). **Conflict.**
- **Freqtrade (FreqAI module):** 55,659 stars and 11,528 forks per [ossinsight](https://ossinsight.io/analyze/freqtrade/freqtrade). No last-activity date was shown. The only date on the page is a "Contributor Rankings 2026/10" heading, which is weak evidence.
- **TensorTrade (tensortrade-org/tensortrade):** 7.3k stars and 1,093 commits on master per [GitHub](https://github.com/tensortrade-org/tensortrade). The last commit date and release list were blank on the captured page.
- **gym-anytrading (AminHP/gym-anytrading):** 2,389 stars, last commit March 14, 2024 per [RelatedRepos](https://relatedrepos.com/gh/AminHP/gym-anytrading); "2 years ago" per [sourcepulse](https://www.sourcepulse.org/projects/1845566). No license stated.

### Inferences
- Likely maintained in 2026: RD-Agent and Qlib (both have dated or very recent activity). FinRL-family status depends on which aggregator is right.
- Likely unmaintained: gym-anytrading (no commits in about 2.5 years as of the snapshot).
- Unknown: Freqtrade and TensorTrade (no dated activity found).

### Gaps
- No primary GitHub data (commit dates, release tags, open-issue counts) for any repo, because GitHub was blocked.
- Current Qlib release number is unconfirmed.
- TradeMaster (NTU) appeared only as a [NeurIPS 2023 paper](https://personal.ntu.edu.sg/boan/papers/NeurIPS_23_TradeMaster.pdf) and a PyPI listing. Its activity was not checked.

## Key Question 2: Which support live or paper order execution?

### Takeaway
Within the sources, only FinRL-Trading / FinRL-X (Alpaca paper and live) and Freqtrade (dry-run and live, crypto) show real order placement. The original FinRL has "basic" Alpaca support. Qlib's online module is a simulator. RD-Agent, TensorTrade, ElegantRL, FinRL-Meta and gym-anytrading show no live execution.

### Cited Findings
- **FinRL-Trading:** paper and live trading both require Alpaca API credentials, per [sourcepulse](https://www.sourcepulse.org/projects/1247282).
- **FinRL-X (blog, promotional source):** describes Alpaca paper and live support with multi-account management and pre-trade risk checks, and calls paper trading "first-class". Live-mode commands are not shown. The post also has internal inconsistencies in its return figures, per [a third-party blog](https://blog.brightcoding.dev/2026/06/05/finrl-x-the-ai-native-trading-framework-wall-street-doesnt-want-you-to-know).
- **Original FinRL:** the README's comparison table lists "Basic Alpaca support" and does not mention paper trading, per the [README](https://cdn.jsdelivr.net/gh/AI4Finance-Foundation/FinRL@master/README.md).
- **Qlib online module (v0.5.0 docs):** simulates daily order generation, execution, and account update against a simulated exchange with costs. It does not describe connecting to a real broker, per [Qlib online docs](https://qlib.readthedocs.io/en/v0.5.0/hidden/online.html). The docs page title is ambiguous about version.
- **QlibRL:** an "RL platform for quantitative investment" focused on order execution and portfolio allocation. The page makes no statement about live orders, per [QlibRL docs](https://qlib.readthedocs.io/en/latest/component/rl/overall.html).
- **RD-Agent:** no live trading or broker integration on the PyPI page. Its disclaimer says the tool is not ready for financial investment or advice, per [PyPI](https://pypi.org/project/rdagent/).
- **Freqtrade FreqAI:** runs in dry-run or live mode and retrains models on a schedule, per [FreqAI docs](https://codeclimate.com/github/freqtrade/freqtrade/docs/freqai.md/source). The FreqAI RL doc says RL state information is used in dry and live runs, not in backtesting, per [FreqAI RL docs](https://codeclimate.com/github/freqtrade/freqtrade/docs/freqai-reinforcement-learning.md/source).
- **TensorTrade:** the repo describes "deploying robust trading agents", but its README architecture table says the Exchange component "simulates execution", per [GitHub](https://github.com/tensortrade-org/tensortrade).

### Inferences
- For Alpaca paper trading, FinRL-Trading is the only candidate in these sources. Verify in the repo before relying on it.
- Freqtrade's "paper" mode is dry-run. Its exchange coverage is crypto-centred per my background knowledge; I did not verify this against its current docs, which were not reachable.

### Gaps
- FinRL-Trading's Alpaca code path was not inspected.
- Freqtrade's supported-exchange list and stock-broker support were not verified.

## Key Question 3: What does "autonomous" mean, and what does RD-Agent do?

### Takeaway
"Autonomous" means different things in each project. In FinRL and FreqAI-RL, an RL agent learns entry and exit actions, but only in backtests or dry runs. In Qlib and RD-Agent, autonomy covers research (proposing and testing factors and models), and trading is a separate step. None of the sources shows a fully unattended, RL-based, broker-connected trader.

### Cited Findings
- **RD-Agent-Quant loop:** the [paper](https://arxiv.org/html/2505.15155v2) describes a closed loop. A proposer generates factor or model hypotheses from past experiments. A coder (Co-STEER) implements them. A validation step drops factors that have IC ≥ 0.99 against the existing library and then backtests in Qlib. An analysis step judges results and uses a contextual Thompson-sampling bandit to choose between factor and model optimisation.
- **RD-Agent-Quant results (CSI 300):** the best run, R&D-Agent(Q) with o3-mini, reports IC 0.0532, annualised return 14.21%, IR 1.7382, and max drawdown -7.42%. The fixed LightGBM baseline reports IR 0.5664, per [the paper's Table 1](https://arxiv.org/html/2505.15155v2).
- **RD-Agent-Quant setup:** training 2008–2014, validation 2015–2016, test 2017-01-01 to 2020-08-01. LightGBM is the fixed predictor during factor search. Strategy is a daily long-short ranking with transaction costs, per the [paper](https://arxiv.org/html/2505.15155v2).
- **RD-Agent-Quant caveats (the paper's own):** the framework "relies solely on the LLM's internal financial knowledge", and online adaptation to regime changes is listed as future work. The paper reports backtests only, per the [paper](https://arxiv.org/html/2505.15155v2).
- **RD-Agent scenarios:** `fin_quant`, `fin_factor` and `fin_model` commands cover joint factor and model evolution, per [PyPI](https://pypi.org/project/rdagent/). The same page lists Kaggle data-science and paper-to-model scenarios.
- **FreqAI RL:** the agent picks an action at each candle (neutral, enter long, exit long, enter short, exit short in the 5-action setup). The reward comes from a user-defined `calculate_reward()`. The model is Stable-Baselines3 on a gym environment, per [FreqAI RL docs](https://codeclimate.com/github/freqtrade/freqtrade/docs/freqai-reinforcement-learning.md/source). The agent therefore learns its own entry and exit policy without strategy labels.

### Inferences
- RD-Agent's autonomy is over research search, not position-taking. Its reported gains are backtest IR on a single index with a fixed predictor.
- The paper repeatedly selects factors and models against the 2015–2016 validation window, so there is a selection-bias risk. The paper does not discuss search-induced overfitting. This is my inference.
- The paper's Table 1 labels the metric "IR (SHR*)" and the text calls it "information ratio". It is not clearly a Sharpe ratio.

### Gaps
- The paper's cost breakdown (Appendix D.5), which supports the "under $10" claim, was not read.
- No independent replication of RD-Agent-Quant results was found.
- RD-Agent's own repository README was not reachable.

## Key Question 4: Limitations (overfitting and sim-to-real gap)

### Takeaway
Almost every project here is a benchmark, backtester or simulator. No source provided live, out-of-sample results for an autonomous RL trader. The sim-to-real gap is therefore unquantified across the set.

### Cited Findings
- **FreqAI RL docs:** the doc calls the default setup "a benchmark" and says it is "not for live production". It warns that poorly trained RL agents can exploit the reward without winning trades, and that the training environment omits strategy callbacks such as `custom_exit` and `custom_stoploss`, per [FreqAI RL docs](https://codeclimate.com/github/freqtrade/freqtrade/docs/freqai-reinforcement-learning.md/source).
- **FreqAI (supervised) docs:** the example strategy is for showcasing and testing, not production. The page has no explicit overfitting warning, per [FreqAI docs](https://codeclimate.com/github/freqtrade/freqtrade/docs/freqai.md/source).
- **FinRL README:** the closing disclaimer says the software is not financial advice and not a recommendation to trade real money. The README has no backtest-overfitting warning, per the [README](https://cdn.jsdelivr.net/gh/AI4Finance-Foundation/FinRL@master/README.md).
- **FinRL-X (blog):** claims walk-forward validation and no-lookahead semantics. It also recommends transaction-cost sensitivity tests and 3–6 months of paper trading before live capital. Its performance figures are not independently verified, per [the blog](https://blog.brightcoding.dev/2026/06/05/finrl-x-the-ai-native-trading-framework-wall-street-doesnt-want-you-to-know).
- **Qlib online module:** simulates a broker with configured costs and fill prices. Real-world slippage and latency are not modelled in the documented setup, per [Qlib online docs](https://qlib.readthedocs.io/en/v0.5.0/hidden/online.html).

### Inferences
- The sim-to-real gap is untested for every project in this list. Expect the gap to be largest for RL agents, which can exploit the simulator's reward and fill assumptions.
- Freqtrade and FinRL-X both recommend a paper-trading period before live use. Neither offers evidence that paper results predict live results.

### Gaps
- No independent replication or live track record was found for any project.
- Related LLM-driven factor-mining papers (QuantEvolve, AlphaCrafter, QuantaAlpha) surfaced in search but were not reviewed. They are outside the non-LLM scope.

## Source Conflicts Summary
- FinRL stars: 11,605 (ecosyste.ms, 19 days ago) vs 17,057 (sourcepulse, 1 week ago).
- FinRL-Trading last activity: 2 weeks ago (sourcepulse) vs 11 months ago (ecosyste.ms).
- ElegantRL: 16 days ago (ecosyste.ms) vs 8 months ago (sourcepulse).
- FinRL-Meta: 1 week ago (sourcepulse) vs about 2 months (ecosyste.ms).
- Qlib latest version: 0.8.0 (changelog) vs 0.9.6 (SourceForge mirror) vs 0.9.8.dev11 (docs build).
