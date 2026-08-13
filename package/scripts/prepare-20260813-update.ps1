[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SourceRoot)
$ErrorActionPreference='Stop'
$source=[IO.Path]::GetFullPath($SourceRoot).TrimEnd('\')
if(-not (Test-Path -LiteralPath $source -PathType Container)){throw "源文件夹不存在：$source"}
$old=$source+'-旧'
if(Test-Path -LiteralPath $old){throw "旧源文件夹已存在，拒绝覆盖：$old"}
$parent=Split-Path -Parent $source; $name=Split-Path -Leaf $source
Rename-Item -LiteralPath $source -NewName ($name+'-旧')
Copy-Item -LiteralPath $old -Destination $source -Recurse
Write-Output "SOURCE_BACKUP:$old"
Write-Output "WORK_COPY:$source"
