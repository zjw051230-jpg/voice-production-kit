param(
  [Parameter(Mandatory = $true)][string]$Path
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
  throw "Directory does not exist: $Path"
}
$item = Get-Item -LiteralPath $Path -Force
$item.Attributes = $item.Attributes -bor [IO.FileAttributes]::Hidden
