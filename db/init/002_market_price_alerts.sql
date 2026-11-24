CREATE TABLE IF NOT EXISTS market_price_alerts (
    id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL DEFAULT 'kraken',
    pair VARCHAR(16) NOT NULL,
    condition VARCHAR(24) NOT NULL
        CHECK (condition IN ('above', 'below', 'percent_up', 'percent_down')),
    threshold NUMERIC(28, 12) NOT NULL CHECK (threshold > 0),
    reference_price NUMERIC(28, 12) NOT NULL CHECK (reference_price > 0),
    status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'triggered', 'deleted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_evaluated_at TIMESTAMPTZ,
    triggered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_market_price_alerts_active
    ON market_price_alerts (provider, pair, status, created_at DESC);

CREATE TABLE IF NOT EXISTS market_price_alert_events (
    id BIGSERIAL PRIMARY KEY,
    alert_id BIGINT REFERENCES market_price_alerts(id) ON DELETE SET NULL,
    provider VARCHAR(32) NOT NULL,
    pair VARCHAR(16) NOT NULL,
    condition VARCHAR(24) NOT NULL,
    threshold NUMERIC(28, 12) NOT NULL,
    reference_price NUMERIC(28, 12) NOT NULL,
    observed_price NUMERIC(28, 12) NOT NULL,
    triggered_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_market_price_alert_events_recent
    ON market_price_alert_events (triggered_at DESC, id DESC);
