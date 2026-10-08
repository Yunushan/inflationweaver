# Security policy

## Supported scope

Security fixes target the current **0.1.x** source line. This repository is a local analytics tool and starter integration service, not an authenticated broker or a financial custody system.

## Reporting a vulnerability

If the hosting platform provides private vulnerability reporting, use that facility. Otherwise contact the maintainer through a private contact explicitly published on the repository host. This initial repository does not invent a security email address or service-level response promise.

Do not publish API keys, licensed/customer datasets, account exports or exploitable details in a public issue. A public issue may request a private contact without disclosing the vulnerability. Include affected version, minimal reproduction, impact and a proposed fix when possible. Ordinary numerical correctness issues without sensitive content can use the issue tracker.

## Credentials and provider requests

Keep `FRED_API_KEY` and `EVDS_API_KEY` in the backend environment or repository-host secret store. Never put them in committed files, notebooks, browser bundles or `NEXT_PUBLIC_*` variables. The included `.env.example` contains empty placeholders; configuration is not loaded automatically simply because a file exists.

Provider errors avoid printing credential-bearing request URLs. Adapters use bounded HTTP timeouts and reject redirects before forwarding credentials. Provider endpoints and contracts must be reviewed when APIs change. Do not weaken that boundary to make a broken integration appear healthy.

## Shared deployment

The local service has no built-in account authentication. Before sharing it beyond trusted local use, configure an authentication/authorization proxy, TLS, request/body/rate limits, explicit CORS origins, limited process privileges, controlled filesystem access, and per-user data isolation as required. Avoid exposing the development server as a production service.

Keep licensed imported series and personal analysis outside the public source tree. Restrict store/report filesystem permissions. Back up persistent source and metadata together. Review DuckDB/Parquet write concurrency before using multiple workers or scheduled writers against one store.

## Data integrity

Checksums detect modification but cannot authenticate an arbitrary publisher. Review provider identity, exact series, units, release dates, vintages, transformations and rights. Constructed hybrids and synthetic examples must retain their labels in stored data and exported reports. Do not use unknown-vintage retrospective CPI as a historical trading signal.

Large uploads and long series can consume CPU/memory. Deployment operators must enforce appropriate limits; a client-side file-size check alone is insufficient. Maintain dependencies and run the repository's checks after upgrading them.
