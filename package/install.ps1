param(
  [string]$WorkspaceRoot = 'D:\VoiceWorkspace',
  [string]$ProjectName = 'default-project',
  [string]$ProjectRoot = '',
  [string]$CodexHome = '',
  [string]$CcSwitchInstallRoot = '',
  [string]$CcSwitchShortcutPath = '',
  [string]$DashboardShortcutPath = '',
  [string]$ApiToolShortcutPath = '',
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
$manifestPath = Join-Path $packageRoot 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Missing manifest: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

$ccSwitchInstaller = Join-Path $packageRoot 'install-ccswitch.ps1'
if (-not (Test-Path -LiteralPath $ccSwitchInstaller)) { throw "Missing CC Switch installer: $ccSwitchInstaller" }
& $ccSwitchInstaller -Force:$Force -InstallRoot $CcSwitchInstallRoot -ShortcutPath $CcSwitchShortcutPath

if ([string]::IsNullOrWhiteSpace($CodexHome)) {
  if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) { $CodexHome = $env:CODEX_HOME }
  else { $CodexHome = Join-Path $env:USERPROFILE '.codex' }
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  throw 'Windows Python Launcher (py) was not found. Install Python 3.10 or newer first.'
}

$skillTarget = Join-Path $CodexHome 'skills'
New-Item -ItemType Directory -Force -Path $skillTarget | Out-Null
foreach ($skill in $manifest.skills) {
  $source = Join-Path (Join-Path $packageRoot 'skills') $skill
  $target = Join-Path $skillTarget $skill
  if (-not (Test-Path -LiteralPath $source)) { throw "Package is missing skill: $skill" }
  if ((Test-Path -LiteralPath $target) -and -not $Force) {
    throw "Skill already exists: $target. Use -Force after approving replacement."
  }
  if (Test-Path -LiteralPath $target) {
    $backup = "$target.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
    Move-Item -LiteralPath $target -Destination $backup
  }
  Copy-Item -LiteralPath $source -Destination $target -Recurse
}

$creator = Join-Path $skillTarget 'manage-voice-production\scripts\create_voice_project.py'
$createArgs = @('-3', '-B', '-X', 'utf8', $creator, '--workspace-root', $WorkspaceRoot, '--project-name', $ProjectName)
if (-not [string]::IsNullOrWhiteSpace($ProjectRoot)) { $createArgs += @('--project-root', $ProjectRoot) }
& py @createArgs
if ($LASTEXITCODE -ne 0) { throw "Project initialization failed with exit code $LASTEXITCODE" }

$dashboardRoot = Join-Path $WorkspaceRoot '.codex-dashboard'
$dashboardApp = Join-Path $dashboardRoot 'app'
New-Item -ItemType Directory -Force -Path $dashboardApp | Out-Null
$dashboardExeSource = Join-Path $packageRoot 'program\配音任务看板.exe'
if (-not (Test-Path -LiteralPath $dashboardExeSource)) { throw "Missing dashboard program: $dashboardExeSource" }
$dashboardExe = Join-Path $dashboardApp '配音任务看板.exe'
Copy-Item -LiteralPath $dashboardExeSource -Destination $dashboardExe -Force
Copy-Item -LiteralPath (Join-Path $skillTarget 'voice-production-dashboard\scripts\voice_dashboard.py') `
  -Destination (Join-Path $dashboardApp 'voice_dashboard.py') -Force
$dashboardConfig = [ordered]@{
  schema_version = 2
  workspace_root = [IO.Path]::GetFullPath($WorkspaceRoot)
  app_mode = 'desktop-exe'
  copy_mode = 'copy-only-no-overwrite'
  installed_version = $manifest.version
  updated_at = (Get-Date).ToString('o')
}
$dashboardConfig | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $dashboardApp 'dashboard-config.json') -Encoding UTF8
attrib +h $dashboardRoot | Out-Null

$toolsRoot = Join-Path $WorkspaceRoot '.codex-tools'
New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $packageRoot '配置Seedance API.ps1') `
  -Destination (Join-Path $toolsRoot '配置Seedance API.ps1') -Force
$apiToolSource = Join-Path $packageRoot 'program\Seedance API配置工具.exe'
if (-not (Test-Path -LiteralPath $apiToolSource)) { throw "Missing API configuration program: $apiToolSource" }
$apiToolExe = Join-Path $toolsRoot 'Seedance API配置工具.exe'
Copy-Item -LiteralPath $apiToolSource -Destination $apiToolExe -Force
$apiToolConfig = [ordered]@{
  schema_version = 1
  workspace_root = [IO.Path]::GetFullPath($WorkspaceRoot)
  installed_version = $manifest.version
  updated_at = (Get-Date).ToString('o')
}
$apiToolConfig | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $toolsRoot 'api-tool-config.json') -Encoding UTF8
attrib +h $toolsRoot | Out-Null

$registry = Get-Content -LiteralPath (Join-Path $WorkspaceRoot '项目注册表.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$projectRootActual = $registry.projects.$ProjectName.project_root
if ([string]::IsNullOrWhiteSpace($projectRootActual)) { throw "Project registry is missing: $ProjectName" }
$projectApiRoot = Join-Path $projectRootActual 'apis'
Copy-Item -LiteralPath $apiToolExe -Destination (Join-Path $projectApiRoot 'Seedance API配置工具.exe') -Force
Copy-Item -LiteralPath (Join-Path $toolsRoot 'api-tool-config.json') -Destination (Join-Path $projectApiRoot 'api-tool-config.json') -Force

if ([string]::IsNullOrWhiteSpace($DashboardShortcutPath)) {
  $desktop = [Environment]::GetFolderPath('Desktop')
  $shortcutPath = Join-Path $desktop '配音任务看板.lnk'
} else {
  $shortcutPath = [IO.Path]::GetFullPath($DashboardShortcutPath)
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $shortcutPath) | Out-Null
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $dashboardExe
$shortcut.WorkingDirectory = $dashboardApp
$shortcut.Description = '多项目配音任务看板'
$shortcut.Save()

if ([string]::IsNullOrWhiteSpace($ApiToolShortcutPath)) {
  $apiShortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Seedance API配置工具.lnk'
} else {
  $apiShortcutPath = [IO.Path]::GetFullPath($ApiToolShortcutPath)
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $apiShortcutPath) | Out-Null
}
$apiShortcut = $shell.CreateShortcut($apiShortcutPath)
$apiShortcut.TargetPath = $apiToolExe
$apiShortcut.WorkingDirectory = $toolsRoot
$apiShortcut.Description = 'Seedance API 本机配置工具'
$apiShortcut.Save()

& py -3 -B -X utf8 (Join-Path $packageRoot 'scripts\validate_package.py') `
  --package-root $packageRoot --workspace-root $WorkspaceRoot --project-name $ProjectName --codex-home $CodexHome
if ($LASTEXITCODE -ne 0) { throw "Installation validation failed with exit code $LASTEXITCODE" }

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Warning 'ffmpeg was not found. Skills and filesystem are installed, but MP3 extraction requires ffmpeg.'
}
Write-Output "Install complete. Workspace: $WorkspaceRoot; project: $ProjectName; skills: $skillTarget"
Write-Output "Dashboard program: $dashboardExe"
Write-Output "Desktop shortcut: $shortcutPath"
Write-Output "Seedance API configuration program: $apiToolExe"
Write-Output "Project API configuration program: $projectApiRoot\Seedance API配置工具.exe"
Write-Output "Seedance API configuration shortcut: $apiShortcutPath"
if ([string]::IsNullOrWhiteSpace($CcSwitchInstallRoot)) {
  $ccSwitchPath = Join-Path $env:LOCALAPPDATA 'Programs\CC Switch\cc-switch.exe'
} else {
  $ccSwitchPath = Join-Path ([IO.Path]::GetFullPath($CcSwitchInstallRoot)) 'cc-switch.exe'
}
Write-Output "CC Switch: $ccSwitchPath"
Write-Output "Seedance API fallback automation: $toolsRoot\配置Seedance API.ps1"
