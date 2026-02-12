#!/usr/bin/env python3
import argparse
import base64
import ctypes
import ctypes.wintypes
import json
import os
import shutil
import sqlite3
import urllib.request
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from websocket import create_connection


CHROME_EPOCH_OFFSET = 11644473600


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32


def _bytes_from_blob(blob: DataBlob) -> bytes:
    if not blob.pbData:
        return b""
    data = ctypes.string_at(blob.pbData, blob.cbData)
    kernel32.LocalFree(blob.pbData)
    return data


def crypt_unprotect_data(data: bytes) -> bytes:
    in_blob = DataBlob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
    out_blob = DataBlob()
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        raise RuntimeError("CryptUnprotectData failed")
    return _bytes_from_blob(out_blob)


def load_chrome_key(user_data_dir: Path) -> bytes:
    local_state = user_data_dir / "Local State"
    if not local_state.exists():
        raise FileNotFoundError(f"Local State not found: {local_state}")
    data = json.loads(local_state.read_text(encoding="utf-8"))
    encrypted_key = data.get("os_crypt", {}).get("encrypted_key")
    if not encrypted_key:
        raise RuntimeError("encrypted_key not found in Local State")
    key_bytes = base64.b64decode(encrypted_key)
    if key_bytes.startswith(b"DPAPI"):
        key_bytes = key_bytes[5:]
    return crypt_unprotect_data(key_bytes)


def decrypt_cookie_value(encrypted: bytes, key: bytes) -> str:
    if encrypted.startswith(b"v10") or encrypted.startswith(b"v11"):
        nonce = encrypted[3:15]
        cipher = encrypted[15:]
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, cipher, None)
        return decrypted.decode("utf-8", errors="replace")
    return crypt_unprotect_data(encrypted).decode("utf-8", errors="replace")


def chrome_time_to_epoch_seconds(value: int) -> Optional[int]:
    if not value:
        return None
    return int(value / 1_000_000 - CHROME_EPOCH_OFFSET)


def find_profile_dir(user_data_dir: Path, profile: Optional[str]) -> Path:
    if profile:
        profile_path = Path(profile)
        if not profile_path.is_absolute():
            profile_path = user_data_dir / profile
        return profile_path

    candidates: List[Path] = []
    for entry in user_data_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == "Default" or entry.name.startswith("Profile "):
            candidates.append(entry)

    if not candidates:
        raise RuntimeError("No Chrome profiles found in user data dir")

    def cookies_path(p: Path) -> Optional[Path]:
        for name in ("Network/Cookies", "Cookies"):
            candidate = p / name
            if candidate.exists():
                return candidate
        return None

    best = None
    best_mtime = -1.0
    for candidate in candidates:
        path = cookies_path(candidate)
        if not path:
            continue
        mtime = path.stat().st_mtime
        if mtime > best_mtime:
            best_mtime = mtime
            best = candidate
    if best is None:
        raise RuntimeError("No Cookies DB found in Chrome profiles")
    return best


def iter_cookies(db_path: Path, key: bytes) -> Iterable[dict]:
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        shutil.copy2(db_path, temp_path)
        conn = sqlite3.connect(temp_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT host_key, name, value, encrypted_value, path,
                       expires_utc, is_secure, is_httponly, samesite
                FROM cookies
                WHERE host_key LIKE '%binance.com%'
                """
            )
            rows = cursor.fetchall()
        finally:
            conn.close()
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass

    for host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite in rows:
        if value:
            cookie_value = value
        else:
            cookie_value = decrypt_cookie_value(encrypted_value, key)
        cookie = {
            "name": name,
            "value": cookie_value,
            "domain": host_key,
            "path": path or "/",
            "secure": bool(is_secure),
            "httpOnly": bool(is_httponly),
        }
        expires = chrome_time_to_epoch_seconds(expires_utc)
        if expires:
            cookie["expires"] = expires
        if samesite is not None:
            same_site_map = {0: "unspecified", 1: "lax", 2: "strict", 3: "none"}
            cookie["sameSite"] = same_site_map.get(samesite, "unspecified")
        yield cookie


def _cdp_request(ws, msg_id: int, method: str, params: Optional[dict] = None) -> dict:
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params
    ws.send(json.dumps(payload))
    while True:
        resp = json.loads(ws.recv())
        if resp.get("id") == msg_id:
            return resp


def export_cookies_via_cdp(cdp_url: str) -> List[dict]:
    with urllib.request.urlopen(f"{cdp_url}/json") as resp:
        targets = json.loads(resp.read().decode("utf-8"))
    page = None
    for target in targets:
        if target.get("type") != "page":
            continue
        if "binance.com" in (target.get("url") or ""):
            page = target
            break
        if page is None:
            page = target
    if not page:
        raise RuntimeError("No page target found for CDP export")
    ws_url = page.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("webSocketDebuggerUrl missing in CDP target")
    try:
        ws = create_connection(ws_url)
    except Exception as exc:
        raise RuntimeError(
            "CDP websocket connection failed. "
            "Restart Chrome with --remote-allow-origins=* (or allow 127.0.0.1) "
            "and try again."
        ) from exc
    try:
        _cdp_request(ws, 1, "Network.enable")
        response = _cdp_request(ws, 2, "Network.getAllCookies")
    finally:
        ws.close()
    cookies = response.get("result", {}).get("cookies", [])
    result = []
    for item in cookies:
        domain = item.get("domain") or ""
        if "binance.com" not in domain:
            continue
        cookie = {
            "name": item.get("name", ""),
            "value": item.get("value", ""),
            "domain": domain,
            "path": item.get("path", "/"),
            "secure": bool(item.get("secure")),
            "httpOnly": bool(item.get("httpOnly")),
        }
        expires = item.get("expires")
        if expires:
            cookie["expires"] = int(expires)
        same_site = item.get("sameSite")
        if same_site:
            cookie["sameSite"] = same_site.lower()
        if cookie["name"] and cookie["value"]:
            result.append(cookie)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Binance cookies from Chrome profile.")
    parser.add_argument("--user-data-dir", default="", help="Chrome user data dir")
    parser.add_argument("--profile", default="", help="Profile directory or name (Default/Profile 1)")
    parser.add_argument("--output", default="cookies.json", help="Output path")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222", help="Chrome CDP base URL")
    args = parser.parse_args()

    user_data_dir = Path(args.user_data_dir) if args.user_data_dir else Path(
        os.environ.get("LOCALAPPDATA", "")
    ) / "Google" / "Chrome" / "User Data"
    if not user_data_dir.exists():
        raise FileNotFoundError(f"user data dir not found: {user_data_dir}")

    profile_dir = find_profile_dir(user_data_dir, args.profile or None)
    cookies_db = profile_dir / "Network" / "Cookies"
    if not cookies_db.exists():
        cookies_db = profile_dir / "Cookies"
    if not cookies_db.exists():
        raise FileNotFoundError(f"Cookies DB not found in profile: {profile_dir}")

    key = load_chrome_key(user_data_dir)
    cookies = []
    try:
        cookies = list(iter_cookies(cookies_db, key))
    except PermissionError:
        cookies = export_cookies_via_cdp(args.cdp_url)
    if not cookies:
        raise RuntimeError("No Binance cookies found in profile")

    output = Path(args.output).expanduser().resolve()
    output.write_text(json.dumps(cookies, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"Exported {len(cookies)} cookies to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
