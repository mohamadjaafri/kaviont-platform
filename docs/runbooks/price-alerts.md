# Dynamic price alerts

Kaviont Live supports persistent Kraken price rules backed by PostgreSQL.

## Rule types

- **Price above / below** compares each successfully stored ticker price with an absolute threshold.
- **Price rises / falls by** compares each stored ticker price with the reference price captured when the rule is created.

Percentage rules are anchored to the latest persisted price at creation time. For example, a 3% rise rule created at 65,000 triggers at or above 66,950. A 3% drop rule triggers at or below 63,050.

## Evaluation and lifecycle

The market-data worker evaluates matching active rules after it stores a successful snapshot. With the default configuration this happens every 60 seconds. A rule transitions from active to triggered once, so later snapshots do not create duplicate events. Rules can be paused and resumed while active. Triggered rules are terminal; create a new rule to watch for another crossing. Removed rules are soft-deleted so the trigger history remains available.

The browser reads rules and trigger events from the same FastAPI origin. No exchange requests or alert evaluation run in the browser.

## API

- GET /v1/market/kraken/alerts lists rules that are not deleted.
- POST /v1/market/kraken/alerts creates a rule. JSON fields: pair, condition, and threshold.
- PATCH /v1/market/kraken/alerts/{id} pauses or resumes an active rule using is_active true or false.
- DELETE /v1/market/kraken/alerts/{id} soft-deletes a rule.
- GET /v1/market/kraken/alerts/events?limit=50 returns recent trigger events.

Supported conditions are above, below, percent_up, and percent_down. A percentage drop must be below 100%.

## Storage and upgrades

The initial database bootstrap includes db/init/002_market_price_alerts.sql. The application also creates the same tables with CREATE TABLE IF NOT EXISTS when it first accesses alert functionality. This lazy schema initialization supports existing local PostgreSQL volumes where Docker's docker-entrypoint-initdb.d scripts do not run again.
