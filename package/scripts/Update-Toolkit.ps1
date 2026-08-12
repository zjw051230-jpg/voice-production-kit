[CmdletBinding()]
param([string]$WorkspaceRoot='D:\VoiceWorkspace',[string]$CodexHome='',[string]$DashboardShortcutPath='',[switch]$Offline)
$ErrorActionPreference='Stop'
$repo='zjw051230-jpg/voice-production-toolkit4bingchuan'
if($Offline){throw '离线模式不能访问 GitHub；请提供经校验的正式安装包给维护人员。'}
$temp=Join-Path ([IO.Path]::GetTempPath()) ('voice-production-toolkit-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp|Out-Null
function Save-TrustedDownload([string]$Uri,[string]$Destination){
  if(Get-Command curl.exe -ErrorAction SilentlyContinue){& curl.exe --fail --location --silent --show-error --retry 3 --retry-delay 2 --connect-timeout 20 --max-time 600 --output $Destination $Uri;if($LASTEXITCODE-ne 0 -or -not(Test-Path $Destination)){throw "官方文件下载失败：$Uri"}}
  else{Invoke-WebRequest -Headers @{'User-Agent'='BC-toolkit'} -UseBasicParsing -TimeoutSec 600 -Uri $Uri -OutFile $Destination}
}
try{
  $release=Invoke-RestMethod -Headers @{Accept='application/vnd.github+json';'User-Agent'='BC-toolkit'} -Uri "https://api.github.com/repos/$repo/releases/latest"
  $zipAsset=@($release.assets|Where-Object {$_.name -match '^voice-production-toolkit-v.+\.zip$'})|Select-Object -First 1
  $hashAsset=@($release.assets|Where-Object {$_.name -eq ($zipAsset.name+'.sha256')})|Select-Object -First 1
  if(-not $zipAsset -or -not $hashAsset){throw '官方 Release 缺少 ZIP 或 SHA-256。'}
  $zip=Join-Path $temp $zipAsset.name; $hashFile="$zip.sha256"
  Save-TrustedDownload $zipAsset.browser_download_url $zip
  Save-TrustedDownload $hashAsset.browser_download_url $hashFile
  $line=(Get-Content -Encoding ASCII $hashFile|Select-Object -First 1).Trim()
  if($line -notmatch '^([A-Fa-f0-9]{64})(?:\s+|$)' -or (Get-FileHash $zip -Algorithm SHA256).Hash -ne $Matches[1].ToUpperInvariant()){throw '官方更新包 SHA-256 校验失败。'}
  $extract=Join-Path $temp 'package'; Expand-Archive $zip $extract
  & py -3 -B -X utf8 (Join-Path $extract 'scripts\validate_package.py') --package-root $extract
  if($LASTEXITCODE -ne 0){throw '更新包安全校验失败。'}
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $extract 'install.ps1') -WorkspaceRoot $WorkspaceRoot -CodexHome $CodexHome -DashboardShortcutPath $DashboardShortcutPath -UpdateOnly -Force
  if($LASTEXITCODE -ne 0){throw '工具更新失败；项目资源未作为更新目标。'}
  Write-Output "UPDATED:$($release.tag_name)"
}finally{if(Test-Path $temp){Remove-Item $temp -Recurse -Force}}
