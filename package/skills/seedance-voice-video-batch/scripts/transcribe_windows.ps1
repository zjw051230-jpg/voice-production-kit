param(
    [Parameter(Mandatory = $true)]
    [string]$InputWav,
    [string]$TargetText = ''
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Speech

$recognizer = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() |
    Where-Object { $_.Culture.Name -eq 'zh-CN' } |
    Select-Object -First 1
if (-not $recognizer) {
    throw 'Windows zh-CN speech recognizer is not installed.'
}

$engine = [System.Speech.Recognition.SpeechRecognitionEngine]::new($recognizer)
try {
    if ($TargetText) {
        $builder = [System.Speech.Recognition.GrammarBuilder]::new()
        $builder.Culture = $recognizer.Culture
        $builder.Append($TargetText)
        $engine.LoadGrammar([System.Speech.Recognition.Grammar]::new($builder))
    }
    else {
        $engine.LoadGrammar([System.Speech.Recognition.DictationGrammar]::new())
    }
    $engine.SetInputToWaveFile($InputWav)
    $results = @()
    while ($true) {
        try {
            $result = $engine.Recognize()
        }
        catch [System.InvalidOperationException] {
            break
        }
        if ($null -eq $result) { break }
        $words = @($result.Words | ForEach-Object {
            [ordered]@{
                text = $_.Text
                start = $_.AudioPosition.TotalSeconds
                end = ($_.AudioPosition + $_.AudioDuration).TotalSeconds
                confidence = $_.Confidence
            }
        })
        $results += [ordered]@{
            text = $result.Text
            confidence = $result.Confidence
            start = $result.Audio.AudioPosition.TotalSeconds
            end = ($result.Audio.AudioPosition + $result.Audio.Duration).TotalSeconds
            words = $words
        }
    }
    [ordered]@{ results = $results } | ConvertTo-Json -Depth 6 -Compress
}
finally {
    $engine.Dispose()
}
