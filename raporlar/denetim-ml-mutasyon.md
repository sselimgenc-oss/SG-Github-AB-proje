# Mutation testing: risk.py and exit_modes.py

Method: custom ast-based driver (scratchpad/mut.py), run on throwaway worktree copies of the repo; mutmut not attempted. Tests: test_risk_spec, test_risk_impl_smoke, engine/test_engine_05_risk_config, test_exit_modes_cf, engine/test_exit_modes_engine, test_exit_modes_engine_parity, plus engine/test_risk_ladder_impl, engine/test_risk_ladder_spec and test_lesson_exit_modes; `-x -q`, 120 s per-mutant timeout, 4 parallel workers. Baseline: 610 passed, 12 skipped (~60 s).

- Total mutants: 379 (all run, ~50 min)
- Killed: 282
- Survived: 91
- Timeouts: 6 (risk.py 218, 219, 248, 249 x2, 250: infinite-loop mutants in _floor_to_step / size_position nextafter loops; effectively detected)
- Score (killed+timeout)/total: 76.0%

Mutation classes: comparison flips, +/- and * / swaps, and/or swap, numeric constant +1/x2, bool flips, max/min swap, `not` removal. Only inside function bodies (not module constants / dataclass defaults). Equivalent-mutant judgments are by reading, not proven.

## Survivors

| file:line | original -> mutant | verdict |
|---|---|---|
| exit_modes.py:56 | `or` -> `and` | minor gap: `any` (or->and) differs only when exactly one of BE/partial is on; no test asserts it for a single mode |
| exit_modes.py:60 | `or` -> `and` | minor gap: parse_section type guard (or->and) not tested with non-numeric/NaN/bool inputs |
| exit_modes.py:62 | `<=` -> `<` | boundary gap: value exactly at a `bounds` limit (<= vs <) not tested |
| exit_modes.py:136 | `and` -> `or` | REAL GAP: lesson_flags missing-key default / `be is None` precedence untested; mutants could enable breakeven when the flag is absent |
| exit_modes.py:136 | `0` -> `1` | REAL GAP: lesson_flags missing-key default / `be is None` precedence untested; mutants could enable breakeven when the flag is absent |
| exit_modes.py:136 | `0` -> `1` | REAL GAP: lesson_flags missing-key default / `be is None` precedence untested; mutants could enable breakeven when the flag is absent |
| exit_modes.py:138 | `0` -> `1` | REAL GAP: same for the partial flag (absent key default 0->1 would enable partial) |
| exit_modes.py:145 | `and` -> `or` | REAL GAP: None/NaN filter in _best (long) with and->or lets NaN into max(); NaN highs untested |
| exit_modes.py:146 | `and` -> `or` | REAL GAP: same for shorts (lows NaN filter) |
| exit_modes.py:155 | `False` -> `True` | REAL GAP: reached_r(best=None) returning True is not caught; only callers' guards protect |
| exit_modes.py:157 | `>` -> `>=` | REAL GAP (minor): zero/tiny stop distance not exercised (`r > 0` vs `>=`, constant 0->1) |
| exit_modes.py:157 | `0` -> `1` | REAL GAP (minor): zero/tiny stop distance not exercised (`r > 0` vs `>=`, constant 0->1) |
| exit_modes.py:158 | `False` -> `True` | REAL GAP: r==0 guard returning True not caught |
| exit_modes.py:159 | `>=` -> `>` | boundary gap: EPS tolerance edge (best exactly at trigger +-EPS) untested (>= vs >, EPS sign) |
| exit_modes.py:159 | `<=` -> `<` | boundary gap: EPS tolerance edge (best exactly at trigger +-EPS) untested (>= vs >, EPS sign) |
| exit_modes.py:159 | `+` -> `-` | boundary gap: EPS tolerance edge (best exactly at trigger +-EPS) untested (>= vs >, EPS sign) |
| exit_modes.py:177 | `>` -> `>=` | boundary gap: `tighter` equality / EPS band untested; all four mutants survive |
| exit_modes.py:177 | `<` -> `<=` | boundary gap: `tighter` equality / EPS band untested; all four mutants survive |
| exit_modes.py:177 | `+` -> `-` | boundary gap: `tighter` equality / EPS band untested; all four mutants survive |
| exit_modes.py:177 | `-` -> `+` | boundary gap: `tighter` equality / EPS band untested; all four mutants survive |
| exit_modes.py:188 | `or` -> `and` | REAL GAP: partial_due with modes=None (or->and raises AttributeError) untested |
| exit_modes.py:189 | `False` -> `True` | REAL GAP: partial disabled but partial_due returning True is not caught by any test |
| exit_modes.py:200 | `and` -> `or` | minor gap: step==0 / qty==0 invalid inputs; and->or would divide by zero |
| exit_modes.py:200 | `>` -> `>=` | minor gap: step==0 / qty==0 invalid inputs; and->or would divide by zero |
| exit_modes.py:200 | `>` -> `>=` | minor gap: step==0 / qty==0 invalid inputs; and->or would divide by zero |
| exit_modes.py:202 | `+` -> `-` | mostly equivalent: +1e-9 float-rounding fudge, only matters for exact-multiple float cases |
| exit_modes.py:202 | `1e-9` -> `2e-09` | mostly equivalent: +1e-9 float-rounding fudge, only matters for exact-multiple float cases |
| exit_modes.py:203 | `12` -> `24` | equivalent: round(q,12) precision change not observable |
| exit_modes.py:203 | `12` -> `13` | equivalent: round(q,12) precision change not observable |
| exit_modes.py:204 | `-` -> `+` | mostly equivalent: round precision; `-`->`+` makes rest>qty (rest min-qty check effectively off): real gap for the rest-below-min case (see 205) |
| exit_modes.py:204 | `12` -> `24` | mostly equivalent: round precision; `-`->`+` makes rest>qty (rest min-qty check effectively off): real gap for the rest-below-min case (see 205) |
| exit_modes.py:204 | `12` -> `13` | mostly equivalent: round precision; `-`->`+` makes rest>qty (rest min-qty check effectively off): real gap for the rest-below-min case (see 205) |
| exit_modes.py:205 | `or` -> `and` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:205 | `<` -> `<=` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:205 | `<` -> `<=` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:205 | `<=` -> `<` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:205 | `-` -> `+` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:205 | `-` -> `+` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:205 | `1e-12` -> `1.000000000001` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:205 | `1e-12` -> `2e-12` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:205 | `1e-12` -> `1.000000000001` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:205 | `1e-12` -> `2e-12` | REAL GAP (boundary): q/rest vs min_qty at exact equality and 1e-12 tolerance untested; or->and (rest-too-small alone) not isolated |
| exit_modes.py:207 | `>` -> `>=` | REAL GAP (boundary): min_notional checks for q and rest at equality, and price>0/None guards, not isolated |
| exit_modes.py:207 | `or` -> `and` | REAL GAP (boundary): min_notional checks for q and rest at equality, and price>0/None guards, not isolated |
| exit_modes.py:207 | `0` -> `1` | REAL GAP (boundary): min_notional checks for q and rest at equality, and price>0/None guards, not isolated |
| exit_modes.py:207 | `<` -> `<=` | REAL GAP (boundary): min_notional checks for q and rest at equality, and price>0/None guards, not isolated |
| exit_modes.py:207 | `<` -> `<=` | REAL GAP (boundary): min_notional checks for q and rest at equality, and price>0/None guards, not isolated |
| risk.py:70 | `1` -> `2` | equivalent: split(':',1) vs 2 differs only for pairs with 2+ colons |
| risk.py:100 | `<=` -> `<` | REAL GAP: zero in a positive-only field (e.g. target_trade_risk=0) accepted when `<=` becomes `<` |
| risk.py:102 | `<` -> `<=` | equivalent: zero fee/slippage/mmr is rejected anyway by HARD_LIMITS min_* lower bounds |
| risk.py:139 | `-` -> `+` | REAL GAP: paper_config unknown-key check (set - set -> set + set raises TypeError) not covered by these tests |
| risk.py:151 | `or` -> `and` | REAL GAP for or->and (loosening via tightened() not rejected here); `<=`->`<` equivalent (0 rejected by RiskConfig) |
| risk.py:151 | `<=` -> `<` | REAL GAP for or->and (loosening via tightened() not rejected here); `<=`->`<` equivalent (0 rejected by RiskConfig) |
| risk.py:201 | `<=` -> `<` | minor gap: leverage==0 direct call would raise ZeroDivisionError instead of ValueError; check_entry guards earlier |
| risk.py:219 | `>` -> `>=` | equivalent: `>`->`>=` changes result by 1 ulp in a defensive loop |
| risk.py:220 | `0.0` -> `1` | REAL GAP (defensive branch): nextafter loop in _floor_to_step never entered in tests |
| risk.py:226 | `0.0` -> `1` | minor gap: default min_notional=0.0 -> 1 undetected; tests always pass min_notional or large notionals |
| risk.py:234 | `<=` -> `<` | minor gap: qty_step==0 -> Decimal error instead of ValueError, boundary untested |
| risk.py:236 | `or` -> `and` | mostly equivalent: bad equity/entry/leverage/min_notional caught downstream (qty>0, margin checks); stop==0 and leverage==0 boundaries untested (minor gap) |
| risk.py:236 | `<=` -> `<` | mostly equivalent: bad equity/entry/leverage/min_notional caught downstream (qty>0, margin checks); stop==0 and leverage==0 boundaries untested (minor gap) |
| risk.py:236 | `<=` -> `<` | mostly equivalent: bad equity/entry/leverage/min_notional caught downstream (qty>0, margin checks); stop==0 and leverage==0 boundaries untested (minor gap) |
| risk.py:236 | `<=` -> `<` | mostly equivalent: bad equity/entry/leverage/min_notional caught downstream (qty>0, margin checks); stop==0 and leverage==0 boundaries untested (minor gap) |
| risk.py:236 | `<=` -> `<` | mostly equivalent: bad equity/entry/leverage/min_notional caught downstream (qty>0, margin checks); stop==0 and leverage==0 boundaries untested (minor gap) |
| risk.py:241 | `>` -> `>=` | equivalent: per_qty cannot be 0 when entry != stop |
| risk.py:245 | `>` -> `<` | equivalent: defensive 1-ulp qty adjustment, unobservable above ulp level |
| risk.py:245 | `>` -> `>=` | equivalent: defensive 1-ulp qty adjustment, unobservable above ulp level |
| risk.py:246 | `0.0` -> `1` | REAL GAP (defensive branch): never entered in tests |
| risk.py:254 | `<` -> `<=` | boundary gap: qty*entry == min_notional exactly (allowed) untested |
| risk.py:257 | `>` -> `>=` | equivalent: target_trade_risk <= max_trade_risk, equality practically unreachable (defensive) |
| risk.py:261 | `>` -> `>=` | boundary gap: margin == equity exactly (allowed) untested |
| risk.py:282 | `<=` -> `<` | equivalent: qty_step<=0 also rejected by size_position (still a deny, message differs) |
| risk.py:286 | `or` -> `and` | equivalent: equity/day_start <=0 rejected downstream (deny reason text differs only) |
| risk.py:286 | `<=` -> `<` | equivalent: equity/day_start <=0 rejected downstream (deny reason text differs only) |
| risk.py:286 | `<=` -> `<` | equivalent: equity/day_start <=0 rejected downstream (deny reason text differs only) |
| risk.py:288 | `or` -> `and` | equivalent: entry/stop<=0 rejected downstream by size_position (message differs only) |
| risk.py:288 | `<=` -> `<` | equivalent: entry/stop<=0 rejected downstream by size_position (message differs only) |
| risk.py:288 | `<=` -> `<` | equivalent: entry/stop<=0 rejected downstream by size_position (message differs only) |
| risk.py:305 | `>=` -> `>` | equivalent: stop==entry rejected by size_position ('stop mesafesi sifir') -> deny either way |
| risk.py:307 | `<=` -> `<` | equivalent: same as 305 for short |
| risk.py:332 | `or` -> `and` | equivalent: defensive re-validation of size_position output; size_position already enforces all of it (would need a monkeypatched size_position test) |
| risk.py:332 | `<=` -> `<` | equivalent: defensive re-validation of size_position output; size_position already enforces all of it (would need a monkeypatched size_position test) |
| risk.py:332 | `<=` -> `<` | equivalent: defensive re-validation of size_position output; size_position already enforces all of it (would need a monkeypatched size_position test) |
| risk.py:332 | `<` -> `<=` | equivalent: defensive re-validation of size_position output; size_position already enforces all of it (would need a monkeypatched size_position test) |
| risk.py:332 | `<` -> `<=` | equivalent: defensive re-validation of size_position output; size_position already enforces all of it (would need a monkeypatched size_position test) |
| risk.py:333 | `>` -> `>=` | equivalent: redundant with line 332 / size_position's own max_trade_risk check |
| risk.py:335 | `>` -> `>=` | equivalent: margin > equity already rejected in size_position |
| risk.py:339 | `<` -> `<=` | REAL GAP (boundary): entry-liq distance exactly == safety_factor*stop distance (allowed) untested |
| risk.py:343 | `>` -> `>=` | REAL GAP (boundary): total open risk exactly == max_open_risk*equity untested |
| risk.py:347 | `>` -> `>=` | REAL GAP (boundary): same-direction risk exactly == limit untested |
| risk.py:351 | `>` -> `>=` | REAL GAP (boundary): daily loss budget exactly == limit untested |
| risk.py:354 | `>` -> `>=` | REAL GAP (boundary): total margin exactly == equity untested |
