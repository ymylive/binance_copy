#!/usr/bin/env python3
"""部署更新到 VPS"""
# TODO(security): paramiko's AutoAddPolicy below silently trusts any host key
# on first connect, which is vulnerable to MITM on the very first deploy. For
# production use, switch to RejectPolicy + a pinned known_hosts file.
import json
import os
import sys

import paramiko

VPS_HOST = os.getenv("VPS_HOST")
if not VPS_HOST:
    raise SystemExit("set VPS_HOST env var")
VPS_USER = os.getenv("VPS_USER", "root")
VPS_PASS = os.getenv("VPS_PASS")
if not VPS_PASS:
    raise SystemExit("set VPS_PASS env var")
REMOTE_PATH = "/opt/binance-copy-sync/"
LOCAL_PATH = os.path.dirname(os.path.abspath(__file__))

def deploy():
    print(f"连接到 VPS {VPS_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS_HOST, username=VPS_USER, password=VPS_PASS)

    sftp = ssh.open_sftp()

    # 上传更新的文件
    files_to_upload = [
        ("app/binance.py", "app/binance.py"),
        ("app/poller.py", "app/poller.py"),
        ("app/static/index.html", "app/static/index.html"),
        ("app/static/app.js", "app/static/app.js"),
        ("app/static/styles.css", "app/static/styles.css"),
    ]

    for local_file, remote_file in files_to_upload:
        local_path = os.path.join(LOCAL_PATH, local_file)
        remote_path = REMOTE_PATH + remote_file
        print(f"上传 {local_file} -> {remote_path}")
        sftp.put(local_path, remote_path)

    config_path = REMOTE_PATH + "config.json"
    try:
        with sftp.open(config_path, "r") as handle:
            config = json.loads(handle.read().decode("utf-8-sig"))
        config["auth_mode"] = "cdp"
        config.setdefault("cdp_url", "http://127.0.0.1:9222")
        config.setdefault("cookie_path", "cookies.json")
        with sftp.open(config_path, "w") as handle:
            handle.write(json.dumps(config, ensure_ascii=True, indent=2))
        print("已更新远端 config.json: auth_mode=cdp")
    except Exception as exc:
        print(f"更新远端 config.json 失败: {exc}")

    sftp.close()

    # 重启服务
    print("\n重启服务...")
    stdin, stdout, stderr = ssh.exec_command("systemctl restart binance-copy-sync")
    print(stdout.read().decode())
    print(stderr.read().decode())

    # 检查服务状态
    print("\n检查服务状态...")
    stdin, stdout, stderr = ssh.exec_command("systemctl status binance-copy-sync --no-pager -l")
    print(stdout.read().decode())

    ssh.close()
    print("\n部署完成!")

if __name__ == "__main__":
    deploy()
