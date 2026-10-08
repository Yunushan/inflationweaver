# InflationWeaver dashboard

The Next.js/TypeScript workspace visualizes nominal and inflation-adjusted indices, drawdowns, purchasing power and multi-asset comparisons. It runs with local uploads and deterministic **synthetic** demo data. It does not fetch live market prices or supply historical ENAG/XU100 data.

```sh
cd web
npm ci
npm run dev
```

Open http://localhost:3000. Use Node.js 22.18 or later; Node.js 24 is recommended.

```sh
npm run typecheck
npm test
npm run build
npm start
```

The default calculator runs entirely in the browser. CSV/JSON uploads are kept in memory and cleared by reloading. To use the Python engine, copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_URL=http://localhost:8000`, then restart/rebuild Next.js. The backend must allow the dashboard origin through its configured CORS list. Browser uploads then go to that API.

Read [dashboard usage and formats](../docs/dashboard.md) for assumptions, supported uploads, alignment behavior and export provenance. Third-party code retains its own licenses: [dependency notices](licenses/README.md). InflationWeaver's first-party source code is under the repository [0BSD license](../LICENSE).
