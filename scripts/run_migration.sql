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
