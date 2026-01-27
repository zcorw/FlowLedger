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


