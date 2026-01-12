-- Migration helper: auth/email columns (idempotent).
ALTER TABLE "user".users 
    ADD COLUMN IF NOT EXISTS username TEXT NULL,
    ADD COLUMN IF NOT EXISTS email TEXT NULL,
    ADD COLUMN IF NOT EXISTS password_hash TEXT NULL,
    ADD COLUMN IF NOT EXISTS password_salt TEXT NULL,
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS email_verification_token TEXT NULL,
    ADD COLUMN IF NOT EXISTS email_verification_expires_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ NULL;

-- Ensure unique constraints for username/email.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_users__username'
    ) THEN
        ALTER TABLE "user".users ADD CONSTRAINT uq_users__username UNIQUE (username);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_users__email'
    ) THEN
        ALTER TABLE "user".users ADD CONSTRAINT uq_users__email UNIQUE (email);
    END IF;
END;
$$;

-- Add amount_updated_at to financial_products for tracking latest amount change time.
ALTER TABLE deposit.financial_products
    ADD COLUMN IF NOT EXISTS amount_updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Ensure trigger function also maintains amount_updated_at when syncing balances.
CREATE OR REPLACE FUNCTION deposit.tg_sync_product_amount()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  latest_ts TIMESTAMPTZ;
BEGIN
  SELECT max(as_of) INTO latest_ts
  FROM deposit.product_balances
  WHERE product_id = NEW.product_id;

  IF latest_ts IS NOT NULL AND NEW.as_of = latest_ts THEN
    UPDATE deposit.financial_products
    SET amount = NEW.amount, amount_updated_at = NEW.as_of, updated_at = now()
    WHERE id = NEW.product_id;
  END IF;
  RETURN NEW;
END $$;
