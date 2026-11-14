param(
    [string]$EnvFile = '.env.live',
    [string]$Python = '',
    [switch]$BotOnly,
    [switch]$PreflightOnly,
    [switch]$AllowDelete,
    [ValidateSet('all', 'registration', 'tasks', 'profile')][string]$Suite = 'all',
    [ValidateSet('student', 'teacher')][string]$Role = 'student',
    [ValidateRange(5, 600)][int]$Timeout = 120
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
$previous = @{}
try {
    if (-not $Python) {
        $candidate = Join-Path $projectRoot '.venv\Scripts\python.exe'
        $Python = if (Test-Path -LiteralPath $candidate) { $candidate } else { (Get-Command python -ErrorAction Stop).Source }
    }
    $selectedEnv = (Resolve-Path -LiteralPath $EnvFile).Path
    # Capture configuration in memory only. Never print this JSON or its values.
    $rawSettings = & $Python -c 'import json,sys;from pathlib import Path;from scripts.live_telegram_smoke import settings;print(json.dumps(settings(Path(sys.argv[1]))))' $selectedEnv
    if ($LASTEXITCODE -ne 0) { throw 'Test configuration validation failed; secrets are not displayed.' }
    $configuration = $rawSettings | ConvertFrom-Json
    $configuration | Add-Member -Force -NotePropertyName BASHKIR_ENV_FILE -NotePropertyValue $selectedEnv
    if (-not $configuration.LIVE_TELEGRAM_PROBE_FILE) {
        $configuration | Add-Member -NotePropertyName LIVE_TELEGRAM_PROBE_FILE -NotePropertyValue (Join-Path $projectRoot '.live-telegram\probe.json')
    }
    foreach ($property in $configuration.PSObject.Properties) {
        $previous[$property.Name] = [Environment]::GetEnvironmentVariable($property.Name, 'Process')
        [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'Process')
    }
    if ($BotOnly) {
        Write-Host 'Test-only polling: all other instances for this token must be stopped. Ctrl+C stops this process.'
        & $Python -m bot.main
    } else {
        $arguments = @('scripts/live_telegram_smoke.py', '--env-file', $selectedEnv, '--suite', $Suite, '--role', $Role, '--timeout', [string]$Timeout)
        if (-not $PreflightOnly) { $arguments += '--interactive' }
        if ($AllowDelete) { $arguments += '--allow-delete' }
        & $Python @arguments
    }
    $resultCode = $LASTEXITCODE
} catch {
    Write-Error 'Live test setup failed. Check the selected test-only env, Python dependencies and docs/TELEGRAM_LIVE_TEST.md. Secret values are hidden.'
    $resultCode = 1
} finally {
    foreach ($name in $previous.Keys) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
    Pop-Location
}
exit $resultCode
