-- Migration helper: auth/email columns (idempotent).
ALTER TABLE "deposit".institutions 
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
-- Ensure unique constraints for username/email.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_institutions__status'
    ) THEN
        ALTER TABLE "deposit".institutions ADD CONSTRAINT ck_institutions__status CHECK (status IN ('active','inactive','closed'));
    END IF;
END;
$$;

