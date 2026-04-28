"""
关闭项目 - 停止后端和前端服务
"""
import os
import time
import socket
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(ROOT_DIR, "logs")
SCRIPT_LOG = os.path.join(LOG_DIR, "service_manager.log")
BACKEND_PORT = 9999
FRONTEND_PORT = 8080

os.makedirs(LOG_DIR, exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(SCRIPT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_pid_by_port(port):
    import subprocess
    result = subprocess.run(["netstat", "-ano"], capture_output=True)
    if result.stdout is None:
        return None
    output = result.stdout.decode("gbk", errors="ignore")
    for line in output.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            parts = line.strip().split()
            pid = parts[-1]
            if pid.isdigit():
                return int(pid)
    return None


def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def stop_service(name, port):
    log(f"正在停止 {name}...")
    pid = get_pid_by_port(port)
    if pid is None:
        log(f"  {name} 未在运行")
        return

    import subprocess
    subprocess.run(["taskkill", "/f", "/pid", str(pid)],
                   capture_output=True, timeout=5)
    log(f"  ✅ {name} 已停止 (PID={pid})")
    time.sleep(1)


def confirm():
    print(f"\n  ⚠️  将停止以下服务:")
    print(f"     - 后端 API 服务 (端口 {BACKEND_PORT})")
    print(f"     - 前端 Web 服务 (端口 {FRONTEND_PORT})")
    print()
    answer = input("  确认停止？(Y/N，默认Y): ").strip().upper()
    return answer != "N"


def main():
    print("=" * 50)
    print("  选股通知系统 - 关闭工具")
    print("=" * 50)
    print()

    if not confirm():
        print("  已取消")
        return

    log("========== 执行停止操作 ==========")
    stop_service("后端服务", BACKEND_PORT)
    stop_service("前端服务", FRONTEND_PORT)
    log("========== 停止操作完成 ==========")
    print("\n  ✅ 所有服务已停止")


if __name__ == "__main__":
    main()
