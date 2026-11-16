# ADR 0006: historical market-data API on PostgreSQL

- Status: accepted
- Date: 2026-11-16

## Context

v0.8 separated ingestion from the API and stores every successful Kraken ticker snapshot in PostgreSQL. The database now contains a time series, but clients can only read the latest snapshot and worker status.

## Decision

Expose three read-only API capabilities:

- A latest-snapshot overview across all pairs stored in the database.
- A historical time-series endpoint with fixed 1h, 24h, and 7d windows.
- A market summary with first/latest price, absolute and percentage movement, high, low, average, sample count, and observation timestamps.

The history endpoint returns chronological points and accepts a limit between 2 and 2,000. PostgreSQL uses window bucketing to return representative points across the requested time range while retaining the first and most recent observations. The API includes the number of source observations and a downsampled flag.

The summary compares the first and latest observations actually stored inside the selected window. It does not imply the existence of an exact candle open at the beginning of the range. An empty range returns zero samples and null statistics.

## Consequences

- Clients can chart recent market movement and render summary cards without querying Kraken directly.
- The API reuses the PostgreSQL storage already required by the worker.
- Fixed ranges and bounded limits constrain query and response costs.
- Downsampling keeps long-window responses manageable without adding TimescaleDB, Redis, or a message broker.
- Historical API responses represent the worker's polling observations, not official exchange OHLC candles.
- The data volume grows with ingestion frequency and tracked pairs; retention and aggregation can be introduced when operational evidence justifies them.

## Alternatives considered

- Fetch history from Kraken on every API request: rejected because it couples user traffic to the provider and bypasses the persisted dataset.
- Introduce a time-series database immediately: deferred because the current polling volume and query requirements fit PostgreSQL.
- Return every raw observation for every range: rejected because response size would grow with the retention window and polling frequency.
