@echo off
cd /d H:\project_development\xuangu

echo ========================================
echo   Xuangu - One-click Start
echo ========================================
echo.

echo [0/2] Stopping existing services...
echo   Releasing ports 9999 and 8080...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports=@(9999,8080); $processIds=Get-NetTCPConnection -LocalPort $ports -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 0 } | Select-Object -ExpandProperty OwningProcess -Unique; foreach($processId in $processIds){ try { $p=Get-Process -Id $processId -ErrorAction Stop; Write-Host ('  Killing PID {0} ({1})' -f $processId,$p.ProcessName); Stop-Process -Id $processId -Force -ErrorAction Stop } catch {} }"
taskkill /f /im python.exe 2>nul
taskkill /f /im uvicorn.exe 2>nul
taskkill /f /im node.exe 2>nul
timeout /t 2 /nobreak >nul

echo [1/2] Starting backend...
start "xuangu-backend" cmd /k "call conda activate xuangu && python -m uvicorn backend.main:app --host 127.0.0.1 --port 9999 --workers 1"
echo   Waiting for backend health check...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(60); do { try { $r=Invoke-WebRequest 'http://127.0.0.1:9999/api/v1/health' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { Write-Host '  Backend health OK'; exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); Write-Host '  [WARN] Backend health check timed out; starting frontend anyway'; exit 0"

echo [2/2] Starting frontend...
set NPM_CMD=
for %%X in (npm.cmd) do set NPM_CMD=%%~$PATH:X
if not defined NPM_CMD (
    if exist "G:\Program Files\nodejs\npm.cmd" set NPM_CMD=G:\Program Files\nodejs\npm.cmd
    if exist "C:\Program Files\nodejs\npm.cmd" set NPM_CMD=C:\Program Files\nodejs\npm.cmd
    if exist "%LOCALAPPDATA%\npm\npm.cmd" set NPM_CMD=%LOCALAPPDATA%\npm\npm.cmd
)
if defined NPM_CMD (
    echo Found npm at: %NPM_CMD%
    start "xuangu-frontend" cmd /k "cd /d H:\project_development\xuangu\frontend && call "%NPM_CMD%" run dev"
) else (
    echo [WARN] npm not found. Please start frontend manually:
    echo   cd H:\project_development\xuangu\frontend
    echo   npm run dev
)
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo   Frontend : http://localhost:8080
echo   Backend  : http://127.0.0.1:9999
echo   API Docs : http://127.0.0.1:9999/docs
echo ========================================
echo.
echo Close the terminal windows to stop services.
echo.
pause
