CREATE TABLE IF NOT EXISTS market_ticker_snapshots (
    id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    pair VARCHAR(16) NOT NULL,
    last_price NUMERIC(28, 12) NOT NULL,
    bid NUMERIC(28, 12) NOT NULL,
    ask NUMERIC(28, 12) NOT NULL,
    volume_24h NUMERIC(28, 12) NOT NULL,
    high_24h NUMERIC(28, 12) NOT NULL,
    low_24h NUMERIC(28, 12) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_ticker_snapshots_latest
    ON market_ticker_snapshots (provider, pair, fetched_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS market_data_worker_state (
    provider VARCHAR(32) NOT NULL,
    pair VARCHAR(16) NOT NULL,
    last_attempt_at TIMESTAMPTZ,
    last_successful_update TIMESTAMPTZ,
    last_error VARCHAR(64),
    worker_status VARCHAR(16) NOT NULL DEFAULT 'stopped'
        CHECK (worker_status IN ('running', 'stopped')),
    worker_instance VARCHAR(128),
    heartbeat_at TIMESTAMPTZ,
    PRIMARY KEY (provider, pair)
);
