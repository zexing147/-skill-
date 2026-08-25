# 知乎研究 Provider

这是独立的知乎线路，不依赖抖音 MediaCrawler/TikHub 或公众号下载器。默认只调用知乎官方开放平台的搜索接口；失败时只返回知乎错误，不自动切换其它平台。

## 配置

在 Windows 用户环境变量中设置：

```text
ZHIHU_ACCESS_SECRET=你的 Access Secret
```

不要把 Secret 写入脚本、日志、Excel 或聊天。每次请求使用 `Authorization: Bearer ...` 和秒级 `X-Request-Timestamp`。

## 调用

```powershell
py -3.11 知乎研究\zhihu_provider.py --query "人工智能" --months 6 --top 10 --output-dir 知乎输出
```

可传多个关键词，分别生成结果：

```powershell
py -3.11 知乎研究\zhihu_provider.py --query "人工智能" "个人成长" --months 6 --top 10 --output-dir 知乎输出
```

接口单次返回条数按官方范围限制为 1–10；脚本会在本地按发布时间过滤最近半年、去重，并按 `ranking_score` 从高到低排序后取前 10。官方搜索返回只有搜索结果，不保证提供阅读量/点赞/收藏，所以这些字段缺失时留空，不伪造为 0。

## 统一字段

输出 `知乎搜索.xlsx` 与 `知乎搜索.csv`，字段为：平台、关键词、标题、内容类型、摘要、作者、作者主页、文章/回答链接、发布时间、排序分数、阅读量、点赞数、收藏数、评论数、抓取时间。Excel 按关键词分工作表，每个关键词独立按排序分数从高到低取前 10；本 Provider 明确不抓评论，表中的评论数仅在官方搜索结果返回时记录。接口未返回的指标为空。

官方文档：<https://developer.zhihu.com/> 。当前官方平台处于邀测阶段，权限和计费需以账户实际状态为准。
