[CmdletBinding()]
param(
  [string]$InstallRoot = '',
  [string]$LocalPackage = '',
  [switch]$Offline
)

$ErrorActionPreference = 'Stop'
$officialRepo = 'zjw051230-jpg/env4BC'
$stateRoot = if ($InstallRoot) { [IO.Path]::GetFullPath($InstallRoot) } else { Join-Path $env:LOCALAPPDATA 'env4BC' }
$statePath = Join-Path $stateRoot 'install-state.json'

function Test-EnvironmentReady {
  if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { return $false }
  try { $state = Get-Content -Raw -Encoding UTF8 -LiteralPath $statePath | ConvertFrom-Json } catch { return $false }
  if ($state.material_directories_touched -and @($state.material_directories_touched).Count -gt 0) { return $false }
  $cc = [string]$state.cc_switch.path
  $api = [string]$state.seedance_api_tool.path
  return (Test-Path -LiteralPath $cc -PathType Leaf) -and (Test-Path -LiteralPath $api -PathType Leaf) -and
    [bool](Get-Command py -ErrorAction SilentlyContinue) -and [bool](Get-Command ffmpeg -ErrorAction SilentlyContinue)
}

function Get-ExpectedHash([string]$HashFile) {
  if (-not (Test-Path -LiteralPath $HashFile -PathType Leaf)) { return $null }
  $line = (Get-Content -LiteralPath $HashFile -Encoding ASCII | Select-Object -First 1).Trim()
  if ($line -match '^([A-Fa-f0-9]{64})(?:\s+|$)') { return $Matches[1].ToUpperInvariant() }
  return $null
}

function Save-TrustedDownload([string]$Uri,[string]$Destination) {
  if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
    & curl.exe --fail --location --silent --show-error --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 600 --output $Destination $Uri
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Destination -PathType Leaf)) { throw "官方文件下载失败：$Uri" }
  } else {
    Invoke-WebRequest -Headers @{'User-Agent'='BC-toolkit'} -UseBasicParsing -TimeoutSec 600 -Uri $Uri -OutFile $Destination
  }
}

function Install-TrustedPackage([string]$ZipPath,[string]$HashPath) {
  $expected = Get-ExpectedHash $HashPath
  if (-not $expected) { throw 'env4BC 安装包缺少有效 SHA-256，拒绝安装。' }
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZipPath).Hash
  if ($actual -ne $expected) { throw 'env4BC SHA-256 校验失败，拒绝安装。' }
  $temp = Join-Path ([IO.Path]::GetTempPath()) ('env4BC-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $temp | Out-Null
  try {
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $temp
    $manifestPath = Join-Path $temp 'manifest.json'
    $installer = Join-Path $temp 'install.ps1'
    if (-not (Test-Path $manifestPath) -or -not (Test-Path $installer)) { throw 'env4BC 包结构无效。' }
    $manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
    if ($manifest.name -ne 'env4BC' -or $manifest.update_policy -ne 'repair-missing-only' -or $manifest.material_policy -ne 'never-touch-user-materials') { throw 'env4BC 安全清单无效。' }
    $forbidden = Get-ChildItem -Recurse -Force -File $temp | Where-Object { $_.Name -match '(?i)cc-switch\.db|credentials\.json|doubao_api_config\.json|providers\.json|\.env$|\.sqlite|\.db-(wal|shm)$' }
    if ($forbidden) { throw 'env4BC 包含用户数据或密钥文件，拒绝安装。' }
    $installArgs=@('-NoProfile','-ExecutionPolicy','Bypass','-File',$installer,'-InstallRoot',$stateRoot)
    if($InstallRoot){$installArgs+=@('-CcSwitchRoot',(Join-Path $stateRoot 'cc-switch'),'-ShortcutRoot',(Join-Path $stateRoot 'shortcuts'))}
    & powershell.exe @installArgs
    if ($LASTEXITCODE -ne 0) { throw 'env4BC 安装失败。' }
  } finally {
    if (Test-Path $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
  }
}

if (Test-EnvironmentReady) { Write-Output 'ENV4BC_READY:installed'; exit 0 }

$candidates = @()
if ($LocalPackage) {
  $candidates += [IO.Path]::GetFullPath($LocalPackage)
} elseif ($env:ENV4BC_PACKAGE) {
  $candidates += [IO.Path]::GetFullPath($env:ENV4BC_PACKAGE)
} else {
  $knownRoot = 'D:\环境工具总结\安装包'
  if (Test-Path $knownRoot) { $candidates += @(Get-ChildItem -LiteralPath $knownRoot -Filter 'env4BC-v*.zip' -File | Sort-Object LastWriteTime -Descending | ForEach-Object FullName) }
}
foreach ($candidate in $candidates | Select-Object -Unique) {
  if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
  $hash = "$candidate.sha256"
  try { Install-TrustedPackage $candidate $hash; if (Test-EnvironmentReady) { Write-Output "ENV4BC_READY:local:$candidate"; exit 0 } } catch { Write-Warning $_.Exception.Message }
}

if (($LocalPackage -or $env:ENV4BC_PACKAGE) -and -not (Test-EnvironmentReady)) {
  throw '显式指定的 env4BC 安装包无法通过安全校验或安装。流程已停止，请联系维护人员处理。'
}

if (-not $Offline) {
  $tempDownload = Join-Path ([IO.Path]::GetTempPath()) ('env4BC-release-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tempDownload | Out-Null
  try {
    $release = Invoke-RestMethod -Headers @{Accept='application/vnd.github+json';'User-Agent'='BC-toolkit'} -Uri "https://api.github.com/repos/$officialRepo/releases/latest"
    $zipAsset = @($release.assets | Where-Object {$_.name -match '^env4BC-v.+\.zip$'}) | Select-Object -First 1
    $hashAsset = @($release.assets | Where-Object {$_.name -eq ($zipAsset.name + '.sha256')}) | Select-Object -First 1
    if (-not $zipAsset -or -not $hashAsset) { throw '官方 Release 缺少 ZIP 或 SHA-256。' }
    $zip = Join-Path $tempDownload $zipAsset.name
    $hash = "$zip.sha256"
    Save-TrustedDownload $zipAsset.browser_download_url $zip
    Save-TrustedDownload $hashAsset.browser_download_url $hash
    Install-TrustedPackage $zip $hash
    if (Test-EnvironmentReady) { Write-Output "ENV4BC_READY:github:$($release.tag_name)"; exit 0 }
  } catch { Write-Warning $_.Exception.Message } finally { if (Test-Path $tempDownload) { Remove-Item $tempDownload -Recurse -Force } }
}

throw '环境资源不足，未找到可验证的 env4BC 或安全安装失败。流程已停止，请联系维护人员处理。'
