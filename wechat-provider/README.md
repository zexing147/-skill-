# 微信公众号独立 Provider（本地）

这是与抖音、知乎隔离的公众号采集方案。它不读取或修改其它平台的配置、Cookie、数据库或输出目录。

## 选用方案

基于 [ar-gen-tin/wechat-article-downloader](https://github.com/ar-gen-tin/wechat-article-downloader)：Chrome CDP 渲染公众号文章，支持单篇 URL、URL 批量、按公众号名搜索，以及正文 Markdown 和本地图片。该仓库目前为只读归档，使用前应锁定 commit 并在本地验证。

依赖：Google Chrome/Chromium、Bun（也可用 `npx -y bun`）。不需要 TikHub Key，也不调用抖音或知乎 Provider。

## 目标流程

```text
关键词（一个或多个）
  -> 公众号搜索候选
  -> 发布时间 >= 当前日期往前 6 个月
  -> 去重（文章 URL 优先，其次标题+公众号）
  -> 每个关键词保留前 10 篇
  -> 逐篇下载正文/图片
  -> 中文 Excel + Markdown/图片目录
```

`前 10` 默认按搜索结果顺序；如果候选页确实返回可见阅读数，则额外生成“按阅读数降序”工作表。阅读数缺失保持空值，不把未知值伪造成 0。发布时间无法解析的文章默认不进入“近半年”结果，但可保留在 `未判定日期` 工作表供人工复核。

## 建议命令

```powershell
git clone https://github.com/ar-gen-tin/wechat-article-downloader .\vendor\wechat-article-downloader
Set-Location .\vendor\wechat-article-downloader
bun install
bun scripts/main.ts --search "关键词" --max 50 --list
bun scripts/main.ts --search "关键词" --max 10 -o ..\..\output\wechat\关键词
```

候选上限 50 只是本地排序前的样本池；最终每个关键词最多下载 10 篇。多个关键词必须分别建立子目录，避免文章、日志和排序结果串线。

## 统一中文输出字段

Excel 工作簿建议包含：`文章信息`、`按阅读数排序`、`按发布时间排序`、`未判定日期`、`采集记录`。核心字段：

| 原始/来源字段 | 中文字段 |
|---|---|
| title | 标题 |
| account / author | 公众号 |
| author | 作者 |
| publish_time / date | 发布时间 |
| url / source | 原文链接 |
| summary | 摘要 |
| content | 正文 |
| read_count | 阅读数 |
| like_count | 点赞数 |
| wow_count | 在看数 |
| keyword | 搜索关键词 |
| search_rank | 搜索排名 |
| collected_at | 采集时间 |

正文和图片同时保存为 Markdown/本地资源；Excel 的正文列保留纯文本或 Markdown 路径，避免单元格超长导致损坏。无值留空；数值字段只有在源明确返回 0 时才写 0。本 Provider 不抓文章评论；评论相关字段不生成、不推断。

## 限制与隔离

- 任意公众号的真实阅读数通常不是稳定公开字段；不能承诺按全网真实阅读数排序。
- 搜索依赖公开搜索页面/登录态，结果受索引、地区、验证码和页面变化影响。
- 删除、隐藏、需要权限的文章无法保证下载。
- 逐篇下载比只列搜索结果更容易触发限制，应保持低并发、低频；失败文章记录原因并继续，不影响抖音/知乎任务。
- 自有公众号全量历史文章可另用官方 API（`WECHAT_APP_ID`/`WECHAT_APP_SECRET`），不得与公开搜索模式混用凭据。

## Provider 边界

输入：`keywords[]`、`months=6`、`per_keyword=10`、`candidate_limit=50`。

输出：只写 `output/wechat/<run-id>/`；不写 `output/douyin`、`output/zhihu`，不复用其它平台 SQLite。付费 Provider（TikHub）对本 Provider 不可见。
