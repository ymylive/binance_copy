#!/usr/bin/env python3
# TODO(security): paramiko's AutoAddPolicy below silently trusts any host key
# on first connect, which is vulnerable to MITM. Pin a known_hosts file for
# production usage.
import os

import paramiko

VPS_HOST = os.getenv("VPS_HOST")
if not VPS_HOST:
    raise SystemExit("set VPS_HOST env var")
VPS_USER = os.getenv("VPS_USER", "root")
VPS_PASS = os.getenv("VPS_PASS")
if not VPS_PASS:
    raise SystemExit("set VPS_PASS env var")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(VPS_HOST, username=VPS_USER, password=VPS_PASS, timeout=30)

# 检查带单员持仓
stdin, stdout, stderr = ssh.exec_command("curl -s http://127.0.0.1:8000/api/leader-positions", timeout=30)
print("Leader Positions:")
print(stdout.read().decode())

ssh.close()
