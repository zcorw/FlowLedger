-- Migration helper: auth/email columns (idempotent).
ALTER TABLE "expense".expenses 
    ADD COLUMN IF NOT EXISTS file_id BIGINT NULL REFERENCES file.files(id) ON DELETE SET NULL;
ALTER TABLE "user".users
    ADD COLUMN IF NOT EXISTS telegram_login_token TEXT NULL;
-- Ensure unique constraints for username/email.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'up_fin_products__inst_product'
    ) THEN
        ALTER TABLE "deposit".financial_products ADD CONSTRAINT up_fin_products__inst_product UNIQUE (institution_id, name);
    END IF;
END;
$$;
