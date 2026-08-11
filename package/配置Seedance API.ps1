param(
  [string]$ProjectRoot = '',
  [string]$CcSwitchDb = '',
  [ValidateSet('', 'test', 'production')]
  [string]$ApiEnvironment = ''
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding
$guiCandidates = @(
  (Join-Path $PSScriptRoot 'Seedance API配置工具.exe'),
  (Join-Path $PSScriptRoot 'program\Seedance API配置工具.exe')
) | Where-Object { Test-Path -LiteralPath $_ }
$gui = $guiCandidates | Select-Object -First 1
if ($gui -and [string]::IsNullOrWhiteSpace($ProjectRoot) -and [string]::IsNullOrWhiteSpace($CcSwitchDb) -and [string]::IsNullOrWhiteSpace($ApiEnvironment)) {
  Start-Process -FilePath $gui -WorkingDirectory (Split-Path -Parent $gui)
  Write-Output "已启动 Seedance API 配置工具：$gui"
  exit 0
}
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
  $ProjectRoot = Read-Host '请输入配音项目根目录绝对路径'
}
if ([string]::IsNullOrWhiteSpace($ApiEnvironment)) {
  Write-Output '请选择 Seedance API 线路：'
  Write-Output '1. test版（https://chat-test.q1.com/v1）'
  Write-Output '2. 正式版（https://chat.q1.com/v1）'
  $choice = Read-Host '输入 1 或 2'
  if ($choice -eq '1') { $ApiEnvironment = 'test' }
  elseif ($choice -eq '2') { $ApiEnvironment = 'production' }
  else { throw '只能输入 1 或 2' }
}
$candidates = @(
  (Join-Path $PSScriptRoot 'skills\seedance-voice-video-batch\scripts\manage_api_pool.py'),
  $(if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills\seedance-voice-video-batch\scripts\manage_api_pool.py' }),
  (Join-Path $env:USERPROFILE '.codex\skills\seedance-voice-video-batch\scripts\manage_api_pool.py')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$script = $candidates | Select-Object -First 1
if (-not $script) { throw '缺少 manage_api_pool.py；请先安装 v2.0 skills。' }
$arguments = @(
  '-3', '-X', 'utf8', $script, '--project-root', $ProjectRoot,
  'import', '--environment', $ApiEnvironment
)
if (-not [string]::IsNullOrWhiteSpace($CcSwitchDb)) {
  $arguments += @('--ccswitch-db', $CcSwitchDb)
}
& py @arguments
if ($LASTEXITCODE -ne 0) { throw "API 自动配置失败，退出码：$LASTEXITCODE" }
Write-Output 'API 已分类整理，当前配置已写入项目 apis\doubao_api_config.json。'
