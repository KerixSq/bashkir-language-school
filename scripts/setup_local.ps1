param([switch]$UseSupabaseCli)
# Запускает локальную среду разработки без доступа к облачному проекту.
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $project
if (-not $UseSupabaseCli) {
    & (Join-Path $PSScriptRoot 'run_local.ps1')
    return
}

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Не найдена команда $Name. Смотри docs/LOCAL_WINDOWS.md"
    }
}

Require-Command 'docker'
Require-Command 'npm'
Require-Command 'node'

& docker info 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'Запусти Docker Desktop и дождись готовности Docker Engine.'
}

if (-not (Test-Path 'node_modules/.bin/supabase.cmd')) {
    Write-Host 'Устанавливаем официальную CLI Supabase в этот проект...' -ForegroundColor Cyan
    & npm install supabase@3.1.0 --save-dev --save-exact
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить Supabase CLI.' }
}

if (-not (Test-Path 'supabase/config.toml')) {
    & npx --no-install supabase init
    if ($LASTEXITCODE -ne 0) { throw 'Supabase CLI init завершился с ошибкой.' }
}

# Браузерный вход без почты: требуется явное включение Supabase Auth.
$configFile = 'supabase/config.toml'
$configText = Get-Content $configFile -Raw -Encoding UTF8
if ($configText -match '(?m)^\s*enable_anonymous_sign_ins\s*=') {
    $configText = [regex]::Replace($configText,
        '(?m)^(\s*enable_anonymous_sign_ins\s*=)\s*(true|false)', '${1} true')
} elseif ($configText -match '(?m)^\[auth\]\s*$') {
    $configText = [regex]::Replace($configText, '(?m)^(\[auth\]\s*)$',
        "`$1`nenable_anonymous_sign_ins = true")
} else {
    $configText += "`n[auth]`nenable_anonymous_sign_ins = true`n"
}
[System.IO.File]::WriteAllText((Join-Path $project $configFile), $configText,
    [System.Text.UTF8Encoding]::new($false))

$networks = & docker network ls --format '{{.Name}}'
if ($LASTEXITCODE -ne 0) { throw 'Не удалось проверить сети Docker.' }
if ('local-network' -notin $networks) {
    & docker network create -o 'com.docker.network.bridge.host_binding_ipv4=127.0.0.1' local-network
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать ограниченную localhost-сеть.' }
}

$networkInfo = & docker network inspect local-network
if ($LASTEXITCODE -ne 0) { throw 'Не удалось проверить параметры local-network.' }
$network = ($networkInfo | ConvertFrom-Json)[0]
if ($network.Options.'com.docker.network.bridge.host_binding_ipv4' -ne '127.0.0.1') {
    throw 'Существующая local-network не ограничена localhost. Запуск остановлен; чужая сеть не изменена.'
}

Write-Host 'Запускаем локальный Supabase. Не публикуй его порты в интернет.' -ForegroundColor Cyan
& npx --no-install supabase start --network-id local-network | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Supabase не запустился. Проверь Docker и объём RAM.' }

# The Python helper updates only Supabase connection keys in .env and keeps
# the existing Telegram token. It also backs up any previous .env locally.
$statusLines = & npx --no-install supabase status -o env
if ($LASTEXITCODE -ne 0) { throw 'Не удалось прочитать статус Supabase.' }
$statusText = ($statusLines -join "`n")
$statusText | & python .\scripts\configure_local_env.py
if ($LASTEXITCODE -ne 0) { throw 'Ошибка настройки локального .env.' }
Write-Host 'Далее: SQL Editor http://127.0.0.1:54323; schema.sql -> seed.sql -> logic.sql.' -ForegroundColor Yellow
Write-Host 'Добавь токен Telegram в .env, затем проверь: python scripts/doctor.py' -ForegroundColor Yellow
