# Preparing XU100 analysis from 1986 onward

InflationWeaver accepts long historical inputs. It does not bundle a verified 1986–2026 XU100/CPI database or reconstruct missing observations from memory. This guide describes the data work necessary for a credible long-horizon report.

## Historical anchor

[Borsa İstanbul's XU100 page](https://www.borsaistanbul.com/en/index/xu100) gives the BIST 100 start date as **1 January 1986** and a current-scale initial value of **0.01**. The date is an index reference; it need not be the first trading date present in a provider's file.

Do not create a 1 January close because an index factsheet supplies a base value. Use the actual chosen source observation. The engine records the first asset observation on or after a requested base. Requesting `1986-01-01` does not establish coverage if the input begins decades later; inspect the actual base and the input's earliest observation.

## Avoid scale discontinuities

Long XU100 exports may reflect different historical display conventions:

| Event | Nature | What to verify |
| --- | --- | --- |
| 1997 index simplification | Earlier index values were divided by 100; January 1986 reference became 1 instead of 100 | Whether the provider has already restated pre-1997 history |
| 2005 currency reform | Six zeros were removed from Turkish-lira currency amounts | Whether cash/FX/asset amount histories are consistently expressed in TRY; an index point is not automatically a cash lira |
| 2020 index simplification | Specified TL-denominated BIST equity index levels were divided by 100 | Whether old history is already on the current index scale |

The official [Borsa İstanbul investor guide](https://www.borsaistanbul.com/data/kilavuzlar/Borsa_Istanbul_For_Investors.pdf) describes the earlier index simplification. The [2020 circular and old/new starting values](https://www.borsaistanbul.com/files/dividing-tl-based-bist-stock-index-values-by-100-and-related-changes-at-derivatives-market-no-2020-12.pdf) describes the later division and comparison rule. [TCMB's currency-reform material](https://tcmb.gov.tr/wps/wcm/connect/4cbe287f-6637-4a5e-8a07-a4a99e12d476/04-08.pdf?MOD=AJPERES) describes the 2005 removal of six currency zeros.

These events are different. Do not multiply every dataset by all factors mechanically. A provider may already have restated every observation. Verify overlapping observations before transforming values; a second adjustment would introduce a false discontinuity. Keep raw exports and document every applied scale factor and date range. This release does not automatically infer unknown vendor-scale conventions.

## Price index versus total return

[Borsa İstanbul's index FAQ](https://www.borsaistanbul.com/en/faq/indices) identifies cash-dividend treatment as the distinction between price and return indices. XU100 price analysis describes index-price performance. It is not a dividend-reinvestment wealth calculation.

Use the exact price or return series intended by the research question. Do not label an XU100 price result “total investor return.” A total-return curve still may differ from an investor's net return after tax, execution and fund costs. The engine accepts either positive price or wealth levels but does not add missing dividends automatically.

## CPI across historical base changes

A modern base-year CPI dataset need not itself extend to 1986. Older Turkish CPI bases require a documented historical bridge or compatible monthly changes. Avoid concatenating raw levels from different bases.

1. Obtain official monthly CPI levels or independently verified month-on-month rates for every required month.
2. Record each series' base definition, basket/methodological breaks, provider, date range and release/vintage policy.
3. Select an exact common observation where adjacent level series overlap. Review available overlap, not just the numeric scale.
4. Scale the successor at the common observation and document the link. The generic `splice_cpi` routine labels a construction as hybrid/synthetic; it does not certify official historical methodology.
5. Check monthly continuity and calculate rates around every boundary against source releases.
6. Confirm that CPI covers the base and every asset point within the chosen maximum staleness. A large staleness allowance is not a substitute for missing months.

Re-referencing alone changes an arbitrary scale, so ratios remain invariant. Methodology or basket changes are economically consequential and must remain visible even when the numeric level is smooth.

## ENAG and hybrid history

[ENAG's published materials](https://enagrup.org/) are a distinct contemporary inflation source; they do not provide observed ENAG CPI back to 1986. Some bulletins publish monthly and annual rates. Import the verified **monthly** rates as `monthly_rate`, chain from a preceding-month anchor, and retain the bulletins and their public availability dates. Do not exponentiate a headline annual rate into a fabricated monthly path.

For a 1986-to-present TÜİK–ENAG scenario:

- Use verified official historical CPI before a documented switch.
- Supply verified ENAG level or monthly-rate history around and after that switch.
- Require exact common observation dates for scaling and verify how the chain anchor was formed.
- State the switch, source identities, scale, data frequency and any basket changes in every report.
- Describe the result as a **constructed TÜİK–ENAG hybrid**, never as ENAG observed since 1986.
- Run a separate TÜİK-only comparison over the same asset dates when available.

The construction is analytic. It does not retroactively validate earlier prices against a later research group's methodology.

## Acquisition and provenance

[Borsa İstanbul's historical data page](https://www.borsaistanbul.com/en/index/index-data) points to its data distribution channel. Rights and access vary by dataset/provider. The project's code license does not grant ownership of exchange data. Verify [Borsa İstanbul's data and index rights](https://www.borsaistanbul.com/en/indices) before redistribution or product publication.

Use [TÜİK's inflation portal](https://data.tuik.gov.tr/Kategori/GetKategori?p=enflasyon-ve-fiyat-106&dil=2), [TCMB inflation tables](https://www.tcmb.gov.tr/wps/wcm/connect/en/tcmb%2Ben/main%2Bmenu/statistics/inflation%2Bdata), and a verified EVDS query/export where suitable. Monthly/annual percentage tables are not automatically an unbroken CPI-level archive. FRED and OECD add useful international comparators but do not guarantee every Turkish series or the required early historical frequency.

For each real input record at least:

| Field | Reason |
| --- | --- |
| Provider and exact series ID | Distinguishes similar symbols/baskets |
| Source URL and retrieval date | Makes acquisition reviewable |
| Earliest/latest observation and frequency | Establishes actual coverage |
| Currency, units and quote direction | Prevents incompatible deflation |
| Price/total-return and corporate actions | Explains economic meaning |
| Scale transformations and overlap | Prevents fictitious gains or losses |
| Original release and vintage policy | Defines what was known when |
| License/access conditions | Governs redistribution |
| Raw/transformed file checksums | Supports reproducibility |

## Acceptance checklist

Before publishing an “1986 onward” report, confirm actual first/last observations; source-backed scale continuity; complete monthly compounding inputs where used; same-currency deflation; verified overlapping CPI links; source attribution; visible hybrid/demo distinctions; actual base, display dates, and staleness; and price-versus-total-return labeling.

If any required decade, month, release, adjustment or overlap is unavailable, narrow the report period or acquire the missing source data. Do not fill it with demonstration data. Tests can verify algorithms without establishing historical source coverage.
