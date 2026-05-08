$root = "H:\project_development\xuangu"
$backendPort = 9999
$frontendPort = 8080

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  选股通知系统 - 一键启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 后端
Write-Host "[1/2] 启动后端服务..." -ForegroundColor Yellow
$backendJob = Start-Job -ScriptBlock {
    param($dir, $port)
    Set-Location $dir
    conda activate xuangu
    uvicorn backend.main:app --host 127.0.0.1 --port $port --workers 1 --log-level info
} -ArgumentList $root, $backendPort

Start-Sleep -Seconds 5

try {
    $r = Invoke-WebRequest "http://127.0.0.1:$backendPort/api/v1/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "  [OK] 后端启动成功 -> http://127.0.0.1:$backendPort" -ForegroundColor Green
} catch {
    Write-Host "  [..] 后端启动中，稍后检查 http://127.0.0.1:$backendPort" -ForegroundColor Yellow
}

# 前端
Write-Host "[2/2] 启动前端服务..." -ForegroundColor Yellow
$frontendJob = Start-Job -ScriptBlock {
    param($dir, $port)
    Set-Location "$dir\frontend"
    npm run dev
} -ArgumentList $root, $frontendPort

Start-Sleep -Seconds 3
Write-Host "  [OK] 前端启动中 -> http://localhost:$frontendPort" -ForegroundColor Green

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  前端: http://localhost:$frontendPort" -ForegroundColor White
Write-Host "  后端: http://127.0.0.1:$backendPort" -ForegroundColor White
Write-Host "  API:  http://127.0.0.1:$backendPort/docs" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "按 Ctrl+C 停止本窗口（服务在后台继续运行）" -ForegroundColor Red

while ($true) {
    Start-Sleep -Seconds 30
}
