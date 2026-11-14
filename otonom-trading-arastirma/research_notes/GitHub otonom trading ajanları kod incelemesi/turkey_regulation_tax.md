# Turkey: legal, regulatory and tax situation (as of Nov 2026) for an individual running an autonomous AI trading bot on own account

Not legal or tax advice. Research done 15 Nov 2026 via web search/fetch; many sources are secondary (law-firm blogs, news, broker PDFs). Primary sources (Resmi Gazete, SPK, GİB, mevzuat.gov.tr) were not fetched directly; items should be verified there before reliance.

## 1. SPK / Borsa İstanbul rules on algorithmic/API trading for retail investors

### Takeaway
A retail investor may run their own bot on their own account; no SPK registration for self-directed own-account algo use was found. Orders must flow through a Turkish member broker (aracı kurum), which carries the exchange-level algo obligations. Broker API/algo availability for retail is broker-specific and I could not confirm any broker's public retail REST API terms.

### Cited Findings
- Per a Turkish law-firm note: an investor running self-written or purchased software on their own account does not face the unlicensed-activity problem; other rules still apply (broker terms, market-conduct rules). — [hukukcularevi.com](https://hukukcularevi.com/borsa-robotu-al-sat-botu-algoritmik-islem-izinsiz-yatirim-danismanligi-iii-37-1-m45-m37-spkn-109-borsa-istanbul-algoritmik-prosedur/)
- Same source: customers cannot send orders directly to Borsa İstanbul; orders go through the member's systems/channels (e.g., approved API). Members must run pre-trade risk controls on algorithmic orders, notify the exchange in writing about algo software, and are directly liable to the exchange; the exchange can suspend users whose algorithms disrupt the market. — [hukukcularevi.com](https://hukukcularevi.com/borsa-robotu-al-sat-botu-algoritmik-islem-izinsiz-yatirim-danismanligi-iii-37-1-m45-m37-spkn-109-borsa-istanbul-algoritmik-prosedur/)
- Same source: user risks include order spoofing/wash-style behaviour under SPKn m.107/1 or m.104 (market manipulation); errors are the user's responsibility; executed trades generally cannot be cancelled (SPKn m.79/1). — [hukukcularevi.com](https://hukukcularevi.com/borsa-robotu-al-sat-botu-algoritmik-islem-izinsiz-yatirim-danismanligi-iii-37-1-m45-m37-spkn-109-borsa-istanbul-algoritmik-prosedur/)
- Borsa İstanbul publishes an "Algoritmik Emir İletim Sistemleri Taahhütnamesi" (undertaking form) used for algorithmic order-routing systems (member-level document). — [Borsa İstanbul PDF](https://www.borsaistanbul.com/files/algoritmik-emir-iletim-sistemleri-taahhutnamesi.pdf)
- Broker examples: Deniz Yatırım describes HFT on selected BIST equity/VIOP instruments (colocation) and data-vendor terminals (ideAlgo, Matriks IQ, Matriks Kahin) where users write custom algorithms and place automated orders; page does not state eligibility or mention an API. — [Deniz Yatırım](https://www.denizyatirim.com/AlgorithmicOperations)
- Matriks publishes a FIX gateway document (FIX connectivity to brokers) — existence only; eligibility for retail not verified. — [Matriks FIX Gateway](https://matriksdata.com/website/uploads/FAST FIX API-FIX GATEWAY-MTXR.pdf)

### Inferences
- Practical path for BIST: a broker-approved API/terminal (Matriks/ideAlgo-type or broker FIX/API), not direct market access. Broker contract terms and risk limits will be the binding constraint.
- A bot with spoofing/layering-like behaviour exposes the owner personally to market-abuse provisions regardless of "own account" status.

### Gaps
- No primary-source SPK text (e.g., III-39.1 or exchange algo procedure article numbers) was fetched; article numbers above are as cited by the law-firm blog.
- No confirmed list of Turkish brokers offering retail programmatic REST/FIX API and their conditions.
- No explicit SPK "registration requirement" for retail algo users found (absence of evidence, not confirmed absence).

## 2. Crypto: Law 7518, KVHS licensing, foreign exchanges, 2025-26 changes

### Takeaway
Law 7518 (2 July 2024) put crypto-asset service providers (KVHS) under SPK licensing. SPK's rules target providers, not users; Turkish residents may use foreign platforms on their own initiative if those platforms do not market in Turkey. The proposed 2026 crypto transaction tax / 10% withholding was withdrawn from parliament on 27 March 2026 (not enacted, per sources found).

### Cited Findings
- Law 7518 brought crypto service providers under capital markets law, dated 2 July 2024. — [hukukcularevi.com travel-rule note](https://hukukcularevi.com/kripto-travel-rule-sinir-otesi-transfer-masak/)
- SPK KVHS rules (CNN Türk, 13 Mar 2025): min paid-in capital 150m TL (custody 500m TL); TÜBİTAK security standards; liquid reserve at least 3% of customer assets; bank-only money transfers; leveraged trading, short selling and margin lending prohibited. — [CNN Türk](https://www.cnnturk.com/ekonomi/kripto-varliklara-yeni-duzenleme-spkdan-kripto-platformlarina-sermaye-ve-guvenlik-sarti-2254716)
- Same: Turkish residents may use foreign platforms on their own initiative, provided those platforms do not promote, advertise or market in Turkey; foreign entities that open a workplace or advertise directly to Turkish users fall under local rules. — [CNN Türk](https://www.cnnturk.com/ekonomi/kripto-varliklara-yeni-duzenleme-spkdan-kripto-platformlarina-sermaye-ve-guvenlik-sarti-2254716)
- SPK's published lists ("Faaliyette Bulunanlar" and "Tasfiye Beyanında Bulunanlar") are declaration records, not licenses. SPKn m.99/A-type measures include halting activity, website access bans and notifying prosecutors; foreign platforms are treated as unlicensed when targeting Turkish residents (Turkish office, Turkish-language site, direct promotion). The same note says the user is not the offender ("kullanıcı ... fail konumunda değildir") for this regulation, but gives no user-penalty detail and does not directly say foreign-exchange use is legal. — [hukukcularevi.com](https://hukukcularevi.com/spk-kripto-listesi-lisans-mi-demek/)
- Access bans on many unlicensed/foreign crypto sites have been reported (e.g., 108 exchanges). — [Paratic](https://paratic.com/spk-harekete-gecti-108-kripto-borsasina-erisim-engeli/) (headline-level only; date and current status not verified)
- Unlicensed provision of crypto services: criminal sanctions exist under the amended law (details not verified here). — [hukukcularevi.com](https://hukukcularevi.com/izinsiz-kripto-platformu-isletme-cezasi/) (not fetched; headline only)
- Tax proposal history: draft in omnibus bill (March 2026) with 0.3 per mille (0.03%) transaction tax (rate-setting range 0 to 5x by President) and 10% quarterly withholding on gains on SPK-licensed platforms; passed Plan and Budget Committee. — [Para Dergi, 16 Mar 2026](https://www.paradergi.com.tr/finans/2026/03/16/kripto-varliklara-islem-vergisi); Finansopia (6 Mar 2026) reported the 10% withholding as removed at that stage, conflicting — [Finansopia](https://www.finansopia.com/ekonomi/kripto-para/kripto-borsalarinda-islem-vergisi-yuzde-003-oldu/). Note the sources also disagree on rate formatting (0.3% vs 0.03% vs "0.003%").
- Withdrawal: On 27 Mar 2026, AK Party's Ömer İleri announced withdrawal of articles 1, 3, 4, 5 (crypto tax) from the omnibus bill "for reconsideration"; may return in a separate bill, none confirmed. — [Bloomberg HT](https://www.bloomberght.com/kripto-varliklara-vergi-teklifi-geri-cekildi-3773037)
- Law 7582 (published 4 June 2026 per Cott; the foreign-income-exemption communiqué says 7582 is dated 21/5/2026 — date discrepancy) does not mention crypto in PwC/Cott summaries. — [PwC](https://www.pwc.com.tr/tr/Hizmetlerimiz/vergi/vergi-bultenleri/2026/7582-sayili-kanunun-vergi-duzenlemeleri.pdf); [Cott](https://www.cottgroup.com/tr/administrative-fine-amounts-in-kvkk-for-2022/item/law-no-7582-introducing-significant-changes-to-turkish-tax-legislation-published). Its asset-repatriation (varlık barışı) regime names cash, gold, FX and capital market instruments abroad; crypto not named.
- MASAK: Art. 24/A crypto transfer-message (travel rule) added Dec 2024 (RG 32763), in force Feb 2025; thresholds raised from 15,000 TL to 30,000 TL by amendment published 7 Oct 2026 (RG 33393). Transfers to self-hosted wallets not prohibited but risk-controlled; sending provider must meet its obligations; incoming funds from foreign platforms may be questioned by banks, so keep records. — [hukukcularevi.com](https://hukukcularevi.com/kripto-travel-rule-sinir-otesi-transfer-masak/); [Alomaliye](https://www.alomaliye.com/2026/10/07/masakta-kimlik-tespiti-sinirlari-iki-katina-cikti/)
- A 2021 CBRT regulation bars using crypto assets for payments (not trading). — [hukukcularevi.com](https://hukukcularevi.com/kripto-travel-rule-sinir-otesi-transfer-masak/)

### Inferences
- Binance Global / Bybit / Hyperliquid use by an individual is not shown to be a user offence, but it is a grey/risk area: sites may be blocked, bank transfers to them can trigger questions, and no Turkish investor protection applies. DEX/Hyperliquid specifically was not addressed in any source found.
- Leverage/perps are prohibited for licensed Turkish platforms; foreign perp venues are by definition outside that licensing, so using them is outside the local protected perimeter.
- As of the sources found, no crypto-specific transaction tax or withholding is in force; verify nothing was passed after 27 Mar 2026 (Apr-Nov 2026 searches surfaced none).

### Gaps
- Current (Nov 2026) status of the full list of KVHS licences granted and which platforms are blocked: not retrieved.
- Whether any separate crypto tax bill was re-submitted after March 2026: not found; cannot confirm absence.
- No source specifically on Hyperliquid or DEXs for Turkish residents.
- Primary SPK/Resmi Gazete texts not directly fetched.

## 3. Foreign brokers (Alpaca, Interactive Brokers) from Turkey

### Takeaway
IBKR lists Turkey among countries where accounts can be opened. Alpaca's direct availability for Turkish residents was not confirmed; instead Alpaca serves Turkey via partner brokers (Midas, Global Menkul Değerler).

### Cited Findings
- IBKR's open-account country list includes "Turkey" (between Tunisia and Turkmenistan). — [IBKR country list](https://www.interactivebrokers.ca/en/accounts/open-account-country-list.php)
- Alpaca's support page does not list countries and directs users to support to check. — [Alpaca support](https://alpaca.markets/support/countries-alpaca-is-available)
- Turkish brokerage Global Menkul Değerler partnered with Alpaca (announced 9 Oct 2025) to offer US equities from $1 via its own app; article does not say Turkish end users get direct API access. — [Alpaca blog](https://alpaca.markets/blog/global-menkul-degerler-partners-with-alpaca-to-expand-access-to-us-equities-for-turkish-investors/)
- Midas is a Turkish digital brokerage built on Alpaca Broker API. — [Alpaca blog](https://alpaca.markets/blog/midas-launches-turkeys-first-fully-digital-stock-brokerage-with-alpaca-broker-api)
- Note: SPK has an obligation-style concern where foreign brokers solicit Turkish residents (see section 2 logic for crypto); no SPK source found specifically restricting residents from using licensed foreign brokers on their own initiative.

### Inferences
- IBKR is the most straightforward foreign API route; its API terms and Turkish tax-ID reporting (W-8BEN) not verified here.
- Foreign-account use creates TL-based tax reporting and bank-transfer/FX documentation duties (section 4).

### Gaps
- Alpaca direct individual account eligibility for Turkey (trading API) unconfirmed.
- Foreign-exchange control rules for outward transfers: Turkey broadly liberalized under Decree 32; not researched here.
- Whether foreign brokers' marketing in Turkish affects legality: no source.

## 4. Taxation in 2026

### Takeaway
BIST stock gains for individuals: 0% withholding, not declared (Geçici Madde 67), but frequent trading may raise "commercial earnings" questions (not sourced). Foreign securities gains: declared in annual return regardless of amount, taxed at progressive rates, computed in TL (FX effects count). Crypto: no enacted specific regime found; the March 2026 proposal was withdrawn. A new 20-year foreign-income exemption exists only for new tax residents.

### Cited Findings
- BIST-listed shares, individuals (acquired after 1.1.2006): withholding 0% under Geçici Madde 67; gains not declared. Non-BIST shares: declared under general rules, PPI indexation if increase 10% or more. — [Garanti BBVA 2025 table](https://garantibbva.com.tr/content/dam/public-website/pdf/yatirim/vergilendirme/mk-vergilendirme-2025.pdf) (2025 table; 2026 not verified)
- Foreign stock gains (2026): declared annually regardless of amount, no exemption amount or threshold; TL conversion at transaction-date rates; Yİ-ÜFE indexation if 10% or more; same-year losses on foreign securities offset gains of that group only; brokerage fees and custody deductible; leverage interest not deductible. — [Yapı Kredi 2026 note](https://www.yapikredi.com.tr/medium/file/yabanci-hisse-senedi-gelirlerinde-2026-yili-vergi-durumu_71999/view); also [Muhasebetr](https://www.muhasebetr.com/yazarlarimiz/hayatiasilturk/003/)
- Foreign dividends: declare if the year's total exceeds 22,000 TL (2026); progressive rates 15% to 40% per Yapı Kredi; foreign tax credit possible under GVK m.123. — [Yapı Kredi](https://www.yapikredi.com.tr/medium/file/yabanci-hisse-senedi-gelirlerinde-2026-yili-vergi-durumu_71999/view)
- New GVK m.20/D (Law 7582): individuals who become Turkish tax residents from 1 Jan 2026 and had no Turkish residence/tax liability in the prior three calendar years can exclude foreign-sourced income for 20 years, via exemption certificate application; communiqué Seri No 333 published 4 July 2026. Not relevant to long-term residents. — [Alomaliye](https://www.alomaliye.com/2026/07/04/gelir-vergisi-genel-tebligi-seri-no-333/); [PwC](https://www.pwc.com.tr/tr/Hizmetlerimiz/vergi/vergi-bultenleri/2026/7582-sayili-kanunun-vergi-duzenlemeleri.pdf)
- Crypto gains: pre-March-2026 secondary sources discuss offshore-platform gains being declarable under income tax brackets only as a possibility ("may come up"); the dedicated crypto tax article (new GVK article treating crypto as intangible rights, value-increase gains) was part of the withdrawn articles. — [Finansopia](https://www.finansopia.com/ekonomi/kripto-para/kripto-borsalarinda-islem-vergisi-yuzde-003-oldu/); [Para Dergi](https://www.paradergi.com.tr/finans/2026/03/16/kripto-varliklara-islem-vergisi); [Bloomberg HT](https://www.bloomberght.com/kripto-varliklara-vergi-teklifi-geri-cekildi-3773037)

### Inferences
- A bot with high turnover on a foreign broker generates many TL-converted lots; record-keeping (per-trade FX rates, FIFO) is a practical burden.
- Whether crypto trading gains are taxable today under general GVK principles is contested in sources and I did not find a definitive GİB position; treat as unresolved.

### Gaps
- 2026 BIST treatment verified only via 2025 table; no check of any 2026 change to Geçici 67.
- Rule on frequent trading being treated as commercial earnings (ticari kazanç): not sourced.
- Crypto: no GİB ruling/official position found; no confirmation that Binance/foreign-exchange gains must be declared.
- Foreign-account declaration/reporting beyond income tax (e.g., CRS exchange) not researched.

## 5. Own account vs managing others' money

### Takeaway
Own-account bot use is unlicensed-safe per the cited note; signals to others is investment advice and auto-executing in a third party's account is portfolio management, both reserved for licensed firms.

### Cited Findings
- Sending buy/sell signals to a specific person or a group with similar profiles is investment advisory (III-37.1 m.45/1); tools that copy trades are advisory (m.45/3); automated execution in a client's account is portfolio management (m.37/3); only SPK-licensed firms may provide these (m.38/1, m.46/1). — [hukukcularevi.com](https://hukukcularevi.com/borsa-robotu-al-sat-botu-algoritmik-islem-izinsiz-yatirim-danismanligi-iii-37-1-m45-m37-spkn-109-borsa-istanbul-algoritmik-prosedur/)
- Penalty for unlicensed investment services: 2 to 5 years' imprisonment and 5,000 to 10,000 days of judicial fines (SPKn m.109/2); SPK can order access bans (m.99/3); prosecution requires SPK complaint (m.115/1). — same source
- Software sale alone generally not regulated; becomes regulated with personalized/group signals, control of client accounts or return-based marketing. — same source
- For crypto, equivalent unlicensed-activity logic applies to anyone providing services to others in Turkey (KVHS regime). — [hukukcularevi.com](https://hukukcularevi.com/spk-kripto-listesi-lisans-mi-demek/)

### Inferences
- Pooling friends'/family funds, or running the bot on accounts you have power of attorney over, crosses into portfolio management territory.

### Gaps
- Family/limited-power-of-attorney edge cases: no source.
- Primary SPK text not verified.
