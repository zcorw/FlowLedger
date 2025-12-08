-- Sample exchange rates for development/testing
-- Loads a few USD-based daily rates for common pairs.
-- Safe to run multiple times (ON CONFLICT DO NOTHING)

-- Ensure required currencies exist (schema seeds already include these, but keep idempotent)
INSERT INTO currency.currencies(code, name, symbol, scale)
VALUES ('USD','US Dollar','$',2)
ON CONFLICT (code) DO NOTHING;

INSERT INTO currency.currencies(code, name, symbol, scale)
VALUES ('CNY','Chinese Yuan','¥',2)
ON CONFLICT (code) DO NOTHING;

INSERT INTO currency.currencies(code, name, symbol, scale)
VALUES ('HKD','Hong Kong Dollar','HK$',2)
ON CONFLICT (code) DO NOTHING;

INSERT INTO currency.currencies(code, name, symbol, scale)
VALUES ('JPY','Japanese Yen','¥',0)
ON CONFLICT (code) DO NOTHING;

-- USD base to CNY/HKD/JPY for two dates to test fallback behavior
INSERT INTO currency.exchange_rates(base_code, quote_code, rate_date, rate, source)
VALUES ('USD','CNY','2025-01-01',7.1000000000,'sample')
ON CONFLICT DO NOTHING;

INSERT INTO currency.exchange_rates(base_code, quote_code, rate_date, rate, source)
VALUES ('USD','CNY','2025-01-15',7.0500000000,'sample')
ON CONFLICT DO NOTHING;

INSERT INTO currency.exchange_rates(base_code, quote_code, rate_date, rate, source)
VALUES ('USD','HKD','2025-01-01',7.8000000000,'sample')
ON CONFLICT DO NOTHING;

INSERT INTO currency.exchange_rates(base_code, quote_code, rate_date, rate, source)
VALUES ('USD','HKD','2025-01-15',7.7900000000,'sample')
ON CONFLICT DO NOTHING;

INSERT INTO currency.exchange_rates(base_code, quote_code, rate_date, rate, source)
VALUES ('USD','JPY','2025-01-01',140.0000000000,'sample')
ON CONFLICT DO NOTHING;

INSERT INTO currency.exchange_rates(base_code, quote_code, rate_date, rate, source)
VALUES ('USD','JPY','2025-01-15',141.5000000000,'sample')
ON CONFLICT DO NOTHING;

