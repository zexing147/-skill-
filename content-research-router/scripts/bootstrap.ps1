param([switch]$SkipBrowser)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$mc = Join-Path $root 'providers\douyin\MediaCrawler'
Write-Host '内容研究路由初始化' -ForegroundColor Cyan
if(-not (Get-Command py -ErrorAction SilentlyContinue)){ throw '未找到 Python。请先安装 Python 3.10+，再重新运行。' }
if(-not (Get-Command uv -ErrorAction SilentlyContinue)){
  Write-Host '安装 uv...'
  py -3 -m pip install uv
}
if(-not (Test-Path (Join-Path $mc 'pyproject.toml'))){ throw "MediaCrawler 源码不完整：$mc" }
Push-Location $mc
try {
  uv sync
  if(-not $SkipBrowser){ uv run playwright install chromium }
} finally { Pop-Location }
Write-Host '初始化完成。下一步：运行 scripts\doctor.ps1 检查环境；首次抖音采集会打开登录浏览器，请扫码一次。' -ForegroundColor Green
