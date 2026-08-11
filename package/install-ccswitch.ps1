param(
  [switch]$Force,
  [string]$InstallRoot = '',
  [string]$ShortcutPath = ''
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'program\cc-switch\cc-switch.exe'
if (-not (Test-Path -LiteralPath $source)) {
  throw "安装包缺少 CC Switch 程序：$source"
}

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
  $targetDir = Join-Path $env:LOCALAPPDATA 'Programs\CC Switch'
} else {
  $targetDir = [IO.Path]::GetFullPath($InstallRoot)
}
$target = Join-Path $targetDir 'cc-switch.exe'
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

$copyRequired = $true
if (Test-Path -LiteralPath $target) {
  $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
  $targetHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
  if ($sourceHash -eq $targetHash) {
    $copyRequired = $false
    Write-Output 'CC Switch 3.18.0 内部精确路由版已存在，程序文件无需替换。'
  } elseif (-not $Force) {
    $copyRequired = $false
    Write-Warning ("检测到已有 CC Switch，默认保留：{0}。用户批准后使用 -Force 备份并替换。" -f $target)
  } else {
    $backup = "$target.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss-fff')"
    Copy-Item -LiteralPath $target -Destination $backup
    Write-Output "已备份原 CC Switch：$backup"
  }
}

if ($copyRequired) {
  Copy-Item -LiteralPath $source -Destination $target -Force
  Write-Output "CC Switch 3.18.0 内部精确路由版已部署：$target"
}

if ([string]::IsNullOrWhiteSpace($ShortcutPath)) {
  $desktop = [Environment]::GetFolderPath('Desktop')
  $ShortcutPath = Join-Path $desktop 'CC Switch.lnk'
} else {
  $ShortcutPath = [IO.Path]::GetFullPath($ShortcutPath)
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ShortcutPath) | Out-Null
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $targetDir
$shortcut.Description = 'CC Switch 3.18.0 内部精确路由版'
$shortcut.Save()
Write-Output "CC Switch 快捷方式：$ShortcutPath"
Write-Output '未启动 CC Switch，未创建或修改用户数据库。'
