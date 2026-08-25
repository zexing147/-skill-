# TikHub Provider 参考

核验日期：2026-08-26。TikHub 端点、参数、响应结构和价格会变化；出现 404、422、字段缺失或明显价格变化时，先查官方 OpenAPI，不要猜测字段。

## 当前核心端点

Base URL：大陆 `https://api.tikhub.dev`；国际 `https://api.tikhub.io`。所有请求使用 `Authorization: Bearer ${TIKHUB_API_KEY}`。

| 目标 | 方法与路径 | 参数 |
|---|---|---|
| 用户资料 | `GET /api/v1/douyin/app/v3/handler_user_profile` | `sec_user_id` |
| 用户作品 | `GET /api/v1/douyin/app/v3/fetch_user_post_videos` | `sec_user_id`, `max_cursor`, `count=20`, `sort_type=0`, `channel=normal` |
| 一级评论 | `GET /api/v1/douyin/app/v3/fetch_video_comments` | `aweme_id`, `cursor`, `count=20` |
| 评论回复 | `GET /api/v1/douyin/app/v3/fetch_video_comment_replies` | `item_id`, `comment_id`, `cursor`, `count=20` |

作品使用返回的 `max_cursor` 与 `has_more`；评论/回复使用 `cursor` 与 `has_more`。若游标未变化则停止，避免重复计费。

官方资料：[Douyin Skill](https://github.com/TikHub/tikhub-plugin/blob/main/skills/douyin/SKILL.md)、[OpenAPI](https://api.tikhub.io/)、[定价说明](https://docs.tikhub.io/4592751m0)、[作品接口](https://docs.tikhub.io/186826223e0)、[评论接口](https://docs.tikhub.io/186826225e0)、[回复接口](https://docs.tikhub.io/186826226e0)。

## 主页链接解析

用户接口需要 `sec_user_id`。标准主页 URL 通常形如 `https://www.douyin.com/user/<sec_user_id>`。对于 `v.douyin.com` 短链，先跟随 HTTP 重定向，再从最终 URL 的 `/user/` 路径或 `sec_uid` 查询参数中解析。

TikHub 官方资料目前没有明确的“主页分享短链 → sec_user_id”专用端点。不要使用 `fetch_one_video_by_share_url` 解析主页；它只适用于作品链接。短链无法解析时，请用户在浏览器打开后复制完整主页 URL，或直接提供 `sec_user_id`。

## 价格与频率

官方定价页当前称大多数接口基础价为每次成功请求 0.001 美元，并有按日请求量计算的阶梯折扣；“大多数”不代表所有端点。脚本中的价格只用于本地预算估算，可用 `--price-per-call` 覆盖。

需要实时核验时，可查询 `/api/v1/tikhub/user/get_endpoint_info`、`/api/v1/tikhub/user/calculate_price` 和 `/api/v1/tikhub/user/get_tiered_discount_info`。这些查询自身也可能计费，调用前同样纳入预算。

TikHub 当前公开上限为 10 QPS。脚本默认串行执行，最多重试 3 次；每次尝试都计入本地请求硬上限。

## 响应变化

脚本总是保存 `raw_json`，并以已知字段做宽松归一化。新增或消失的指标保留为 `NULL`，不要当作 0。若 HTTP 为 200 但业务 `code` 不是 200，按失败处理并保存错误摘要。
