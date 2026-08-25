---
name: content-research-router
description: 统一路由抖音、微信公众号和知乎采集，平台独立运行、失败隔离，输出统一中文字段与排序工作簿。
---

# 内容研究路由

三个 Provider 使用独立凭据、配置、缓存和输出目录；一个平台失败不得自动切换或污染另一个平台。

默认路由：抖音使用本地 MediaCrawler；公众号使用本地文章下载器；知乎使用官方开放 API。TikHub 是冻结的付费备用源，只有用户明确要求并传入启用标志才可调用。

统一规则：字段名中文化；缺失值留空，只有源明确返回 0 才写 0；按平台和关键词分别排序；每个平台先生成独立原始文件，再生成各自汇总工作簿。当前不做跨平台混合表，避免字段语义串线。

默认阈值：近 6 个月；每个关键词候选最多 50 条，最终最多 10 条；抖音账号最多 10 条作品、每条最多 20 条一级评论；公众号和知乎不抓评论；任何平台都不抓二级评论。

目录结构：

- `content-research-router/SKILL.md`：总路由
- `content-research-router/providers/douyin/`：抖音 Provider、脚本与参考资料
- `content-research-router/providers/wechat/`：公众号 Provider、下载器与汇总脚本
- `content-research-router/providers/zhihu/`：知乎 Provider 与说明

当前状态：三个 Provider 分开调用，路由文档已统一边界；尚未提供一个跨平台总启动脚本。不要用一个平台的命令替代另一个平台的 Provider。
