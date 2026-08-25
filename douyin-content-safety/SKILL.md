---
name: douyin-content-safety
description: 检测抖音或闲鱼短视频、图文、商品标题和直播文案的违规风险；抖音走 MCP 预筛与官方 antidirt 复核，闲鱼使用本地 RAG 词库预筛。
metadata:
  short-description: 抖音文案内容安全检测
---

# 抖音内容安全检测

按平台路由：抖音先用 `chinese-sensitive-words-mcp` 做词库预筛，再用抖音官方文本内容安全接口复核；闲鱼使用本地 RAG 词库进行商品违禁、版权和盗版违规预筛。形成发布前风险筛查。

## 新环境接手

仓库克隆后不会自动注册本 Skill。新 Agent 必须将 `douyin-content-safety/` 整个目录复制到自己的用户级 Skills 目录并重启；闲鱼流程无需凭证即可运行，抖音官方复核需要用户在开发者服务器配置 `DOUYIN_ACCESS_TOKEN`。完整接手步骤见仓库根目录 [README.md](../README.md)。

## 必须遵守

- 仅检测用户明确提供的文本，不擅自改写或规避平台审核。
- 请求在开发者服务器端执行，使用 `X-Token: <access_token>`；绝不把 token 写入文件、代码、日志或最终回复。
- Body 必须是 `application/json`，格式为 `{ "tasks": [{ "content": "..." }] }`。
- 默认线上地址为 `https://developer.toutiao.com/api/v2/tags/text/antidirt`；用户明确测试沙盒时才使用沙盒地址。
- `hit=true` 表示命中违法违规内容；`prob` 仅供参考，不代表平台确定结论。
- 只能称为“接口检测结果”或“发布前风险筛查”，不能承诺一定过审。
- MCP 词库结果不是抖音官方结论；词库命中或未命中都不能替代官方接口复核。
- 闲鱼词库来自用户提供的本地文件，见 [references/xianyu-wordlists.md](references/xianyu-wordlists.md)；它是经验词库，不代表闲鱼完整或最新官方规则。

## 执行方式

1. 先判断平台。用户说抖音时走下方“抖音流程”；用户说闲鱼、商品、上架或商品标题时走“闲鱼流程”。
2. 抖音流程：调用 MCP 工具 `check_sensitive_words`，平台参数选择抖音（若工具支持）；记录命中词、类别、风险等级、变体和替换建议。
3. 若缺少 access token，说明需要用户在开发者服务器环境提供 `DOUYIN_ACCESS_TOKEN`，不要索取或重复输出 token 本身；此时可以只报告 MCP 预筛，明确官方复核未执行。
4. 使用 `scripts/check_text.py` 发送官方请求；脚本从环境变量读取 token。
5. 汇总每个 task 的 `code`、`msg`、`task_id`、命中的 `model_name`/`target`，并指出 `log_id` 供排查。
6. `code=0` 且所有 `hit=false` 时报告“官方接口本次未命中”；任意 `hit=true` 时报告“官方接口检测命中，建议暂停发布并人工复核”。
7. MCP 命中但官方未命中，或官方命中但 MCP 未命中，都要标记“结果不一致，需人工复核”，不要自行裁决。
8. `code=400` 是参数有误，`code=401` 是 token 校验失败；网络或接口异常不能当作通过。

### 闲鱼流程

1. 使用 `scripts/scan_xianyu.py` 读取 [references/xianyu-wordlists.md](references/xianyu-wordlists.md)，按“商品违禁词”“商品版权词”“平台盗版违规词”三类匹配用户提供的标题、描述和评论文案；不要用单字词做裸子串匹配，以免把“操”误报为“操作”。
2. 输出命中词、所属词库、原文位置和风险解释；版权/盗版类优先标为高风险，商品违禁类标为高风险或需人工复核。
3. 词库未命中只能表示“本地词库未命中”，不能表示闲鱼官方审核通过；涉及会员、账号、课程、影视、软件、资料、版权内容时，即使未命中也要提示人工确认授权和交易合规性。
4. 不提供绕过闲鱼检测的谐音、拆字或黑话改写；只提供合规、真实的商品描述建议。

## 调用示例

```powershell
$env:DOUYIN_ACCESS_TOKEN = "在当前终端临时设置"
python scripts/check_text.py --text "待检测文案"
```

不要在回复中展示真实 token。字段说明见 [references/api.md](references/api.md)。
MCP 配置与隐私边界见 [references/mcp.md](references/mcp.md)。
