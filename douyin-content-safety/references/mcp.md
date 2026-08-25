# MCP 预筛配置

推荐安装：

```bash
npx -y chinese-sensitive-words-mcp
```

兼容的 MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "chinese-sensitive-words": {
      "command": "npx",
      "args": ["-y", "chinese-sensitive-words-mcp"]
    }
  }
}
```

主要工具：

- `check_sensitive_words`：检测敏感词、引流词、极限词、谐音和拆字变体。
- `get_word_suggestions`：为命中词提供替换建议。

注意：该项目的免费额度、词库更新频率和平台规则属于第三方项目说明，使用前应以其当前 README 和实际返回为准。文案可能被发送到第三方服务；涉及未公开商业信息时，应先获得用户明确同意，或跳过 MCP、只使用用户自己的官方 API 服务。
