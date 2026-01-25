DO $$
DECLARE
  dbname text := current_database();
BEGIN
  IF dbname NOT ILIKE '%flow%' THEN
    RAISE EXCEPTION 'Refusing to clear database %', dbname;
  END IF;
END $$;

DO $$
DECLARE
  tbls text;
BEGIN
  SELECT string_agg(format('%I.%I', schemaname, tablename), ', ')
    INTO tbls
  FROM pg_tables
  WHERE schemaname IN ('deposit', 'expense', 'currency', 'user');

  IF tbls IS NULL THEN
    RAISE NOTICE 'No tables found in target schemas.';
    RETURN;
  END IF;

  EXECUTE 'TRUNCATE TABLE ' || tbls || ' RESTART IDENTITY CASCADE';
END $$;
