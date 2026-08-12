param(
  [string]$WorkspaceRoot = 'D:\VoiceWorkspace',
  [string]$ProjectName = 'default-project',
  [string]$ProjectRoot = '',
  [string]$CodexHome = '',
  [string]$DashboardShortcutPath = '',
  [string]$Env4BCRoot = '',
  [string]$Env4BCPackage = '',
  [switch]$Offline,
  [switch]$UpdateOnly,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$packageRoot = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $packageRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
& (Join-Path $packageRoot 'scripts\Resolve-Env4BC.ps1') -InstallRoot $Env4BCRoot -LocalPackage $Env4BCPackage -Offline:$Offline
if ($LASTEXITCODE -ne 0) { throw 'env4BC 环境资源钩子失败。' }
if ([string]::IsNullOrWhiteSpace($CodexHome)) {
  $CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
}
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'env4BC 未能提供 Python，已停止，请联系维护人员处理。' }

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

if (-not $UpdateOnly) {
  $creator = Join-Path $skillTarget 'manage-voice-production\scripts\create_voice_project.py'
  $createArgs = @('-3','-B','-X','utf8',$creator,'--workspace-root',$WorkspaceRoot,'--project-name',$ProjectName)
  if ($ProjectRoot) { $createArgs += @('--project-root',$ProjectRoot) }
  & py @createArgs
  if ($LASTEXITCODE -ne 0) { throw "Project initialization failed: $LASTEXITCODE" }
}

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

if ($UpdateOnly) {
  & py -3 -B -X utf8 (Join-Path $packageRoot 'scripts\validate_package.py') --package-root $packageRoot
} else {
  & py -3 -B -X utf8 (Join-Path $packageRoot 'scripts\validate_package.py') --package-root $packageRoot --workspace-root $WorkspaceRoot --project-name $ProjectName --codex-home $CodexHome
}
if ($LASTEXITCODE -ne 0) { throw "Installation validation failed: $LASTEXITCODE" }
Write-Output "Install complete. Workspace: $WorkspaceRoot; project: $ProjectName"
Write-Output "Dashboard program: $dashboardExe"
Write-Output 'Environment owner: env4BC (not modified by this installer)'

$toolStateRoot = Join-Path $WorkspaceRoot '.voice-production-toolkit'
New-Item -ItemType Directory -Force -Path $toolStateRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $packageRoot 'scripts\Update-Toolkit.ps1') -Destination (Join-Path $toolStateRoot 'Update-Toolkit.ps1') -Force
[ordered]@{schema_version=1;repository='https://github.com/zjw051230-jpg/voice-production-toolkit4bingchuan';installed_version=$manifest.version;update_command="powershell -ExecutionPolicy Bypass -File `"$toolStateRoot\Update-Toolkit.ps1`" -WorkspaceRoot `"$WorkspaceRoot`"";managed_scope=@('Codex skills','.codex-dashboard');protected_scope=@('项目注册表.json','项目四大目录','.codex task records','API private configuration');updated_at=(Get-Date).ToString('o')} | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $toolStateRoot 'update-source.json')
attrib +h $toolStateRoot | Out-Null
