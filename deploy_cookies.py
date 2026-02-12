import argparse
import json
import posixpath
import socket
import sys
import time
from pathlib import Path

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


def load_cookie_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"cookie file not found: {path}")
    raw = path.read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    if isinstance(data, dict) and "cookies" in data:
        if not isinstance(data["cookies"], list):
            raise ValueError("cookie file 'cookies' must be a list")
    elif not isinstance(data, list):
        raise ValueError("cookie file must be a list or {'cookies': [...]} JSON")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload Binance cookies to VPS.")
    parser.add_argument("--host", required=True, help="VPS IP or hostname")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--user", default="root", help="SSH username")
    parser.add_argument("--password", required=True, help="SSH password")
    parser.add_argument(
        "--cookie-path",
        required=True,
        help="Local path to cookies.json",
    )
    parser.add_argument(
        "--remote-dir",
        default="/opt/binance-copy-sync",
        help="Remote installation directory",
    )
    parser.add_argument(
        "--remote-cookie",
        default="cookies.json",
        help="Remote cookie filename (inside remote-dir)",
    )
    parser.add_argument(
        "--auth-mode",
        default="",
        help="Override auth_mode in remote config.json (e.g. cdp or cookie)",
    )
    parser.add_argument("--retries", type=int, default=4, help="SSH retry count")
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=10,
        help="Seconds to wait between SSH retries",
    )
    args = parser.parse_args()

    local_cookie = Path(args.cookie_path).expanduser().resolve()
    cookie_content = load_cookie_file(local_cookie)
    remote_root = args.remote_dir.rstrip("/")
    remote_cookie = args.remote_cookie
    remote_cookie_path = posixpath.join(remote_root, remote_cookie)
    remote_config_path = posixpath.join(remote_root, "config.json")

    transport = connect_transport(
        args.host,
        args.port,
        args.user,
        args.password,
        retries=args.retries,
        retry_delay=args.retry_delay,
    )
    try:
        run_remote(transport, f"mkdir -p {remote_root}")
        with paramiko.SFTPClient.from_transport(transport) as sftp:
            with sftp.open(remote_cookie_path, "w") as fp:
                fp.write(cookie_content)

            with sftp.open(remote_config_path, "r") as fp:
                config = json.loads(fp.read().decode("utf-8-sig"))

            if args.auth_mode:
                config["auth_mode"] = args.auth_mode
            config["cookie_path"] = remote_cookie

            with sftp.open(remote_config_path, "w") as fp:
                fp.write(json.dumps(config, ensure_ascii=True, indent=2))

        run_remote(transport, "systemctl restart binance-copy-sync")
    finally:
        transport.close()

    print("Cookie upload completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
