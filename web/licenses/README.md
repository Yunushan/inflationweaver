# Frontend dependency notices

InflationWeaver's first-party frontend source is licensed under 0BSD. Dependency code is not relicensed by this repository.

| Direct dependency | Version | License |
| --- | --- | --- |
| Next.js | 16.4.0 | MIT |
| React / React DOM | 19.3.0 | MIT |
| TradingView Lightweight Charts™ | 5.2.1 | Apache-2.0; TradingView attribution required |
| Papa Parse | 5.7.0 | MIT |
| TypeScript | 7.0.2 | Apache-2.0 |
| DefinitelyTyped declarations | See `package-lock.json` | MIT |

The locked transitive dependency tree is in `package-lock.json`. Each installed dependency distributes its own license information; preserve those notices when redistributing its code.

The chart displays a public TradingView attribution and link. [The upstream notice](lightweight-charts-NOTICE.txt) and [Apache license](lightweight-charts-LICENSE.txt) are retained here. The chart library also exposes its attribution logo. See the [official requirements](https://tradingview.github.io/lightweight-charts/docs/5.0) and [upstream NOTICE](https://github.com/tradingview/lightweight-charts/blob/master/NOTICE).

Dependency versions were verified against the npm registry on 2026-10-08. Update exact versions and regenerate the lockfile as part of normal maintenance; an exact pin is not a claim that future versions will remain secure.
