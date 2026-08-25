$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$mc = Join-Path $root 'providers\douyin\MediaCrawler'
$checks = @()
function Check($name, $ok, $detail) { $script:checks += [pscustomobject]@{检查=$name; 状态=($(if($ok){'通过'}else{'缺失'})); 说明=$detail} }
Check 'Python 3.10+' ($null -ne (Get-Command py -ErrorAction SilentlyContinue)) '需要 Windows Python Launcher'
Check 'uv' ($null -ne (Get-Command uv -ErrorAction SilentlyContinue)) '用于创建 MediaCrawler 环境'
Check 'MediaCrawler 源码' (Test-Path (Join-Path $mc 'main.py')) $mc
Check 'MediaCrawler 虚拟环境' (Test-Path (Join-Path $mc '.venv\Scripts\python.exe')) '运行 bootstrap.ps1 安装'
Check 'Playwright Chromium' (Test-Path (Join-Path $mc '.venv\Lib\site-packages\playwright')) '运行 bootstrap.ps1 安装'
Check '抖音登录态' (Test-Path (Join-Path $mc 'chrome-cdp-profile')) '首次运行需扫码登录'
Check '知乎密钥' (-not [string]::IsNullOrWhiteSpace($env:ZHIHU_ACCESS_SECRET)) '环境变量 ZHIHU_ACCESS_SECRET'
$checks | Format-Table -AutoSize
if($checks.Status -contains '缺失'){ exit 1 }
