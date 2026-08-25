# 闲鱼 / 抖音违禁词检测 Skill

这是一个可交接的 Agent Skill 仓库。核心目录是 `douyin-content-safety/`。

## 新 Agent 接手清单

仓库链接本身不会自动把 Skill 注册到 Agent。接手后必须先将整个目录复制到该 Agent 的用户级 Skills 目录：

```powershell
# Codex Windows 示例；请把路径替换为实际克隆路径
$repo = "C:\path\to\-skill-"
$dest = "$env:USERPROFILE\.codex\skills\douyin-content-safety"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item "$repo\douyin-content-safety\*" $dest -Recurse -Force
```

然后重启 Agent，或明确告诉它：

> 使用 `douyin-content-safety` Skill 检测下面的闲鱼/抖音文案。

如果 Agent 使用其他 Skills 根目录，应把 `douyin-content-safety` 放到该目录下，而不是只打开 README。

## 闲鱼：无需 token

闲鱼检测使用仓库内置的本地词库，可以直接运行：

```powershell
python douyin-content-safety/scripts/scan_xianyu.py --text "待检测的闲鱼标题和描述"
```

也可以直接把文案交给已注册的 Agent。词库包含商品违禁词、商品版权词、平台盗版违规词三类；“未命中”只代表本地词库未命中，不代表闲鱼官方审核通过。

## 抖音：必须由用户配置官方 token

抖音检测分两层：第三方 MCP 预筛 + 抖音官方 `antidirt` 接口复核。MCP 配置不会随仓库自动注册，需按 [MCP 配置说明](douyin-content-safety/references/mcp.md) 接入；官方接口还必须有用户自己的小程序服务端凭证。

用户需要在抖音开放平台创建/管理小程序，在开发配置中取得 AppID 和 AppSecret，再由开发者服务器换取小程序 `access_token`。不要把 AppSecret 或 token 发给 Agent，也不要提交到 Git。

在运行 Agent 的开发者服务器环境中设置：

```powershell
[Environment]::SetEnvironmentVariable("DOUYIN_ACCESS_TOKEN", "你的 token", "User")
```

重启 Agent 后，官方脚本会从环境变量读取 token：

```powershell
python douyin-content-safety/scripts/check_text.py --text "待检测的抖音文案"
```

## 接手时必须如实说明

- 没有配置 MCP：只能做闲鱼本地词库检测，或报告抖音预筛不可用。
- 没有配置 `DOUYIN_ACCESS_TOKEN`：可以做 MCP 预筛，但不能声称完成抖音官方复核。
- 词库和第三方 MCP 都不是平台最终审核结论，不能承诺一定过审。
- 只允许检测用户明确提供的文本，不提供规避平台审核的黑话、谐音或拆字改写。

详细执行规则见 [douyin-content-safety/SKILL.md](douyin-content-safety/SKILL.md)。
