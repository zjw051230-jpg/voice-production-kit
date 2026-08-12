param(
  [string]$WorkspaceRoot = 'D:\VoiceWorkspace',
  [string]$ProjectName = 'default-project',
  [string]$ProjectRoot = '',
  [string]$CodexHome = '',
  [string]$DashboardShortcutPath = '',
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $packageRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$envState = Join-Path $env:LOCALAPPDATA 'env4BC\install-state.json'
if (-not (Test-Path -LiteralPath $envState)) {
  Write-Warning '未检测到 env4BC。配音业务文件仍可安装，但生成前请先通过 env4BC 配置 CC Switch、Seedance API、Python 和 ffmpeg。'
}
if ([string]::IsNullOrWhiteSpace($CodexHome)) {
  $CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
}
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw '未找到 Python，请通过 env4BC 补齐环境。' }

$skillTarget = Join-Path $CodexHome 'skills'
New-Item -ItemType Directory -Force -Path $skillTarget | Out-Null
foreach ($skill in $manifest.skills) {
  $source = Join-Path (Join-Path $packageRoot 'skills') $skill
  $target = Join-Path $skillTarget $skill
  if (-not (Test-Path -LiteralPath $source)) { throw "Package is missing skill: $skill" }
  if ((Test-Path -LiteralPath $target) -and -not $Force) { throw "Skill already exists: $target. Use -Force only after approving replacement." }
  if (Test-Path -LiteralPath $target) {
    Move-Item -LiteralPath $target -Destination "$target.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
  }
  Copy-Item -LiteralPath $source -Destination $target -Recurse
}

$creator = Join-Path $skillTarget 'manage-voice-production\scripts\create_voice_project.py'
$createArgs = @('-3','-B','-X','utf8',$creator,'--workspace-root',$WorkspaceRoot,'--project-name',$ProjectName)
if ($ProjectRoot) { $createArgs += @('--project-root',$ProjectRoot) }
& py @createArgs
if ($LASTEXITCODE -ne 0) { throw "Project initialization failed: $LASTEXITCODE" }

$dashboardRoot = Join-Path $WorkspaceRoot '.codex-dashboard'
$dashboardApp = Join-Path $dashboardRoot 'app'
New-Item -ItemType Directory -Force -Path $dashboardApp | Out-Null
$dashboardExe = Join-Path $dashboardApp '配音任务看板.exe'
Copy-Item -LiteralPath (Join-Path $packageRoot 'program\配音任务看板.exe') -Destination $dashboardExe -Force
Copy-Item -LiteralPath (Join-Path $skillTarget 'voice-production-dashboard\scripts\voice_dashboard.py') -Destination (Join-Path $dashboardApp 'voice_dashboard.py') -Force
[ordered]@{schema_version=2;workspace_root=[IO.Path]::GetFullPath($WorkspaceRoot);app_mode='desktop-exe';copy_mode='copy-only-no-overwrite';installed_version=$manifest.version;updated_at=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dashboardApp 'dashboard-config.json') -Encoding UTF8
attrib +h $dashboardRoot | Out-Null

if (-not $DashboardShortcutPath) { $DashboardShortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) '配音任务看板.lnk' }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut([IO.Path]::GetFullPath($DashboardShortcutPath))
$shortcut.TargetPath = $dashboardExe
$shortcut.WorkingDirectory = $dashboardApp
$shortcut.Description = '多项目配音任务看板'
$shortcut.Save()

& py -3 -B -X utf8 (Join-Path $packageRoot 'scripts\validate_package.py') --package-root $packageRoot --workspace-root $WorkspaceRoot --project-name $ProjectName --codex-home $CodexHome
if ($LASTEXITCODE -ne 0) { throw "Installation validation failed: $LASTEXITCODE" }
Write-Output "Install complete. Workspace: $WorkspaceRoot; project: $ProjectName"
Write-Output "Dashboard program: $dashboardExe"
Write-Output 'Environment owner: env4BC (not modified by this installer)'
