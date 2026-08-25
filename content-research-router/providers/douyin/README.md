---
name: douyin-research-tikhub
description: 通过本地 MediaCrawler 采集公开抖音账号资料、作品指标和受限的一级评论；TikHub 仅作为经用户明确授权的付费备用源。适用于账号研究、竞品研究及内容分析；不用于发布、私信、登录绕过或采集非公开数据。
---

# 抖音账号研究（TikHub）

默认使用本地 MediaCrawler，完成“账号 → 作品 → 指标 → 一级评论 → 中文 Excel”。TikHub 是冻结的付费 Provider，只有用户明确指定 `--provider tikhub --enable-paid-provider` 才允许请求。

## 前置条件

- Python 3.10+；脚本仅使用标准库。
- 从环境变量 `TIKHUB_API_KEY` 读取密钥。不得把密钥写入文件、命令参数、日志或数据库。
- 中国大陆默认使用 `https://api.tikhub.dev`；其他地区可用 `https://api.tikhub.io`。
- 只采集公开可访问的数据，遵守平台规则、适用法律和合理频率限制。

## 执行流程

1. 收集账号主页链接或 `sec_user_id`、每个账号作品上限和输出目录。基础模式默认单账号最多 20 条作品，评论为 0。
2. 先运行 `estimate`，展示账号数、作品页、评论页、回复页、总请求上限和费用估算。说明费用只是估算，不等于实际账单。
3. 任何付费请求前必须获得用户确认，并把确认的请求上限传给 `--max-api-calls`。没有确认时只允许 dry-run。
4. 先完成账号和作品阶段。用户只说“研究账号”时，到此停止。
5. 用户明确要求评论时，基于实际保存的视频数量重新估算并二次确认。回复需要再次明确范围；不要把“抓评论”自动扩大成“抓全部回复”。
   - `creator`：主页链接或 `sec_user_id`，采集一个账号的多条作品。
   - `detail`：具体视频链接或 `aweme_id`，只采集一条作品详情。
   两种模式统一映射为中文字段后导出 Excel。
6. 执行采集并验证 SQLite、CSV 和 `manifest.json`。汇报实际请求数、成功/失败账号、保存记录数和停止原因。
7. 采集完成后自动生成 `抖音账号研究.xlsx`，将账号、作品、作品指标、评论和调用记录整合到不同工作表，并把常见字段名翻译成中文。

## 默认阈值

- 基础模式：1 个账号、最多 20 条作品、评论关闭、并发 1、低频请求。
- 默认分析模式：1 个账号、最多 10 条作品、每条最多 20 条一级评论、不抓二级回复；评论仅限抖音。
- 不提供深度模式；不自动抓全部评论或回复。
- 账号作品不做阈值筛选；保留最近 20 条，并在中文 Excel 中分别生成“按播放量排序”和“按收藏量排序”工作表（字段缺失时保留原始表并注明不可排序）。

## 命令

在本 Skill 目录运行：

```powershell
# 只估算，不调用 TikHub
python scripts/collect.py estimate --account "<主页链接或sec_user_id>" --videos 100

# TikHub 付费线路（默认冻结；只有用户明确授权时才可使用）
python scripts/collect.py collect --provider tikhub --enable-paid-provider --account "<主页链接或sec_user_id>" --videos 20 --max-api-calls 6 --max-estimated-cost-usd 0.01 --output-dir output

# 基于已有数据库估算评论，不重复抓账号和作品
python scripts/collect.py estimate-comments --output-dir output --max-videos 100 --comments 40

# 已明确确认评论范围后再抓；默认从断点继续
python scripts/collect.py collect-comments --output-dir output --max-videos 100 --comments 40 --max-api-calls 200 --max-estimated-cost-usd 0.25

# MediaCrawler 单账号备用模式
python scripts/mediacrawler_collect.py creator --account "<主页链接>" --videos 10 --comments --output-dir output
python scripts/mediacrawler_collect.py detail --video "<视频链接>" --comments --output-dir output
```

多个账号可重复使用 `--account`，或用 `--accounts-file` 传入每行一个链接/ID的 UTF-8 文本。先运行 `python scripts/collect.py --help` 查看完整参数。

## 预算与停止规则

- `--max-api-calls` 是强制硬上限；重试也占请求预算。下一次请求会越界时，保存当前数据并停止。
- `--max-estimated-cost-usd` 是按当前单价假设计算的金额护栏；实际计费仍以 TikHub 为准。
- 评论从已有 SQLite 的作品开始，不重复购买账号和作品请求；完成的评论页有断点。只有用户明确要求刷新时才使用 `--refresh`。
- 断点在每页处理完成后保存；若进程恰好在“API 已返回、断点尚未提交”的窗口崩溃，恢复时最多可能重复请求最后一页。
- 作品页固定最多 20 条。评论和回复保持 TikHub App-V3 官方默认的每页 20 条。
- 未取得可信的端点实时价格时，只提供带日期和假设的估算，不声称是实付金额。
- 遇到分页游标不前进、连续空页或 API 结构变化时停止对应资源，保存错误摘要并报告，不无限重试；成功数据始终保留原始 JSON。
- 私密、已删除或接口不可得的数据记为不可得；不得把缺失指标写成 0。

## 数据与验证

默认输出：

```text
output/
├─ douyin-research.sqlite
├─ accounts.csv
├─ videos.csv
├─ video-metrics.csv
├─ comments.csv
├─ api-usage.csv
├─ manifest.json
├─ 抖音账号研究.xlsx       # 中文整合版 Excel
└─ manifests/             # 每次运行的历史清单
```

完成前检查：数据库可打开、主键无重复、记录数与 CSV 一致、每条视频指标保存为时间快照、`manifest.json` 区分 `completed`、`partial` 与 `failed`。实际账单无法从响应确认时写 `null`，不要用估算值代替。

## 按需读取

- 调用接口或排查分页/字段变化时，阅读 [references/tikhub-provider.md](references/tikhub-provider.md)。
- 修改数据库或接入第二数据源时，阅读 [references/data-contract.md](references/data-contract.md)。
