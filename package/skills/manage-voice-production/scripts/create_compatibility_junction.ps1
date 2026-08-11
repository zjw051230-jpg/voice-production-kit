param(
  [Parameter(Mandatory = $true)][string]$LinkPath,
  [Parameter(Mandatory = $true)][string]$TargetPath
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $TargetPath -PathType Container)) {
  throw "Compatibility target does not exist: $TargetPath"
}
if (Test-Path -LiteralPath $LinkPath) {
  $existing = Get-Item -LiteralPath $LinkPath -Force
  if (-not ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "Compatibility path already exists and is not a junction: $LinkPath"
  }
  exit 0
}
New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath | Out-Null
$item = Get-Item -LiteralPath $LinkPath -Force
$item.Attributes = $item.Attributes -bor [IO.FileAttributes]::Hidden
