# 用户模块 API 设计说明

## 1. 模块概述与边界
- 职责：用户与偏好、Telegram 绑定
- 依赖：与所有业务资源的 user_id 关联；时区影响调度

## 2. 资源模型
- User：id、telegram_user_id（可空）、is_bot_enabled
- UserPreference：base_currency、timezone、language

## 3. 端点一览
| 路径 | 方法 | 用途 | 鉴权/作用域 | 幂等 | 速率限制 | 备注 |
|---|---|---|---|---|---|---|
| /v1/users | POST | 注册 | write:user | 幂等键 | 严格 | 首次创建 |
| /v1/users/me | GET | 当前用户 | read:user | 是 | 标准 | 需 Bearer |
| /v1/users/me/preferences | PATCH | 更新偏好 | write:user | 幂等键 | 严格 | 时区/货币 |
| /v1/users/link-telegram | POST | 绑定 | write:user | 幂等键 | 严格 | 可带 link_token |

## 4. 字段与验证规则
- timezone：IANA 时区字符串（1-64字）
- base_currency：ISO 4217；language：BCP47，如 zh-CN

## 5. 错误与冲突场景
- 409 重复绑定 telegram_user_id
- 422 偏好字段校验失败

## 6. 示例交互
- POST /v1/users 注册 → 返回 user 与默认偏好
- POST /v1/users/link-telegram 携带 link_token 绑定

## 7. 监控指标
- active_users、link_success_rate、pref_update_latency

## 8. 变更与兼容
- 偏好字段新增保持可选与默认值

