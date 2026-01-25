-- Migration helper: auth/email columns (idempotent).
ALTER TABLE "deposit".institutions 
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
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

