-- Migration helper: auth/email columns (idempotent).
ALTER TABLE "expense".expenses 
    ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT '';
ALTER TABLE "expense".expense_categories
    ADD COLUMN IF NOT EXISTS tax NUMERIC(7,6) NOT NULL DEFAULT 0.0;
-- Backfill tax for existing categories (idempotent).
UPDATE "expense".expense_categories AS ec
SET tax = v.tax
FROM (
    VALUES
        ('餐饮', 0.08),
        ('住房', 0.1),
        ('交通', 0.1),
        ('日用品', 0.1),
        ('健康', 0.1),
        ('教育', 0.1),
        ('旅行', 0.1),
        ('娱乐', 0.1),
        ('水电网', 0.1),
        ('礼物', 0.1)
) AS v(name, tax)
WHERE ec.name = v.name
  AND ec.tax <> v.tax;
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
