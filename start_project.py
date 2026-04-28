"""
启动项目 - 先后端再前端
"""
import os
import sys
import subprocess
import time
import socket
import signal
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(ROOT_DIR, "logs")
SCRIPT_LOG = os.path.join(LOG_DIR, "service_manager.log")
VENV_DIR = os.path.join(ROOT_DIR, ".venv")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
BACKEND_PORT = 9999
FRONTEND_PORT = 8080

os.makedirs(LOG_DIR, exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(SCRIPT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def kill_process_on_port(port):
    """通过 netstat 查找并杀掉端口进程"""
    import subprocess
    result = subprocess.run(["netstat", "-ano"], capture_output=True)
    if result.stdout is None:
        return False
    output = result.stdout.decode("gbk", errors="ignore")
    for line in output.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            parts = line.strip().split()
            pid = parts[-1]
            if pid.isdigit():
                subprocess.run(["taskkill", "/f", "/pid", pid],
                               capture_output=True, timeout=5)
                log(f"已释放端口 {port} (PID={pid})")
                return True
    return False


def start_backend():
    log("========== 启动后端 ==========")
    if is_port_open(BACKEND_PORT):
        log(f"端口 {BACKEND_PORT} 已被占用，尝试释放...")
        kill_process_on_port(BACKEND_PORT)
        time.sleep(1)

    python_exe = os.path.join(VENV_DIR, "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        log(f"❌ 虚拟环境 Python 不存在: {python_exe}")
        return False

    cmd = [
        python_exe, "-m", "uvicorn", "backend.main:app",
        "--host", "0.0.0.0", "--port", str(BACKEND_PORT),
        "--log-level", "info"
    ]

    log("启动后端服务...")
    subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )

    for i in range(15):
        time.sleep(1)
        if is_port_open(BACKEND_PORT):
            log(f"✅ 后端服务已启动 (http://localhost:{BACKEND_PORT}/)")
            return True

    log("❌ 后端服务启动超时")
    return False


def start_frontend():
    log("========== 启动前端 ==========")
    if is_port_open(FRONTEND_PORT):
        log(f"端口 {FRONTEND_PORT} 已被占用，尝试释放...")
        kill_process_on_port(FRONTEND_PORT)
        time.sleep(1)

    package_json = os.path.join(FRONTEND_DIR, "package.json")
    if not os.path.exists(package_json):
        log(f"❌ 前端项目不存在: {FRONTEND_DIR}")
        return False

    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    if not os.path.exists(node_modules):
        log("⚠️ 未安装前端依赖，正在安装...")
        npm = subprocess.run(
            ["npm", "install", "--registry=https://registry.npmmirror.com"],
            cwd=FRONTEND_DIR, capture_output=True, text=True
        )
        if npm.returncode != 0:
            log(f"❌ 前端依赖安装失败:\n{npm.stderr}")
            return False
        log("✅ 前端依赖安装完成")

    log("启动前端服务...")
    subprocess.Popen(
        ["cmd", "/c", "npm", "run", "dev"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )

    for i in range(15):
        time.sleep(1)
        if is_port_open(FRONTEND_PORT):
            log(f"✅ 前端服务已启动 (http://localhost:{FRONTEND_PORT}/)")
            return True

    log("❌ 前端服务启动超时")
    return False


def main():
    print("=" * 50)
    print("  选股通知系统 - 启动工具")
    print("=" * 50)
    print(f"\n  项目目录: {ROOT_DIR}\n")

    ok = start_backend()
    if not ok:
        log("🚫 后端启动失败，终止流程")
        sys.exit(1)

    start_frontend()

    print("\n" + "=" * 50)
    print("  后端: http://localhost:9999/")
    print("  文档: http://localhost:9999/docs")
    print("  前端: http://localhost:8080/")
    print("=" * 50)


if __name__ == "__main__":
    main()
