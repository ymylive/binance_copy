import argparse
import re
import socket
import sys
import time
import urllib.request

import paramiko


def run_remote_raw(transport: paramiko.Transport, command: str) -> tuple[int, str, str]:
    session = transport.open_session()
    session.exec_command(command)
    out = session.makefile("r", -1).read().decode("utf-8", errors="ignore")
    err = session.makefile_stderr("r", -1).read().decode("utf-8", errors="ignore")
    exit_status = session.recv_exit_status()
    session.close()
    return exit_status, out, err


def run_remote(transport: paramiko.Transport, command: str) -> None:
    exit_status, out, err = run_remote_raw(transport, command)
    if out:
        print(out.strip())
    if err:
        print(err.strip(), file=sys.stderr)
    if exit_status != 0:
        raise RuntimeError(f"Command failed ({exit_status}): {command}")


def run_remote_allow_fail(transport: paramiko.Transport, command: str) -> int:
    exit_status, out, err = run_remote_raw(transport, command)
    if out:
        print(out.strip())
    if err:
        print(err.strip(), file=sys.stderr)
    return exit_status


def has_command(transport: paramiko.Transport, command: str) -> bool:
    exit_status, _, _ = run_remote_raw(transport, f"command -v {command}")
    return exit_status == 0


def connect_transport(
    host: str,
    port: int,
    user: str,
    password: str,
    retries: int,
    retry_delay: int,
) -> paramiko.Transport:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            sock = socket.create_connection((host, port), timeout=30)
            sock.settimeout(300)
            transport = paramiko.Transport(sock)
            transport.banner_timeout = 300
            transport.auth_timeout = 300
            transport.start_client(timeout=300)
            transport.auth_password(username=user, password=password, fallback=True)
            return transport
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(retry_delay)
    raise RuntimeError(f"SSH connection failed after {retries} attempts: {last_error}")


def fetch_latest_mihomo_tag() -> str:
    url = "https://github.com/MetaCubeX/mihomo/releases/latest"
    with urllib.request.urlopen(url, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    match = re.search(r"/MetaCubeX/mihomo/releases/tag/([^\"\\s>]+)", html)
    if not match:
        raise RuntimeError("Failed to detect mihomo release tag.")
    return match.group(1)


def resolve_mihomo_asset(tag: str, arch: str) -> str:
    if arch in {"x86_64", "amd64"}:
        return f"mihomo-linux-amd64-{tag}.gz"
    if arch in {"aarch64", "arm64"}:
        return f"mihomo-linux-arm64-{tag}.gz"
    raise RuntimeError(f"Unsupported architecture: {arch}")


def detect_package_manager(transport: paramiko.Transport) -> str:
    if has_command(transport, "apt-get"):
        return "apt"
    if has_command(transport, "dnf"):
        return "dnf"
    if has_command(transport, "yum"):
        return "yum"
    return ""


def ensure_packages(transport: paramiko.Transport) -> None:
    pkg_mgr = detect_package_manager(transport)
    if not pkg_mgr:
        raise RuntimeError("Unsupported VPS (no apt-get/dnf/yum found).")
    if pkg_mgr == "apt":
        run_remote(transport, "apt-get update -y")
        run_remote(transport, "apt-get install -y curl unzip gzip")
    else:
        run_remote(transport, f"{pkg_mgr} install -y curl unzip gzip")


def install_mihomo(transport: paramiko.Transport, tag: str, arch: str) -> None:
    asset = resolve_mihomo_asset(tag, arch)
    url = f"https://github.com/MetaCubeX/mihomo/releases/download/{tag}/{asset}"
    run_remote(transport, "mkdir -p /opt/mihomo /opt/mihomo/providers")
    run_remote(transport, f"curl -L {url} -o /tmp/mihomo.gz")
    run_remote(transport, "gzip -d -f /tmp/mihomo.gz")
    run_remote(transport, "install -m 755 /tmp/mihomo /opt/mihomo/mihomo")

    service_content = """[Unit]
Description=Mihomo Core
After=network.target

[Service]
Type=simple
ExecStart=/opt/mihomo/mihomo -d /opt/mihomo
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""
    config_content = """mixed-port: 7890
allow-lan: true
mode: rule
log-level: info
external-controller: 127.0.0.1:9090
external-ui: /opt/mihomo/ui
secret: ""
proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - DIRECT
rules:
  - MATCH,PROXY
"""

    with paramiko.SFTPClient.from_transport(transport) as sftp:
        with sftp.open("/tmp/mihomo.service", "w") as fp:
            fp.write(service_content)
        with sftp.open("/opt/mihomo/config.yaml", "w") as fp:
            fp.write(config_content)

    run_remote(transport, "mv /tmp/mihomo.service /etc/systemd/system/mihomo.service")
    run_remote(transport, "chmod 644 /etc/systemd/system/mihomo.service")
    run_remote(transport, "systemctl daemon-reload")
    run_remote(transport, "systemctl enable mihomo")
    run_remote(transport, "systemctl restart mihomo")


def install_metacubex(transport: paramiko.Transport) -> None:
    ui_url = "https://github.com/MetaCubeX/metacubexd/archive/refs/heads/gh-pages.zip"
    run_remote(transport, "mkdir -p /opt/mihomo/ui")
    run_remote(transport, "rm -rf /tmp/metacubex-ui")
    run_remote(transport, "mkdir -p /tmp/metacubex-ui")
    run_remote(transport, f"curl -L {ui_url} -o /tmp/metacubex.zip")
    run_remote(transport, "unzip -o /tmp/metacubex.zip -d /tmp/metacubex-ui")
    run_remote(transport, "rm -rf /opt/mihomo/ui/*")
    run_remote(transport, "cp -r /tmp/metacubex-ui/*/* /opt/mihomo/ui/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install mihomo + MetaCubeX UI.")
    parser.add_argument("--host", required=True, help="VPS IP or hostname")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--user", default="root", help="SSH username")
    parser.add_argument("--password", required=True, help="SSH password")
    parser.add_argument("--tag", default="", help="Override mihomo tag (e.g. v1.19.18)")
    parser.add_argument("--skip-ui", action="store_true", help="Skip MetaCubeX UI install")
    parser.add_argument("--retries", type=int, default=4, help="SSH retry count")
    parser.add_argument("--retry-delay", type=int, default=10, help="Seconds between retries")
    args = parser.parse_args()

    tag = args.tag or fetch_latest_mihomo_tag()

    transport = connect_transport(
        args.host,
        args.port,
        args.user,
        args.password,
        retries=args.retries,
        retry_delay=args.retry_delay,
    )
    try:
        ensure_packages(transport)
        _, arch_raw, _ = run_remote_raw(transport, "uname -m")
        arch = (arch_raw or "").strip()
        if not arch:
            raise RuntimeError("Failed to detect remote architecture.")
        install_mihomo(transport, tag, arch)
        if not args.skip_ui:
            install_metacubex(transport)
    finally:
        transport.close()

    print("Proxy components installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
