param([switch]$UseSupabaseCli)
# A single-command launch for an already configured local Supabase project.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if (-not $UseSupabaseCli) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop is required for the primary Compose launch.' }
    & python .\scripts\create_docker_env.py
    if ($LASTEXITCODE -ne 0) { throw 'Environment setup failed.' }
    & docker compose --env-file .env.docker up -d --build --wait
    if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed. Check docker compose logs.' }
    Write-Host 'Website: http://127.0.0.1:54321/web/'
    return
}

$env:BASHKIR_ENV_FILE = Join-Path $root '.env'
$python = (Get-Command python -ErrorAction Stop).Source
if (Test-Path '.venv\Scripts\python.exe') {
    $python = (Resolve-Path '.venv\Scripts\python.exe').Path
}
if (-not (Test-Path '.env')) {
    throw 'Нет .env. Сначала выполни scripts/setup_local.ps1 и настрой токен бота.'
}

Write-Host 'Проверяю локальный Supabase и публичные права...' -ForegroundColor Cyan
& $python .\scripts\doctor.py --require-bot
if ($LASTEXITCODE -ne 0) { throw 'Проверка не пройдена. Исправь ошибку до запуска бота.' }

$site = $null
try {
    $site = Start-Process -FilePath $python -ArgumentList @(
        '-m', 'http.server', '8000', '--bind', '127.0.0.1'
    ) -WorkingDirectory $root -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 1
    $site.Refresh()
    if ($site.HasExited) { throw 'Сайт не запустился: проверь, свободен ли порт 8000.' }
    Write-Host 'Сайт: http://127.0.0.1:8000/web/' -ForegroundColor Green
    Write-Host 'Запускаю Telegram-бота. Ctrl+C завершит и бота, и локальный веб-сервер.' -ForegroundColor Yellow
    & $python -m bot.main
    if ($LASTEXITCODE -ne 0) { throw 'Бот завершился с ошибкой; проверь вывод выше.' }
}
finally {
    if ($site) {
        $site.Refresh()
        if (-not $site.HasExited) { Stop-Process -Id $site.Id -Force -ErrorAction SilentlyContinue }
    }
}
