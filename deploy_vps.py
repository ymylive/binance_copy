import argparse
import json
import os
import posixpath
import socket
import time
import sys
from pathlib import Path

import paramiko


EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__", ".chrome-debug", ".chrome-debug-visible"}
EXCLUDE_SUFFIXES = {".pyc"}
EXCLUDE_FILES = {".DS_Store", "config.json", "trade_config.json", "cookies.json"}

ACME_HOME = "/opt/acme.sh"
ACME_SRC_DIR = "/opt/acme.sh-src"
ACME_CONFIG_HOME = "/opt/acme.sh/config"
ACME_CERT_ROOT = "/etc/ssl/acme"
ACME_WEBROOT = "/var/www/acme-challenge"


def iter_local_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.is_dir():
            continue
        if path.name in EXCLUDE_FILES:
            continue
        if path.suffix in EXCLUDE_SUFFIXES:
            continue
        files.append(path)
    return files


def mkdir_p(sftp: paramiko.SFTPClient, remote_path: str) -> None:
    parts = remote_path.strip("/").split("/")
    current = ""
    for part in parts:
        current = f"{current}/{part}"
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def run_remote_raw(
    transport: paramiko.Transport,
    command: str,
) -> tuple[int, str, str]:
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


def reload_nginx(transport: paramiko.Transport) -> None:
    if run_remote_allow_fail(transport, "systemctl reload nginx") != 0:
        run_remote(transport, "systemctl restart nginx")


def has_command(transport: paramiko.Transport, command: str) -> bool:
    exit_status, _, _ = run_remote_raw(transport, f"command -v {command}")
    return exit_status == 0


def remote_file_exists(transport: paramiko.Transport, path: str) -> bool:
    exit_status, _, _ = run_remote_raw(transport, f"test -f {path}")
    return exit_status == 0


def acme_sh_command() -> str:
    return f"{ACME_HOME}/acme.sh --home {ACME_HOME} --config-home {ACME_CONFIG_HOME}"


def detect_package_manager(transport: paramiko.Transport) -> str:
    if has_command(transport, "apt-get"):
        return "apt"
    if has_command(transport, "dnf"):
        return "dnf"
    if has_command(transport, "yum"):
        return "yum"
    return ""


def ensure_acme_sh(transport: paramiko.Transport, pkg_mgr: str, email: str) -> None:
    src_path = posixpath.join(ACME_SRC_DIR, "acme.sh")
    if not remote_file_exists(transport, src_path):
        if not has_command(transport, "git"):
            if not pkg_mgr:
                raise RuntimeError("git is required for acme.sh install but no package manager detected.")
            if pkg_mgr == "apt":
                run_remote(transport, "apt-get install -y git")
            elif pkg_mgr in {"dnf", "yum"}:
                run_remote(transport, f"{pkg_mgr} install -y git")
        run_remote(transport, f"rm -rf {ACME_SRC_DIR}")
        run_remote(
            transport,
            f"git clone --depth 1 https://github.com/acmesh-official/acme.sh.git {ACME_SRC_DIR}",
        )
    run_remote(transport, f"mkdir -p {ACME_HOME} {ACME_CONFIG_HOME}")
    run_remote(transport, f"cp {ACME_SRC_DIR}/acme.sh {ACME_HOME}/acme.sh")
    run_remote(transport, f"chmod 755 {ACME_HOME}/acme.sh")
    if email:
        run_remote(
            transport,
            f"{acme_sh_command()} --register-account -m {email} || true",
        )
    cron_line = (
        f"34 3 * * * root {ACME_HOME}/acme.sh --cron --home {ACME_HOME} "
        f"--config-home {ACME_CONFIG_HOME} > /dev/null 2>&1"
    )
    run_remote(
        transport,
        "printf '%s\\n' "
        f"\"{cron_line}\""
        " | tee /etc/cron.d/acme-sh-binance-copy-sync >/dev/null",
    )


def configure_acme_ca(transport: paramiko.Transport, staging: bool) -> None:
    server = "letsencrypt_test" if staging else "letsencrypt"
    run_remote(transport, f"{acme_sh_command()} --set-default-ca --server {server}")


def issue_acme_cert(transport: paramiko.Transport, domain: str) -> None:
    run_remote(transport, f"mkdir -p {ACME_WEBROOT}")
    run_remote(
        transport,
        f"{acme_sh_command()} --issue --webroot {ACME_WEBROOT} -d {domain}",
    )


def install_acme_cert(transport: paramiko.Transport, domain: str) -> None:
    cert_dir = posixpath.join(ACME_CERT_ROOT, domain)
    run_remote(transport, f"mkdir -p {cert_dir}")
    run_remote(
        transport,
        (
            f"{acme_sh_command()} --install-cert -d {domain} "
            f"--key-file {cert_dir}/privkey.pem "
            f"--fullchain-file {cert_dir}/fullchain.pem "
            f'--reloadcmd "systemctl reload nginx"'
        ),
    )


def upload_project(
    sftp: paramiko.SFTPClient,
    local_root: Path,
    remote_root: str,
) -> None:
    files = iter_local_files(local_root)
    for local_path in files:
        rel_path = local_path.relative_to(local_root).as_posix()
        remote_path = posixpath.join(remote_root, rel_path)
        remote_dir = posixpath.dirname(remote_path)
        mkdir_p(sftp, remote_dir)
        sftp.put(str(local_path), remote_path)


def reset_remote(
    transport: paramiko.Transport,
    remote_root: str,
    domain: str,
) -> None:
    nginx_name = f"{domain}.conf"
    run_remote_allow_fail(transport, "systemctl stop binance-copy-sync || true")
    run_remote_allow_fail(transport, "systemctl disable binance-copy-sync || true")
    run_remote_allow_fail(transport, "pkill -f '/opt/binance-copy-sync' || true")
    run_remote_allow_fail(transport, "pkill -f 'playwright/driver' || true")
    run_remote_allow_fail(transport, "rm -f /etc/systemd/system/binance-copy-sync.service")
    run_remote_allow_fail(
        transport,
        f"rm -f /etc/nginx/sites-enabled/{nginx_name} /etc/nginx/sites-available/{nginx_name}",
    )
    run_remote_allow_fail(transport, "systemctl daemon-reload")
    run_remote_allow_fail(transport, f"rm -rf {remote_root}")
    run_remote_allow_fail(transport, "nginx -t || true")
    run_remote_allow_fail(
        transport, "systemctl reload nginx || systemctl restart nginx || true"
    )


def configure_swap(transport: paramiko.Transport, swap_gb: int) -> None:
    if swap_gb <= 0:
        return
    run_remote(transport, "swapoff -a || true")
    run_remote(transport, "rm -f /swapfile")
    run_remote(
        transport,
        f"fallocate -l {swap_gb}G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count={swap_gb * 1024}",
    )
    run_remote(transport, "chmod 600 /swapfile")
    run_remote(transport, "mkswap /swapfile")
    run_remote(transport, "swapon /swapfile")
    run_remote(transport, "sed -i '/\\bswapfile\\b/d' /etc/fstab")
    run_remote(transport, "echo '/swapfile none swap sw 0 0' >> /etc/fstab")


def update_remote_config(
    sftp: paramiko.SFTPClient,
    remote_root: str,
    auth_mode: str,
    disable_projects: bool,
    poll_interval_ms: int | None,
    header_overrides: dict[str, str] | None,
) -> None:
    config_path = posixpath.join(remote_root, "config.json")
    with sftp.open(config_path, "r") as fp:
        data = json.loads(fp.read().decode("utf-8-sig"))

    if auth_mode:
        data["auth_mode"] = auth_mode
        if auth_mode == "cookie":
            data["cookie_path"] = data.get("cookie_path") or "cookies.json"

    if disable_projects:
        for project in data.get("projects", []):
            project["enabled"] = False

    if poll_interval_ms is not None:
        for project in data.get("projects", []):
            project["poll_interval_ms"] = int(poll_interval_ms)

    if header_overrides is not None:
        data["leader_headers"] = header_overrides

    with sftp.open(config_path, "w") as fp:
        fp.write(json.dumps(data, ensure_ascii=True, indent=2))

    if auth_mode == "cookie":
        cookie_path = posixpath.join(remote_root, data["cookie_path"])
        try:
            sftp.stat(cookie_path)
        except FileNotFoundError:
            with sftp.open(cookie_path, "w") as fp:
                fp.write("[]")


def build_nginx_config(
    domain: str,
    ssl_enabled: bool,
    cert_dir: str,
    acme_webroot: str,
) -> str:
    acme_location = f"""    location /.well-known/acme-challenge/ {{
        root {acme_webroot};
    }}
"""
    if ssl_enabled:
        return f"""server {{
    server_name {domain};

{acme_location}
    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    listen 443 ssl;
    ssl_certificate {cert_dir}/fullchain.pem;
    ssl_certificate_key {cert_dir}/privkey.pem;
}}
server {{
    listen 80;
    server_name {domain};
{acme_location}
    location / {{
        return 301 https://$host$request_uri;
    }}
}}
"""
    return f"""server {{
    listen 80;
    server_name {domain};

{acme_location}
    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Binance Copy Sync to VPS.")
    parser.add_argument("--host", required=True, help="VPS IP or hostname")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--user", default="root", help="SSH username")
    parser.add_argument("--password", required=True, help="SSH password")
    parser.add_argument("--domain", required=True, help="Domain to bind in Nginx")
    parser.add_argument(
        "--remote-dir",
        default="/opt/binance-copy-sync",
        help="Remote installation directory",
    )
    parser.add_argument(
        "--project-dir",
        default=str(Path(__file__).resolve().parent),
        help="Local project directory",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip OS package installation",
    )
    parser.add_argument(
        "--skip-pip",
        action="store_true",
        help="Skip venv/pip install",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip project upload",
    )
    parser.add_argument("--retries", type=int, default=4, help="SSH retry count")
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=15,
        help="Seconds to wait between SSH retries",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Stop services and delete existing deployment before install",
    )
    parser.add_argument(
        "--swap-gb",
        type=int,
        default=0,
        help="Create or replace swapfile with this size in GB",
    )
    parser.add_argument(
        "--server-auth-mode",
        default="",
        help="Override auth_mode in remote config.json",
    )
    parser.add_argument(
        "--disable-projects",
        action="store_true",
        help="Disable all projects in remote config.json",
    )
    parser.add_argument(
        "--poll-interval-ms",
        type=int,
        default=None,
        help="Override poll_interval_ms for all projects in remote config.json",
    )
    parser.add_argument(
        "--header-file",
        default="",
        help="JSON file containing leader header overrides",
    )
    parser.add_argument(
        "--enable-ssl",
        action="store_true",
        help="Enable HTTPS via acme.sh and Let's Encrypt",
    )
    parser.add_argument(
        "--ssl-email",
        default="",
        help="Email for Let's Encrypt registration",
    )
    parser.add_argument(
        "--ssl-staging",
        action="store_true",
        help="Use Let's Encrypt staging environment (acme.sh)",
    )
    args = parser.parse_args()

    local_root = Path(args.project_dir).resolve()
    remote_root = args.remote_dir.rstrip("/")

    header_overrides: dict[str, str] | None = None
    if args.header_file:
        header_path = Path(args.header_file).expanduser().resolve()
        header_overrides = json.loads(header_path.read_text(encoding="utf-8"))
        if not isinstance(header_overrides, dict):
            raise RuntimeError("header file must be a JSON object")

    transport = connect_transport(
        args.host,
        args.port,
        args.user,
        args.password,
        retries=args.retries,
        retry_delay=args.retry_delay,
    )
    try:
        if args.reset:
            reset_remote(transport, remote_root, args.domain)

        if args.swap_gb > 0:
            configure_swap(transport, args.swap_gb)

        cert_dir = posixpath.join(ACME_CERT_ROOT, args.domain)
        cert_fullchain = posixpath.join(cert_dir, "fullchain.pem")
        cert_privkey = posixpath.join(cert_dir, "privkey.pem")
        ssl_available = remote_file_exists(transport, cert_fullchain) and remote_file_exists(
            transport, cert_privkey
        )
        ssl_ready = ssl_available
        ssl_requested = args.enable_ssl or ssl_available

        pkg_mgr = ""
        if not args.skip_install:
            pkg_mgr = detect_package_manager(transport)
            if not pkg_mgr:
                raise RuntimeError("Unsupported VPS (no apt-get/dnf/yum found).")

        if pkg_mgr == "apt":
            run_remote(transport, "apt-get update -y")
            run_remote(
                transport,
                "apt-get install -y python3 python3-venv python3-pip nginx",
            )
        elif pkg_mgr in {"dnf", "yum"}:
            run_remote(
                transport,
                f"{pkg_mgr} install -y python3 python3-pip nginx",
            )

        run_remote(transport, f"mkdir -p {ACME_WEBROOT}")

        if not args.skip_upload:
            with paramiko.SFTPClient.from_transport(transport) as sftp:
                mkdir_p(sftp, remote_root)
                upload_project(sftp, local_root, remote_root)

        if (
            args.server_auth_mode
            or args.disable_projects
            or args.poll_interval_ms is not None
            or header_overrides is not None
        ):
            with paramiko.SFTPClient.from_transport(transport) as sftp:
                update_remote_config(
                    sftp,
                    remote_root,
                    auth_mode=args.server_auth_mode,
                    disable_projects=args.disable_projects,
                    poll_interval_ms=args.poll_interval_ms,
                    header_overrides=header_overrides,
                )

        venv_path = posixpath.join(remote_root, "venv")
        if not args.skip_pip:
            run_remote(transport, f"python3 -m venv {venv_path}")
            run_remote(
                transport,
                f"{venv_path}/bin/pip install --upgrade pip",
            )
            run_remote(
                transport,
                f"{venv_path}/bin/pip install -r {remote_root}/requirements.txt",
            )

        service_content = f"""[Unit]
Description=Binance Copy Sync
After=network.target

[Service]
Type=simple
WorkingDirectory={remote_root}
ExecStart={venv_path}/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
"""

        nginx_content = build_nginx_config(
            args.domain,
            ssl_ready,
            cert_dir=cert_dir,
            acme_webroot=ACME_WEBROOT,
        )

        service_path = "/etc/systemd/system/binance-copy-sync.service"
        nginx_name = f"{args.domain}.conf"
        nginx_path = f"/etc/nginx/sites-available/{nginx_name}"
        tmp_service = "/tmp/binance-copy-sync.service"
        tmp_nginx = "/tmp/binance-copy-sync.nginx"

        with paramiko.SFTPClient.from_transport(transport) as sftp:
            with sftp.open(tmp_service, "w") as fp:
                fp.write(service_content)
            with sftp.open(tmp_nginx, "w") as fp:
                fp.write(nginx_content)

        run_remote(transport, "mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled")
        run_remote(transport, f"mv {tmp_service} {service_path}")
        run_remote(transport, f"mv {tmp_nginx} {nginx_path}")
        run_remote(transport, "chmod 644 /etc/systemd/system/binance-copy-sync.service")
        run_remote(transport, f"chmod 644 {nginx_path}")
        run_remote(
            transport,
            f"ln -sf {nginx_path} /etc/nginx/sites-enabled/{nginx_name}",
        )
        run_remote(transport, "systemctl daemon-reload")
        run_remote(transport, "systemctl enable binance-copy-sync")
        run_remote(transport, "systemctl restart binance-copy-sync")
        run_remote(transport, "nginx -t")
        reload_nginx(transport)

        if has_command(transport, "ufw"):
            run_remote(transport, "ufw allow 80/tcp || true")
            if ssl_ready:
                run_remote(transport, "ufw allow 443/tcp || true")

        if args.enable_ssl:
            if not args.ssl_email:
                raise RuntimeError("--ssl-email is required for acme.sh account registration.")
            ensure_acme_sh(transport, pkg_mgr, args.ssl_email)
            configure_acme_ca(transport, args.ssl_staging)
            if not ssl_ready:
                issue_acme_cert(transport, args.domain)
                install_acme_cert(transport, args.domain)

                ssl_ready = True
                nginx_content = build_nginx_config(
                    args.domain,
                    ssl_ready,
                    cert_dir=cert_dir,
                    acme_webroot=ACME_WEBROOT,
                )
                with paramiko.SFTPClient.from_transport(transport) as sftp:
                    with sftp.open(tmp_nginx, "w") as fp:
                        fp.write(nginx_content)
                run_remote(transport, f"mv {tmp_nginx} {nginx_path}")
                run_remote(transport, "nginx -t")
                reload_nginx(transport)
            if has_command(transport, "ufw"):
                run_remote(transport, "ufw allow 443/tcp || true")

    finally:
        transport.close()

    print("Deployment completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
