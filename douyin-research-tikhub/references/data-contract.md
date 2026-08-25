# DataProvider 与 SQLite 数据契约

第一版只实现 TikHub。采集编排依赖下列稳定概念，而不直接依赖 TikHub 的原始字段：

```text
resolve_account(input) -> sec_user_id
get_account(sec_user_id) -> Account
list_videos(sec_user_id, cursor, limit) -> Page[Video]
list_comments(video_id, cursor, limit) -> Page[Comment]
list_replies(video_id, comment_id, cursor, limit) -> Page[Comment]
```

`Page` 必须包含 `items`、`next_cursor`、`has_more` 和原始响应。将来接入 `douyin-mcp` 时新增 Provider，保持采集编排和数据库 schema 不变。

## 表与不变量

- `accounts`：账号当前快照及原始 JSON，以 `(provider, sec_user_id)` 去重。
- `videos`：作品稳定信息及原始 JSON，以 `(provider, platform_video_id)` 去重。
- `video_metrics`：每次采集的播放、点赞、评论、收藏、分享快照，不覆盖历史。
- `comments`：一级评论与回复，以 `(provider, platform_comment_id)` 去重；回复用 `parent_comment_id` 关联平台评论 ID。
- `crawl_jobs`：请求范围、预算、状态和停止原因。
- `api_usage`：每次 HTTP 尝试；不得包含 Authorization 头或 API Key。

指标缺失存 `NULL`，平台明确返回 0 时才存 0。时间统一存 UTC ISO 8601。

## 运行状态

- `completed`：达到用户范围或数据源已正常结束。
- `partial`：预算耗尽、部分账号失败或游标异常。
- `failed`：没有取得可用数据，或认证/配置导致整体失败。

`manifest.json` 中的 `estimated_cost_usd` 只是预算估算；`reported_billed_cost_usd` 只有供应商明确返回账单数据时才填写，否则必须是 `null`。
