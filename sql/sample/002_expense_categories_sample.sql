-- Sample expense categories for all existing users (idempotent).
INSERT INTO expense.expense_categories (user_id, name)
SELECT u.id, c.name
FROM "user".users u
CROSS JOIN (
  VALUES
    ('餐饮'),         -- 餐食、买菜、咖啡、零食
    ('住房'),         -- 房租、房贷、居住相关费用
    ('交通'),         -- 公交地铁、打车、油费、停车
    ('日用品'),         -- 零售消费、日用品
    ('健康'),         -- 医疗、药品、健身
    ('教育'),         -- 课程、书籍、培训
    ('旅行'),         -- 旅途交通、住宿、门票
    ('娱乐'),         -- 电影、游戏、兴趣爱好
    ('水电网'),       -- 水电、网络、电话
    ('礼物')        -- 礼品与捐赠
) AS c(name)
ON CONFLICT DO NOTHING;
