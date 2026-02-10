-- Reset and seed demo account data (idempotent).
-- Demo credentials: username=demo, password=demo1234, email=demo@example.com

DO $$
DECLARE
  demo_user_id BIGINT;
BEGIN
  SELECT id INTO demo_user_id
  FROM "user".users
  WHERE username = 'demo' OR email = 'demo@example.com'
  LIMIT 1;

  IF demo_user_id IS NOT NULL THEN
    DELETE FROM expense.expenses WHERE user_id = demo_user_id;
    DELETE FROM "user".users WHERE id = demo_user_id;
  END IF;
END $$;

WITH new_user AS (
  INSERT INTO "user".users (
    username,
    email,
    password_salt,
    password_hash,
    email_verified_at,
    is_bot_enabled,
    created_at,
    updated_at
  )
  VALUES (
    'demo',
    'demo@example.com',
    'demo_salt_001',
    'ypgoQlgLYiIvdFUbG+ZPjfEFvVOOSRjkjEYniYCoz7o=',
    now(),
    true,
    now(),
    now()
  )
  RETURNING id
),
insert_pref AS (
  INSERT INTO "user".user_prefs (
    user_id,
    base_currency,
    timezone,
    language,
    created_at,
    updated_at
  )
  SELECT id, 'CNY', 'Asia/Shanghai', 'zh-CN', now(), now()
  FROM new_user
  RETURNING user_id
),
insert_categories AS (
  INSERT INTO expense.expense_categories (user_id, name, tax)
  SELECT user_id, name, tax
  FROM (
    SELECT (SELECT user_id FROM insert_pref) AS user_id, 'Food' AS name, 0.08::numeric AS tax
    UNION ALL SELECT (SELECT user_id FROM insert_pref), 'Transport', 0.10
    UNION ALL SELECT (SELECT user_id FROM insert_pref), 'Shopping', 0.10
    UNION ALL SELECT (SELECT user_id FROM insert_pref), 'Health', 0.05
  ) c
  ON CONFLICT (user_id, name) DO NOTHING
  RETURNING id, name
),
insert_institutions AS (
  INSERT INTO deposit.institutions (user_id, name, type, status)
  SELECT user_id, name, type, status
  FROM (
    SELECT (SELECT user_id FROM insert_pref) AS user_id, 'Bank of Demo' AS name, 'bank' AS type, 'active' AS status
    UNION ALL SELECT (SELECT user_id FROM insert_pref), 'Demo Broker', 'broker', 'active'
  ) i
  ON CONFLICT (user_id, name) DO UPDATE SET status = EXCLUDED.status
  RETURNING id, name
),
insert_products AS (
  INSERT INTO deposit.financial_products (
    institution_id,
    name,
    product_type,
    currency,
    status,
    risk_level,
    amount,
    amount_updated_at,
    created_at,
    updated_at
  )
  SELECT i.id, p.name, p.product_type, p.currency, 'active', p.risk_level, p.amount, now(), now(), now()
  FROM insert_institutions i
  JOIN (
    SELECT 'Bank of Demo' AS inst_name, 'Savings' AS name, 'deposit' AS product_type, 'CNY' AS currency, 'stable' AS risk_level, 120000::numeric AS amount
    UNION ALL SELECT 'Bank of Demo', 'USD Time Deposit', 'deposit', 'USD', 'stable', 15000
    UNION ALL SELECT 'Demo Broker', 'Index Fund', 'investment', 'USD', 'stable', 8000
    UNION ALL SELECT 'Demo Broker', 'Tech ETF', 'securities', 'USD', 'high_risk', 5000
  ) p ON p.inst_name = i.name
  ON CONFLICT (institution_id, name) DO UPDATE
    SET status = EXCLUDED.status,
        amount = EXCLUDED.amount,
        amount_updated_at = EXCLUDED.amount_updated_at,
        updated_at = now()
  RETURNING id, name
),
insert_balances AS (
  INSERT INTO deposit.product_balances (product_id, amount, as_of, created_at, updated_at)
  SELECT p.id, b.amount, b.as_of, now(), now()
  FROM insert_products p
  JOIN (
    SELECT 'Savings' AS name, 120000::numeric AS amount, now()::timestamptz AS as_of
    UNION ALL SELECT 'Savings', 118000, now() - interval '30 days'
    UNION ALL SELECT 'USD Time Deposit', 15000, now()
    UNION ALL SELECT 'USD Time Deposit', 14500, now() - interval '30 days'
    UNION ALL SELECT 'Index Fund', 8000, now()
    UNION ALL SELECT 'Index Fund', 7600, now() - interval '30 days'
    UNION ALL SELECT 'Tech ETF', 5000, now()
    UNION ALL SELECT 'Tech ETF', 4700, now() - interval '30 days'
  ) b ON b.name = p.name
  ON CONFLICT (product_id, as_of) DO UPDATE SET amount = EXCLUDED.amount, updated_at = now()
),
insert_expenses AS (
  INSERT INTO expense.expenses (
    user_id,
    name,
    amount,
    currency,
    category_id,
    merchant,
    occurred_at,
    note
  )
  SELECT (SELECT user_id FROM insert_pref), e.name, e.amount, e.currency, c.id, e.merchant, e.occurred_at, e.note
  FROM (
    SELECT 'Lunch' AS name, 35.50::numeric AS amount, 'CNY' AS currency, 'Food' AS category, 'Cafe 99' AS merchant, now() - interval '1 day' AS occurred_at, 'Demo lunch' AS note
    UNION ALL SELECT 'Taxi', 68.00, 'CNY', 'Transport', 'City Taxi', now() - interval '2 days', 'Airport ride'
    UNION ALL SELECT 'Pharmacy', 120.00, 'CNY', 'Health', 'HealthPlus', now() - interval '3 days', 'Vitamins'
    UNION ALL SELECT 'Online Shopping', 299.90, 'CNY', 'Shopping', 'Demo Mall', now() - interval '5 days', 'Headphones'
  ) e
  JOIN expense.expense_categories c
    ON c.user_id = (SELECT user_id FROM insert_pref) AND c.name = e.category
  RETURNING id
)
SELECT 1;
