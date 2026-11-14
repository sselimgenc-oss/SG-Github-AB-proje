# Verified GitHub metadata: autonomous trading agent repos

Retrieved: 2026-11-14 (UTC, sandbox clock). Method: direct `gh api repos/OWNER/NAME` calls returned HTTP 403 ("GitHub access to this repository is not enabled for this session") for every target repo, so all values come from `gh search repos` (GitHub search API). Search-index values can lag the live repo by hours to days. The `gh` CLI also reported an invalid GH_TOKEN, but the search endpoint still answered. "last push" is the search index's `pushedAt`. "Archived" is the `isArchived` flag.

| repo | stars | license | last push | archived | one-line description | note |
|---|---|---|---|---|---|---|
| TauricResearch/TradingAgents | 122590 | Apache-2.0 | 2026-11-04 | no | Multi-agents LLM financial trading framework | Official repo |
| virattt/ai-hedge-fund | 64678 | MIT | 2026-11-09 | no | AI hedge fund team of LLM agents | Official repo |
| AI4Finance-Foundation/FinRobot | 8425 | Apache-2.0 | 2026-10-24 | no | Open-source AI agent platform for financial applications using LLMs | Official repo |
| AI4Finance-Foundation/FinRL | 17071 | MIT | 2026-11-03 | no | Financial reinforcement learning library | Official repo |
| AI4Finance-Foundation/FinRL-Trading | 3941 | Apache-2.0 | 2026-09-18 | no | Description now reads "FinRL-X: AI-native modular infrastructure for quantitative trading" | Name matches; description differs from the FinRL trading-agent framework |
| pipiku915/FinMem-LLM-StockTrading | 973 | MIT | 2024-08-18 | no | LLM trading agent with layered memory and character design | Last push is about 2 years old |
| The-FinAI/FinCon | 72 | MIT | 2026-10-08 | no | Multi-agent LLM system with conceptual verbal reinforcement (arXiv:2407.06567) | Official repo |
| MingyuJ666/Stockagent | 719 | none (search API returns no license) | 2026-06-16 | no | LLM stock trading in simulated real-world environments (TIST) | No license declared |
| FinStep-AI/ContestTrade | 680 | Apache-2.0 | 2025-12-22 | no | Multi-agent trading system based on an internal contest mechanism | Official repo |
| HKUDS/AI-Trader | 23269 | none (search API returns no license) | 2026-06-11 | no | "100% fully-automated agent-native trading" | No license declared per API |
| NoFxAiOS/nofx | 13282 | AGPL-3.0 | 2026-11-04 | no | AI trading terminal assistant for US stocks, commodities, forex, crypto | Official NoFx repo (matches the NoFxAiOS org) |
| wquguru/nof0 | 2754 | none (search API returns no license) | 2025-12-07 | no | Open-source AI trading arena reproducing NOF1 Alpha Arena | Last push about 11 months old |
| alsk1992/CloddsBot | 3109 | MIT | 2026-11-13 | no | Open-source AI trading agent across prediction markets, crypto and DEXs, built on Claude | Highest-star match; several forks and mirrors also exist (alejandrozinz-eng, Bmaxiomq, INAPP-Mobile/clodds). Official owner not confirmed |
| elizaOS/eliza | 19873 | MIT | 2026-11-14 | no | Open-source agentic operating system | General agent framework, not trading-specific |
| sendaifun/solana-agent-kit | 1764 | Apache-2.0 | 2026-05-14 | no | Connects AI agents to Solana protocols | Official repo |
| Polymarket/agents | 3819 | MIT | 2024-11-05 | **yes** | Trade autonomously on Polymarket using AI agents | Archived; no pushes in about 2 years |
| microsoft/qlib | 50285 | MIT | 2026-11-04 | no | AI-oriented quant investment platform | Official repo |
| microsoft/RD-Agent | 15375 | MIT | 2026-10-21 | no | Automates data-driven AI R&D; integrates with Qlib | Official repo |
| freqtrade/freqtrade | 56889 | GPL-3.0 | 2026-11-12 | no | Free, open-source crypto trading bot | Official repo |
| tensortrade-org/tensortrade | 7271 | Apache-2.0 | 2026-02-19 | no | Open-source RL framework for training, evaluating, deploying trading agents | Last push about 9 months old |
| hsliuping/TradingAgents-CN | 32955 | "Other" (API did not identify an SPDX license) | 2026-11-14 | no | Chinese-language multi-agent LLM financial trading framework (enhanced TradingAgents-CN) | Check LICENSE file; the API did not parse one |
| Infinite Bagholder | not found | not found | not found | not found | not found | Lookup failed: no repo matched "Infinite Bagholder", "infinite-bagholder" or "bagholder" as a trading agent. The closest hits are unrelated (ZeframLou/bagholder, bagholder-bets). Name or owner needed |
| NightWatcher-V2 | 1 | Other | 2026-07-23 | no | Autonomous trading agent powered by social sentiment analysis and AI | Match is LNSTT369/NightWatcher-V2; very low stars, owner not confirmed as the intended project |
| AgenticTrading | 897 | Other | 2026-11-05 | no | Not in search index (no description) | Match is Open-Finance-Lab/AgenticTrading. Other candidates: BenPomme/agentictrading (8 stars, AGPL-3.0, last push 2026-03-20) |
| open-nof1.ai | 805 | none (search API returns no license) | 2026-04-01 | no | Open-source AI trading platform in real markets | Name match is SnowingFox/open-nof1.ai. Alternative: 195440/nof1.ai (693 stars, AGPL-3.0, last push 2026-05-15, description "Open nof1.ai") |

## Lookup failures and caveats

- No direct repo endpoint returned data (HTTP 403 for all 22 named repos), so every value is from search-index results.
- Infinite Bagholder: no match found.
- Ambiguous picks, where the chosen repo is a best guess: CloddsBot, NightWatcher-V2, AgenticTrading, open-nof1.ai, and the FinRL-Trading description change.
- Licenses marked "none" are what the search API returned. Some repos may still have a LICENSE file that the API did not parse. Verify before reuse.
