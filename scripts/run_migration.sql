UPDATE "expense".expense_categories
SET name = '订阅'
WHERE name = '旅行';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class WHERE relname = 'trg_auth_tokens__upd'
    ) THEN
        CREATE TRIGGER trg_auth_tokens__upd
        BEFORE UPDATE ON "user".auth_tokens
        FOR EACH ROW EXECUTE FUNCTION "user".tg_set_updated_at();
    END IF;
END;
$$;
