# 用户管理模块 详细设计

## 假设与澄清点
- Telegram 为主要入口，每个用户唯一绑定一个 Telegram ID。
- 用户偏好包含时区、默认货币、语言。
- 新 Telegram 用户接入策略：
  - 默认创建新用户。
  - 若携带有效一次性绑定令牌（link_token，通常由已有账户从 Web/Admin 或迁移流程发起），则绑定到既有用户而不创建新用户。
  - 同一 Telegram ID 不允许绑定多个账户；账户合并需要人工或受控流程。

### 1. 模块概述
- 职责：身份标识、认证授权、用户偏好管理、Telegram 绑定。
- 依赖：无强依赖；被所有业务模块引用。
- 使用场景：注册/登录、Bot 绑定、更新偏好。

### 2. 功能设计
- 功能清单
  | 编号 | 名称 | 说明 | 优先级 |
  |---|---|---|---|
  | U-01 | 注册与身份 | 用户创建、最小资料集 | 高 |
  | U-02 | Telegram 绑定 | 绑定/解绑、校验唯一性 | 高 |
  | U-03 | 偏好设置 | 默认货币、时区、语言 | 高 |
  | U-04 | 权限与令牌 | API Token 管理（可选） | 中 |
- 核心业务规则
  - 一个 Telegram ID 仅绑定一个用户；解绑需二次确认。
  - 偏好变更后影响报表与调度时区计算。
- 异常与补偿策略
  - 绑定冲突/失效：幂等校验、冷却时间、审计日志。

### 3. 数据逻辑设计（概念层）
- 主要对象
  - User(id, created_at, status)
  - TelegramBinding(user_id, telegram_user_id, linked_at, status)
  - UserPreference(user_id, base_currency, timezone, language)
- 对象关系
  - User 1—1 TelegramBinding，User 1—1 UserPreference
- 跨模块数据流
  - 提供用户上下文给业务模块；时区影响调度计算。

### 4. 模块交互与流程
- Bot 引导注册→验证→（判定是否携带 link_token）→创建或绑定→写入/加载偏好→返回欢迎信息。
- 新用户接入判定：
  - 若深链/启动参数包含有效 link_token→校验签名与有效期→绑定至既有用户→失效该令牌→返回绑定成功。
  - 否则→创建新用户（默认偏好：base_currency、timezone、language）→返回欢迎与初始化指引。
- 绑定流程：Bot 触发→签名校验→生成绑定记录→确认→生效。

### 5. 接口说明（结构级，不含OpenAPI）
- 提供接口
  - get_user(): 查询当前用户信息
  - update_preferences(prefs): 更新默认货币、时区、语言
  - link_telegram(link_token?): 绑定 Telegram；可选 link_token 用于绑定既有账户
  - unlink_telegram(): 解绑 Telegram（需二次确认与风险提示）
- 被调用能力
  - 授权/鉴权中间件，提供 user_context
- 权限控制与访问限制
  - 用户仅可操作自身；绑定相关操作限流与风控。
- 幂等性与速率限制
  - 绑定按 telegram_user_id 幂等；偏好更新按 user_id+updated_at 乐观锁。

### 6. 日志与监控
- 监控指标：active_users、link_success_rate、pref_update_latency
- 关键日志点：user_id、telegram_id、action、result

### 7. 测试与验收标准
- 测试范围：
  - 无 token 首次接入（创建新用户）
  - 携带有效 token 绑定既有用户
  - 重复/过期 token 防重放
  - 解绑再绑定、偏好变更后的时区影响
- 验收标准：
  - Given 首次接入且无 token When 访问 Bot Then 创建新用户并完成欢迎引导
  - Given 有效 link_token When 接入 Then 绑定至既有用户且不创建新用户
- Mock/隔离：模拟 Telegram 回调与深链参数，隔离外部依赖。

### 8. 模块扩展与未来优化方向
- 支持多身份提供方、团队/家庭共享、SAML/OIDC（后续）

