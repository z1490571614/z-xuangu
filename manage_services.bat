@echo off
chcp 65001 >nul 2>&1
title 选股通知系统 - 服务管理工具
setlocal enabledelayedexpansion

:: ============================================================
::  选股通知系统 - 一键启动/停止管理脚本
::  版本: 1.0
::  兼容: Windows 7/10/11
::  用法: 双击运行，按菜单提示操作
:: ============================================================

set "ROOT_DIR=%~dp0"
set "LOG_DIR=%ROOT_DIR%logs"
set "SCRIPT_LOG=%LOG_DIR%\service_manager.log"
set "VENV_DIR=%ROOT_DIR%.venv"
set "FRONTEND_DIR=%ROOT_DIR%frontend"
set "BACKEND_PORT=9999"
set "FRONTEND_PORT=8080"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: ============================================================
:: 日志函数
:: ============================================================
:log
set "timestamp=%date:~0,4%-%date:~5,2%-%date:~8,2% %time:~0,2%:%time:~3,2%:%time:~6,2%"
set "log_msg=[%timestamp%] %*"
echo %log_msg% >> "%SCRIPT_LOG%"
exit /b

:: ============================================================
:: 获取进程PID（通过端口号）
:: ============================================================
:get_pid_by_port
set "port=%~1"
set "pid="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%port%" ^| findstr "LISTENING" 2^>nul') do (
    set "pid=%%a"
    goto :pid_found
)
:pid_found
if defined pid (
    echo !pid!
) else (
    echo 0
)
exit /b

:: ============================================================
:: 检查服务状态
:: ============================================================
:check_backend
set "backend_pid="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING" 2^>nul') do (
    set "backend_pid=%%a"
)
if defined backend_pid (
    for /f "skip=1 tokens=1" %%b in ('tasklist /fi "PID eq !backend_pid!" /fo csv 2^>nul') do (
        set "backend_name=%%b"
        goto :backend_done
    )
    :backend_done
    echo 运行中 (PID:!backend_pid!^)
) else (
    echo 已停止
)
exit /b

:check_frontend
set "frontend_pid="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING" 2^>nul') do (
    set "frontend_pid=%%a"
)
if defined frontend_pid (
    for /f "skip=1 tokens=1" %%b in ('tasklist /fi "PID eq !frontend_pid!" /fo csv 2^>nul') do (
        set "frontend_name=%%b"
        goto :frontend_done
    )
    :frontend_done
    echo 运行中 (PID:!frontend_pid!^)
) else (
    echo 已停止
)
exit /b

:: ============================================================
:: 显示状态
:: ============================================================
:show_status
cls
echo ╔══════════════════════════════════════════════╗
echo ║       选股通知系统 - 服务状态                  ║
echo ╚══════════════════════════════════════════════╝
echo.
echo  后端服务 (端口 %BACKEND_PORT%^)：
  call :check_backend
echo.
echo  前端服务 (端口 %FRONTEND_PORT%^)：
  call :check_frontend
echo.
echo  日志目录: %LOG_DIR%
echo  数据库文件: %ROOT_DIR%data\xuangu.db
echo.
exit /b

:: ============================================================
:: 停止后端服务
:: ============================================================
:stop_backend
call :log "正在停止后端服务..."
set "killed=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING" 2^>nul') do (
    set "target_pid=%%a"
    taskkill /f /pid !target_pid! >nul 2>&1
    if !errorlevel! equ 0 (
        call :log "后端服务已终止 (PID: !target_pid!^)"
        set killed=1
    )
)
if !killed! equ 0 (
    call :log "后端服务未在运行"
    echo   后端服务未在运行。
) else (
    timeout /t 1 /nobreak >nul
    echo   ✅ 后端服务已停止。
)
exit /b

:: ============================================================
:: 停止前端服务
:: ============================================================
:stop_frontend
call :log "正在停止前端服务..."
set "killed=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING" 2^>nul') do (
    set "target_pid=%%a"
    taskkill /f /pid !target_pid! >nul 2>&1
    if !errorlevel! equ 0 (
        call :log "前端服务已终止 (PID: !target_pid!^)"
        set killed=1
    )
)
if !killed! equ 0 (
    call :log "前端服务未在运行"
    echo   前端服务未在运行。
) else (
    timeout /t 1 /nobreak >nul
    echo   ✅ 前端服务已停止。
)
exit /b

:: ============================================================
:: 完全停止（后端 + 前端）
:: ============================================================
:stop_all
cls
echo.
echo  ⚠ 即将停止所有服务：
echo     - 后端 API 服务 (端口 %BACKEND_PORT%^)
echo     - 前端 Web 服务 (端口 %FRONTEND_PORT%^)
echo.
set "confirm="
set /p confirm="  确认停止？(Y/N，默认Y): 
if /i "!confirm!"=="N" (
    echo   已取消。
    timeout /t 2 /nobreak >nul
    exit /b 0
)
cls
call :log "========== 执行停止操作 =========="
echo.
echo  正在停止所有服务...
echo.
call :stop_backend
call :stop_frontend
echo.
call :log "========== 停止操作完成 =========="
echo  ─────────────────────────────
echo   所有服务已处理完毕。
echo.
echo  按任意键返回主菜单...
pause >nul
exit /b 0

:: ============================================================
:: 启动后端服务（新窗口）
:: ============================================================
:start_backend
call :log "正在启动后端服务..."
echo.
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   ❌ 错误：找不到虚拟环境 Python
    echo      路径: %VENV_DIR%\Scripts\python.exe
    call :log "启动失败：虚拟环境不存在"
    timeout /t 3 /nobreak >nul
    exit /b 1
)
:: 检查端口是否被占用
set "existing_pid="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING" 2^>nul') do set "existing_pid=%%a"
if defined existing_pid (
    echo   ⚠ 后端端口 %BACKEND_PORT% 已被占用 (PID: !existing_pid!^)
    echo     将尝试强制释放...
    taskkill /f /pid !existing_pid! >nul 2>&1
    timeout /t 1 /nobreak >nul
)
cd /d "%ROOT_DIR%"
start "XuanGu-Backend" /min "%VENV_DIR%\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port %BACKEND_PORT% --log-level info
set "launch_rc=%errorlevel%"
if !launch_rc! neq 0 (
    echo   ❌ 启动失败，错误码: !launch_rc!
    call :log "后端服务启动失败，错误码: !launch_rc!"
    exit /b 1
)
echo   正在等待后端服务就绪...
for /l %%i in (1,1,15) do (
    timeout /t 1 /nobreak >nul
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING" 2^>nul') do (
        set "new_pid=%%a"
        goto :backend_ready
    )
)
:backend_ready
if not defined new_pid (
    echo   ❌ 后端服务启动超时（15秒）
    call :log "后端服务启动超时"
    exit /b 1
)
echo   ✅ 后端服务已启动 (PID: !new_pid!^)
echo      地址: http://localhost:%BACKEND_PORT%/
echo      文档: http://localhost:%BACKEND_PORT%/docs
call :log "后端服务启动成功 (PID: !new_pid!^)"
exit /b 0

:: ============================================================
:: 启动前端服务（新窗口）
:: ============================================================
:start_frontend
call :log "正在启动前端服务..."
echo.
if not exist "%FRONTEND_DIR%\package.json" (
    echo   ❌ 错误：找不到前端项目配置
    echo      路径: %FRONTEND_DIR%\package.json
    call :log "启动失败：前端项目不存在"
    timeout /t 3 /nobreak >nul
    exit /b 1
)
:: 检查 node_modules
if not exist "%FRONTEND_DIR%\node_modules" (
    echo   ⚠ 未安装前端依赖，正在安装...
    cd /d "%FRONTEND_DIR%"
    call npm install --registry=https://registry.npmmirror.com
    if !errorlevel! neq 0 (
        echo   ❌ 前端依赖安装失败
        call :log "前端依赖安装失败"
        timeout /t 3 /nobreak >nul
        exit /b 1
    )
    echo   ✅ 前端依赖安装完成
)
:: 检查端口是否被占用
set "existing_fpid="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING" 2^>nul') do set "existing_fpid=%%a"
if defined existing_fpid (
    echo   ⚠ 前端端口 %FRONTEND_PORT% 已被占用 (PID: !existing_fpid!^)
    taskkill /f /pid !existing_fpid! >nul 2>&1
    timeout /t 1 /nobreak >nul
)
cd /d "%FRONTEND_DIR%"
start "XuanGu-Frontend" /min cmd /c "npm run dev"
cd /d "%ROOT_DIR%"
echo   正在等待前端服务就绪...
for /l %%i in (1,1,15) do (
    timeout /t 1 /nobreak >nul
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING" 2^>nul') do (
        set "new_fpid=%%a"
        goto :frontend_ready
    )
)
:frontend_ready
if not defined new_fpid (
    echo   ❌ 前端服务启动超时（15秒）
    call :log "前端服务启动超时"
    exit /b 1
)
echo   ✅ 前端服务已启动 (PID: !new_fpid!^)
echo      地址: http://localhost:%FRONTEND_PORT%/
call :log "前端服务启动成功 (PID: !new_fpid!^)"
exit /b 0

:: ============================================================
:: 完全启动（后端 + 前端，按顺序）
:: ============================================================
:start_all
cls
echo.
echo  ⚠ 即将启动所有服务：
echo     - 后端 API 服务 (端口 %BACKEND_PORT%^)
echo     - 前端 Web 服务 (端口 %FRONTEND_PORT%^)
echo.
echo  启动顺序：先后端 → 再前端
echo.
set "confirm="
set /p confirm="  确认启动？(Y/N，默认Y): 
if /i "!confirm!"=="N" (
    echo   已取消。
    timeout /t 2 /nobreak >nul
    exit /b 0
)
cls
call :log "========== 执行启动操作 =========="
echo.
echo  [1/2] 启动后端服务...
call :start_backend
if !errorlevel! neq 0 (
    echo.
    echo   ❌ 后端启动失败，终止启动流程。
    call :log "启动终止：后端启动失败"
    timeout /t 3 /nobreak >nul
    exit /b 1
)
echo.
echo  [2/2] 启动前端服务...
call :start_frontend
if !errorlevel! neq 0 (
    echo.
    echo   ⚠ 后端已启动但前端启动失败。
    echo      后端地址: http://localhost:%BACKEND_PORT%/
)
echo.
call :log "========== 启动操作完成 =========="
echo  ─────────────────────────────
echo  所有服务已处理完毕。
echo.
echo  按任意键返回主菜单...
pause >nul
exit /b 0

:: ============================================================
:: 重启服务
:: ============================================================
:restart_all
cls
call :log "========== 执行重启操作 =========="
echo.
echo  ⚠ 即将重启所有服务...
echo.
set "confirm="
set /p confirm="  确认重启？(Y/N，默认Y): 
if /i "!confirm!"=="N" (
    echo   已取消。
    timeout /t 2 /nobreak >nul
    exit /b 0
)
cls
echo.
echo  步骤 1/3：停止后端服务...
call :stop_backend
echo.
echo  步骤 2/3：停止前端服务...
call :stop_frontend
echo.
timeout /t 2 /nobreak >nul
echo  步骤 3/3：启动所有服务...
echo.
call :start_all
call :log "========== 重启操作完成 =========="
exit /b 0

:: ============================================================
:: 查看日志
:: ============================================================
:view_log
cls
echo ╔══════════════════════════════════════════════╗
echo ║          服务管理工具 - 操作日志              ║
echo ╚══════════════════════════════════════════════╝
echo.
if not exist "%SCRIPT_LOG%" (
    echo   暂无操作日志。
) else (
    echo   最近 30 条操作记录：
    echo   ─────────────────────────────
    for /f "delims=" %%a in ('type "%SCRIPT_LOG%" ^| findstr /n "^"') do (
        set "line=%%a"
        set "line=!line:*:=!"
        echo   !line!
    )
)
echo.
echo  完整日志: %SCRIPT_LOG%
echo.
echo  按任意键返回主菜单...
pause >nul
exit /b 0

:: ============================================================
:: 主菜单
:: ============================================================
:main_menu
cls
echo ╔══════════════════════════════════════════════╗
echo ║       选股通知系统 - 服务管理工具 v1.0        ║
echo ╠══════════════════════════════════════════════╣
echo ║                                              ║
echo ║  项目目录: %ROOT_DIR%
echo ║                                              ║
echo ╚══════════════════════════════════════════════╝
echo.
echo  ┌──────────────────────────────────────────┐
echo  │  当前服务状态:                            │
call :show_status
echo  └──────────────────────────────────────────┘
echo.
echo  ┌──────────────────────────────────────────┐
echo  │  请选择操作：                             │
echo  │                                          │
echo  │    1. 启动所有服务                        │
echo  │    2. 停止所有服务                        │
echo  │    3. 重启所有服务                        │
echo  │    4. 仅启动后端服务                      │
echo  │    5. 仅停止后端服务                      │
echo  │    6. 仅启动前端服务                      │
echo  │    7. 仅停止前端服务                      │
echo  │    8. 查看操作日志                        │
echo  │    0. 退出                               │
echo  │                                          │
echo  └──────────────────────────────────────────┘
echo.
set /p choice="  请输入数字 (0-8): "

if "!choice!"=="1" goto :start_all
if "!choice!"=="2" goto :stop_all
if "!choice!"=="3" goto :restart_all
if "!choice!"=="4" goto :menu_start_backend
if "!choice!"=="5" goto :menu_stop_backend
if "!choice!"=="6" goto :menu_start_frontend
if "!choice!"=="7" goto :menu_stop_frontend
if "!choice!"=="8" goto :view_log
if "!choice!"=="0" exit /b 0

echo.
echo  无效输入，请重新选择。
timeout /t 2 /nobreak >nul
goto :main_menu

:menu_start_backend
cls
call :log "========== 单独启动后端 =========="
call :start_backend
echo.
echo  按任意键返回主菜单...
pause >nul
goto :main_menu

:menu_stop_backend
cls
call :log "========== 单独停止后端 =========="
call :stop_backend
echo.
echo  按任意键返回主菜单...
pause >nul
goto :main_menu

:menu_start_frontend
cls
call :log "========== 单独启动前端 =========="
call :start_frontend
echo.
echo  按任意键返回主菜单...
pause >nul
goto :main_menu

:menu_stop_frontend
cls
call :log "========== 单独停止前端 =========="
call :stop_frontend
echo.
echo  按任意键返回主菜单...
pause >nul
goto :main_menu
