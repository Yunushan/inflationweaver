# Contributing

Thank you for improving InflationWeaver. Contributions should make financial calculations reproducible, preserve source identity, and distinguish implemented functionality from data-access assumptions.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
```

On PowerShell, activate with `.venv\Scripts\Activate.ps1`. For dashboard work:

```bash
cd web
npm ci
npm run typecheck
npm test
npm run build
```

Use Python 3.11+ and Node.js 22+. Keep changes focused and document user-visible behavior in the changelog. Include reproducible inputs and a clear before/after when fixing a calculation.

## Financial changes

- State units, currency, baseline, observation/release dates and price/total-return assumptions.
- Use exact ratio-based real returns and multiplicative compounding. Do not infer monthly inflation from annual rates.
- Preserve source/vintage metadata and synthetic or constructed status through transformations.
- Fail on ambiguous series, unsupported units, invalid overlap and arithmetic problems; do not choose a substitute source silently.
- Add meaningful financial-identity or failure-boundary tests for changed behavior. Include edge cases that can actually distinguish a wrong calculation.
- Check that exported metrics, dashboard labels and Pine semantics agree with the engine's documented contract.

A UI-only reversible change does not need a test that merely repeats its implementation. Choose verification appropriate to the change.

## Providers and fixtures

Use only documented provider interfaces and reference their primary documentation. Include deterministic, clearly synthetic response fixtures. Never commit API keys, account exports, licensed market history or personal portfolio reports. A provider adapter must state whether it supplies current or historical vintages and must not invent release dates.

For historical CPI links, document upstream identities, overlap and scaling. For corporate actions, explain whether source prices already reflect them. Unsupported periods must remain unavailable; use narrower examples instead of filling gaps.

## Review checklist

Describe the problem, resulting behavior and relevant validation in the pull request. Run Python checks for backend changes and web checks for frontend changes. Update the English/Turkish README or methodology when a public contract changes. Keep first-party licensing `0BSD`; retain required upstream notices and do not claim upstream data is covered by the repository license.

## License of contributions

By submitting a contribution for inclusion, you agree that your first-party contribution may be distributed under this repository's [0BSD license](LICENSE). You must have the right to contribute it. No additional attribution condition should be inserted into first-party code. Third-party materials retain their own applicable terms and must be clearly identified.

## Reporting problems

Open an issue with the version, minimal synthetic input, command/request, expected result and actual result. Avoid screenshots as the only evidence for a numerical error; attach a reproducible small table instead. For sensitive security information, follow [SECURITY.md](SECURITY.md).
