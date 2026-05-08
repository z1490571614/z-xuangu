#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""快速启动脚本 - 清除缓存并重启前端和后端"""
import os
import sys
import time
import subprocess
import socket

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(ROOT_DIR, ".venv")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
BACKEND_PORT = 9999
FRONTEND_PORT = 8080

print("=" * 60)
print("    选股通知系统 - 快速重启工具")
print("=" * 60)
print()

# --------------------------------------------------------
# 步骤1：停止旧服务
# --------------------------------------------------------
print("[1/6] 正在停止旧服务...")
def kill_process_by_port(port):
    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            timeout=10
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid.isdigit():
                    subprocess.run(['taskkill', '/f', '/pid', pid], 
                                   capture_output=True, timeout=5)
                    print(f"   已停止端口 {port} (PID: {pid})")
    except Exception as e:
        print(f"   停止端口 {port} 时出错: {e}")

kill_process_by_port(BACKEND_PORT)
kill_process_by_port(FRONTEND_PORT)
time.sleep(1)
print("   ✅ 旧服务已停止")
print()

# --------------------------------------------------------
# 步骤2：清除缓存
# --------------------------------------------------------
print("[2/6] 正在清除缓存...")
try:
    # 清除Python缓存
    import shutil
    cache_dirs = []
    for root, dirs, files in os.walk(ROOT_DIR):
        if "__pycache__" in dirs:
            cache_dirs.append(os.path.join(root, "__pycache__"))
        if ".pyc" in files:
            for f in files:
                if f.endswith(".pyc"):
                    try:
                        os.remove(os.path.join(root, f))
                    except:
                        pass
    
    for d in cache_dirs:
        try:
            shutil.rmtree(d)
        except:
            pass
    
    # 调用缓存清除脚本
    clear_cache_script = os.path.join(ROOT_DIR, "_clear_cache.py")
    if os.path.exists(clear_cache_script):
        python_exe = os.path.join(VENV_DIR, "Scripts", "python.exe")
        if os.path.exists(python_exe):
            subprocess.run([python_exe, clear_cache_script], 
                         capture_output=True, timeout=30)
    
    print("   ✅ 缓存已清除")
except Exception as e:
    print(f"   ⚠ 清除缓存时出错: {e}")
print()

# --------------------------------------------------------
# 步骤3：检查虚拟环境
# --------------------------------------------------------
print("[3/6] 检查虚拟环境...")
python_exe = os.path.join(VENV_DIR, "Scripts", "python.exe")
uvicorn_exe = os.path.join(VENV_DIR, "Scripts", "uvicorn.exe")
if not os.path.exists(python_exe):
    print("   ❌ 错误：虚拟环境Python不存在")
    print(f"      路径: {python_exe}")
    sys.exit(1)
print("   ✅ 虚拟环境正常")
print()

# --------------------------------------------------------
# 步骤4：启动后端服务
# --------------------------------------------------------
print("[4/6] 启动后端服务...")
backend_process = None
try:
    os.chdir(ROOT_DIR)
    # 不弹出新窗口，在后台运行
    backend_process = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "backend.main:app", 
         "--host", "0.0.0.0", "--port", str(BACKEND_PORT), 
         "--log-level", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print(f"   ✅ 后端已启动 (PID: {backend_process.pid})")
    print(f"      地址: http://localhost:{BACKEND_PORT}/")
except Exception as e:
    print(f"   ❌ 后端启动失败: {e}")
    sys.exit(1)
print()

# --------------------------------------------------------
# 步骤5：等待后端就绪
# --------------------------------------------------------
print("[5/6] 等待后端就绪...")
backend_ready = False
for i in range(20):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', BACKEND_PORT))
        sock.close()
        if result == 0:
            backend_ready = True
            print("   ✅ 后端已就绪")
            break
    except:
        pass
    time.sleep(1)
    print(f"   等待... ({i+1}/20)")

if not backend_ready:
    print("   ⚠ 后端启动可能有问题，请检查")
print()

# --------------------------------------------------------
# 步骤6：启动前端服务
# --------------------------------------------------------
print("[6/6] 启动前端服务...")
frontend_process = None
try:
    if not os.path.exists(FRONTEND_DIR):
        print(f"   ⚠ 前端目录不存在: {FRONTEND_DIR}")
    else:
        package_json = os.path.join(FRONTEND_DIR, "package.json")
        if os.path.exists(package_json):
            # 检查node_modules
            node_modules = os.path.join(FRONTEND_DIR, "node_modules")
            if not os.path.exists(node_modules):
                print("   ⚠ 未安装前端依赖，正在安装...")
                subprocess.run(
                    ['cmd', '/c', 'npm', 'install'],
                    cwd=FRONTEND_DIR,
                    timeout=300,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            # 启动前端（不弹出新窗口）
            frontend_process = subprocess.Popen(
                ['cmd', '/c', 'npm', 'run', 'dev'],
                cwd=FRONTEND_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print(f"   ✅ 前端已启动 (PID: {frontend_process.pid})")
            print(f"      地址: http://localhost:{FRONTEND_PORT}/")
        else:
            print("   ⚠ 前端项目不存在")
except Exception as e:
    print(f"   ⚠ 前端启动失败: {e}")
print()

# --------------------------------------------------------
# 完成提示
# --------------------------------------------------------
print("=" * 60)
print("  🎉 服务重启完成！")
print("=" * 60)
print()
print("  后端地址: http://localhost:9999/")
print("  API文档: http://localhost:9999/docs")
print("  前端地址: http://localhost:8080/")
print()
print("  ✅ 所有服务已在后台运行")
print("  无弹出窗口，安静运行")
print()

