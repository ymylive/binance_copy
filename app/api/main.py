from __future__ import annotations

import json
import os
import re
import secrets
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional

from fastapi import Body, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..core.logging import LOG_BUFFER, get_logger
from ..core.paths import ROOT_DIR, STATIC_DIR
from ..core.time import now_ms
from ..domain.config import (
    ConfigPatch,
    LeaderConfig,
    LeaderSubscription,
    ProjectConfig,
    QuickProjectInput,
    SignalConfig,
    OnchainConfig,
)
from ..domain.events import OrderEvent
from ..domain.trade import TradeConfig, TradingAccount
from ..executors.binance import load_trade_config, save_trade_config
from ..services.config_store import ConfigStore
from ..services.state import AppState

INDEX_PATH = STATIC_DIR / "index.html"
FAVICON_PATH = STATIC_DIR / "favicon.svg"

config_store = ConfigStore()
state = AppState(config_store)
logger = get_logger()


# ---------------------------------------------------------------------------
# API token bootstrap
# ---------------------------------------------------------------------------
# Resolution order:
#   1. BINANCE_COPY_API_TOKEN env var
#   2. AppConfig field `api_token` (read-only soft-extra, optional)
#   3. runtime/api_token.txt (auto-generated on first run, mode 0600)
#
# Token is required for all /api/* routes. The static index page and /static/*
# remain public; the front-end is expected to attach the token as a Bearer
# header itself (no front-end change is shipped here).
RUNTIME_DIR = ROOT_DIR / "runtime"
API_TOKEN_FILE = RUNTIME_DIR / "api_token.txt"


def _read_token_from_config() -> Optional[str]:
    try:
        cfg_dict = config_store.load().model_dump()
    except Exception:  # pragma: no cover - defensive
        return None
    value = cfg_dict.get("api_token")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_token_from_file() -> Optional[str]:
    try:
        if API_TOKEN_FILE.is_file():
            text = API_TOKEN_FILE.read_text(encoding="utf-8").strip()
            return text or None
    except OSError:
        return None
    return None


def _generate_and_persist_token() -> str:
    token = secrets.token_urlsafe(32)
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        API_TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
        try:
            os.chmod(API_TOKEN_FILE, 0o600)
        except OSError:
            # On some filesystems chmod is a no-op; not fatal.
            pass
    except OSError as exc:
        logger.error("failed to persist api token: %s", exc)
    # Print once to stdout so an operator can copy it on first boot.
    print(
        f"[binance-copy] generated API token (saved to {API_TOKEN_FILE}): {token}",
        flush=True,
    )
    return token


def _load_api_token() -> str:
    env_token = os.getenv("BINANCE_COPY_API_TOKEN", "").strip()
    if env_token:
        return env_token
    cfg_token = _read_token_from_config()
    if cfg_token:
        return cfg_token
    file_token = _read_token_from_file()
    if file_token:
        return file_token
    return _generate_and_persist_token()


API_TOKEN: str = _load_api_token()


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": "unauthorized",
            "hint": (
                "set Authorization: Bearer <token> header or run with "
                "auth_disabled=true on localhost"
            ),
        },
    )


async def verify_api_token(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """FastAPI dependency: enforce a bearer token on every /api/* route."""
    if not API_TOKEN:
        # Fail closed if we somehow have no token configured.
        raise HTTPException(status_code=503, detail="api token not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        # Raise via HTTPException with a structured detail body matching the
        # hint contract above.
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "hint": (
                    "set Authorization: Bearer <token> header or run with "
                    "auth_disabled=true on localhost"
                ),
            },
        )
    presented = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(presented, API_TOKEN):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "hint": (
                    "set Authorization: Bearer <token> header or run with "
                    "auth_disabled=true on localhost"
                ),
            },
        )


# ---------------------------------------------------------------------------
# CORS allowlist
# ---------------------------------------------------------------------------
def _resolve_cors_origins() -> List[str]:
    default = ["http://localhost:8000", "http://127.0.0.1:8000"]
    try:
        cfg_dict = config_store.load().model_dump()
    except Exception:
        return default
    value = cfg_dict.get("allowed_origins")
    if isinstance(value, list) and all(isinstance(v, str) and v for v in value):
        return list(value)
    return default


# Disable OpenAPI/docs in production to avoid leaking endpoint surface.
app = FastAPI(
    title="Binance Copy Sync",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Round 2 routers (signal-centric API surface).
# Registered BEFORE the legacy @app.get("/api/leaders") block below so that
# FastAPI's first-match route resolution serves the enriched payload to new
# callers. Old callers that hit /api/leaders/{id} (single-segment) still get
# the legacy single-leader handler because the router does not define that
# overload.
# ---------------------------------------------------------------------------
from .routers import leaders as _leaders_router  # noqa: E402
from .routers import signals as _signals_router  # noqa: E402
from .routers import health as _health_router  # noqa: E402
from .routers import metrics as _metrics_router  # noqa: E402

app.include_router(_leaders_router.router, prefix="/api", tags=["leaders"])
app.include_router(_signals_router.router, prefix="/api", tags=["signals"])
app.include_router(_health_router.router, prefix="/api", tags=["health"])
app.include_router(_metrics_router.router, prefix="/api", tags=["metrics"])


# ---------------------------------------------------------------------------
# Global /api/* auth enforcement
# ---------------------------------------------------------------------------
# We apply the bearer-token check as a middleware so every existing and future
# /api/* route is covered without needing to amend 56 decorators. The static
# index ("/", "/favicon.ico") and "/static/*" are exempt by path prefix.
#
# Special case: /api/signals/stream is a Server-Sent Events endpoint. Browser
# EventSource API cannot attach an Authorization header, so we accept the API
# token via ?token= query parameter and validate it inside the route. The
# middleware therefore skips this single path. The route handler itself uses
# secrets.compare_digest so the path is not actually unauthenticated.
@app.middleware("http")
async def _api_auth_middleware(request: Request, call_next):
    path = request.url.path or ""
    if not path.startswith("/api/"):
        return await call_next(request)
    if request.method == "OPTIONS":
        # Let CORS preflight succeed without auth.
        return await call_next(request)
    if path == "/api/signals/stream":
        # Token check is enforced inside the SSE route handler via query param.
        return await call_next(request)
    if not API_TOKEN:
        return JSONResponse(
            status_code=503,
            content={"error": "api token not configured"},
        )
    auth_header = request.headers.get("authorization") or request.headers.get(
        "Authorization"
    )
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return _unauthorized()
    presented = auth_header.split(" ", 1)[1].strip()
    if not secrets.compare_digest(presented, API_TOKEN):
        return _unauthorized()
    return await call_next(request)


# ---------------------------------------------------------------------------
# Secret masking helpers
# ---------------------------------------------------------------------------
_SECRET_FIELDS = ("api_key", "api_secret", "passphrase")


def _mask_secret(value: Any) -> str:
    """Return a masked representation of a credential.

    Empty/None becomes "" so the front-end can detect "not set".
    Non-empty values are rendered as ****<last4> (or **** for short ones).
    """
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if len(text) <= 4:
        return "****"
    return "****" + text[-4:]


def _mask_in_place(payload: Any) -> Any:
    """Recursively mask known credential fields in a dict/list structure."""
    if isinstance(payload, dict):
        for key, value in list(payload.items()):
            if key in _SECRET_FIELDS and isinstance(value, (str, type(None))):
                payload[key] = _mask_secret(value)
            else:
                _mask_in_place(value)
    elif isinstance(payload, list):
        for item in payload:
            _mask_in_place(item)
    return payload


def resolve_cookie_path(value: str):
    try:
        return config_store.resolve_cookie_path(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def normalize_account_id(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def matches_account(project: ProjectConfig, account_id: Optional[str]) -> bool:
    if not account_id:
        return True
    normalized = normalize_account_id(account_id)
    project_id = normalize_account_id(project.trade_account_id)
    if normalized == "default":
        return not project_id or project_id == "default"
    return project_id == normalized




@app.on_event("startup")
async def on_startup() -> None:
    await state.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await state.stop()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(INDEX_PATH)


@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    return FileResponse(FAVICON_PATH, media_type="image/svg+xml")


@app.get("/api/status")
async def status() -> Dict[str, object]:
    header_status = None
    if hasattr(state.leader, "header_status"):
        header_status = state.leader.header_status()
    fetch_health = state.summarize_fetch_health()
    return {
        "cdp_url": state.config.cdp_url,
        "api_base": state.config.api_base,
        "auth_mode": state.config.auth_mode,
        "cookie_path": state.config.cookie_path,
        "cookie_exists": config_store.cookie_exists(state.config),
        "leader_source": state.config.leader_source,
        "leader_proxy_base": state.config.leader_proxy_base,
        "connected": state.leader.connected,
        "last_error": state.leader.last_error,
        "running": state.poller.running(),
        "event_count": len(state.events),
        "leader_headers": header_status,
        "position_hidden": fetch_health.get("position_hidden", False),
    }


@app.get("/api/logs")
async def list_logs(limit: int = 200) -> List[Dict[str, object]]:
    safe_limit = max(1, min(limit, 500))
    logs = list(LOG_BUFFER)[-safe_limit:]
    return list(reversed(logs))


@app.post("/api/connect")
async def connect() -> Dict[str, object]:
    ok = await state.leader.connect()
    return {"connected": ok, "last_error": state.leader.last_error}


@app.get("/api/config")
async def get_config() -> Dict[str, object]:
    payload = state.config.model_dump(mode="json")
    # AppConfig itself does not carry api_key/api_secret today, but mask
    # defensively in case any nested account/leader struct does.
    return _mask_in_place(payload)


@app.post("/api/cookies")
async def upload_cookies(file: UploadFile = File(...)) -> Dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="cookie file is required")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="cookie file is empty")
    try:
        json.loads(content.decode("utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid cookie json: {exc.msg}") from exc

    cookie_path_value = state.config.cookie_path or "cookies.json"
    cookie_path = resolve_cookie_path(cookie_path_value)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_bytes(content)

    await state.update_config(
        ConfigPatch(auth_mode="cookie", cookie_path=cookie_path_value)
    )
    return {"ok": True, "cookie_path": cookie_path_value}


@app.post("/api/cookies/raw")
async def upload_cookies_raw(request: Request) -> Dict[str, object]:
    raw_value: Optional[str] = None
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            raw_value = payload.get("raw")
        elif isinstance(payload, str):
            raw_value = payload
    if raw_value is None:
        body = await request.body()
        if body:
            raw_value = body.decode("utf-8", errors="ignore")
    cookies, headers = parse_cookie_payload(str(raw_value) if raw_value is not None else "")
    if not cookies:
        raise HTTPException(status_code=400, detail="no cookies found in text")
    cookie_path_value = state.config.cookie_path or "cookies.json"
    cookie_path = resolve_cookie_path(cookie_path_value)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(
        json.dumps(cookies, indent=2),
        encoding="utf-8",
    )
    merged_headers = dict(state.config.leader_headers or {})
    for key, value in headers.items():
        if value:
            merged_headers[key] = value
    await state.update_config(
        ConfigPatch(
            auth_mode="cookie",
            cookie_path=cookie_path_value,
            leader_headers=merged_headers or None,
        )
    )
    return {
        "ok": True,
        "cookie_path": cookie_path_value,
        "cookie_count": len(cookies),
        "header_count": len(headers),
    }


@app.post("/api/config")
async def update_config(patch: ConfigPatch) -> Dict[str, object]:
    await state.update_config(patch)
    return {"ok": True}


@app.get("/api/signal-config")
async def get_signal_config() -> Dict[str, object]:
    return state.config.signal.model_dump(mode="json")


@app.post("/api/signal-config")
async def update_signal_config(payload: SignalConfig) -> Dict[str, object]:
    updates = payload.model_dump(exclude_unset=True)
    if updates:
        merged = state.config.signal.model_copy(update=updates)
        await state.update_signal_config(merged)
    return {"ok": True}


@app.get("/api/onchain/config")
async def get_onchain_config() -> Dict[str, object]:
    return state.config.onchain.model_dump(mode="json")


@app.post("/api/onchain/config")
async def update_onchain_config(payload: OnchainConfig) -> Dict[str, object]:
    await state.update_onchain_config(payload)
    return {"ok": True}


@app.get("/api/leader/ping")
async def leader_ping() -> Dict[str, object]:
    raise HTTPException(status_code=410, detail="dom-only mode: leader api disabled")


@app.get("/api/leader/{portfolio_id}/detail")
async def leader_detail(portfolio_id: str) -> Dict[str, object]:
    raise HTTPException(status_code=410, detail="dom-only mode: leader api disabled")


@app.post("/api/leader/{portfolio_id}/order-history")
async def leader_order_history(
    portfolio_id: str,
    payload: Dict[str, object] = Body(...),
) -> Dict[str, object]:
    raise HTTPException(status_code=410, detail="dom-only mode: leader api disabled")


@app.post("/api/leader/{portfolio_id}/position-history")
async def leader_position_history(
    portfolio_id: str,
    payload: Dict[str, object] = Body(...),
) -> Dict[str, object]:
    raise HTTPException(status_code=410, detail="dom-only mode: leader api disabled")


class SimulateOrderInput(BaseModel):
    portfolio_id: Optional[str] = None
    symbol: str = "SOLUSDT"
    side: Literal["BUY", "SELL"] = "BUY"
    position_side: Literal["LONG", "SHORT", "BOTH"] = "LONG"
    notional_usd: float = 2000.0
    price: Optional[float] = None
    action: Optional[Literal["open", "add", "reduce", "close"]] = None
    execute: bool = False


class OKXStopOrderInput(BaseModel):
    sub_pos_id: str
    tp_trigger_px: str = ""
    sl_trigger_px: str = ""
    tp_trigger_px_type: str = ""
    sl_trigger_px_type: str = ""


class OKXAmendInstrumentsInput(BaseModel):
    inst_id: str = ""


class OKXClosePositionInput(BaseModel):
    sub_pos_id: str


def parse_cookie_payload(raw: str) -> tuple[List[Dict[str, str]], Dict[str, str]]:
    text = (raw or "").strip()
    if not text:
        return [], {}

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "cookies" in data and isinstance(data["cookies"], list):
            return data["cookies"], {}
        if isinstance(data, list):
            return data, {}
    except json.JSONDecodeError:
        pass

    header_allowlist = {
        "bnc-uuid": "bnc-uuid",
        "bnc-level": "bnc-level",
        "bnc-location": "bnc-location",
        "bnc-time-zone": "bnc-time-zone",
        "clienttype": "clienttype",
        "lang": "lang",
        "csrftoken": "csrftoken",
        "device-info": "device-info",
        "fvideo-id": "fvideo-id",
        "fvideo-token": "fvideo-token",
        "user-agent": "user-agent",
        "accept-language": "accept-language",
        "x-passthrough-token": "x-passthrough-token",
    }
    cookie_allowlist = [
        "bnc-uuid",
        "BNC_FV_KEY",
        "lang",
        "se_gd",
        "se_gsd",
        "BNC-Location",
        "changeBasisTimeZone",
        "userPreferredCurrency",
        "currentAccount",
        "logined",
        "theme",
        "r20t",
        "r30t",
        "cr00",
        "d1og",
        "r2o1",
        "f30l",
        "futures-layout",
        "aws-waf-token",
        "BNC_FV_KEY_T",
        "BNC_FV_KEY_EXPIRE",
        "p20t",
        "g_state",
        "sensorsdata2015jssdkcross",
        "OptanonConsent",
    ]
    cookie_inject_keys = {
        "bnc-uuid": "bnc-uuid",
        "csrftoken": "csrftoken",
        "lang": "lang",
        "bnc-location": "BNC-Location",
        "fvideo-id": "fvideo-id",
        "fvideo-token": "fvideo-token",
        "device-info": "device-info",
    }
    header_stop_keys = {
        "cookie",
        "accept",
        "accept-encoding",
        "content-type",
        "content-length",
        "origin",
        "referer",
        "dnt",
        "if-none-match",
        "priority",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "host",
        "x-trace-id",
        "x-ui-request-trace",
        "x-passthrough-token",
    }
    header_stop_keys.update(header_allowlist.keys())
    header_key_pattern = re.compile(r"^[A-Za-z0-9-]+$")
    header_kv_pattern = re.compile(r"^([A-Za-z0-9-]+)\s*:\s*(.*)$")

    headers: Dict[str, str] = {}
    cookie_parts: List[str] = []
    lines = text.splitlines()

    def read_value(start: int) -> tuple[str, int]:
        idx = start
        while idx < len(lines):
            value = lines[idx].strip()
            if not value or value.startswith(":"):
                idx += 1
                continue
            if header_kv_pattern.match(value):
                return "", idx
            if value.lower() in header_stop_keys:
                return "", idx
            if header_key_pattern.match(value) and value.lower() in header_stop_keys:
                return "", idx
            return value, idx + 1
        return "", idx

    def read_cookie_parts(start: int) -> tuple[List[str], int]:
        parts: List[str] = []
        idx = start
        while idx < len(lines):
            value = lines[idx].strip()
            if not value or value.startswith(":"):
                idx += 1
                continue
            if header_kv_pattern.match(value):
                return parts, idx
            if value.lower() in header_stop_keys:
                return parts, idx
            if header_key_pattern.match(value) and value.lower() in header_stop_keys:
                return parts, idx
            parts.append(value)
            idx += 1
        return parts, idx

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith(":"):
            i += 1
            continue
        match = header_kv_pattern.match(line)
        if match:
            key = match.group(1).strip().lower()
            value = match.group(2).strip()
            if key == "cookie":
                if value:
                    cookie_parts.append(value)
                extra, next_idx = read_cookie_parts(i + 1)
                cookie_parts.extend(extra)
                i = next_idx
                continue
            if key in header_allowlist:
                if value:
                    headers[header_allowlist[key]] = value
                    i += 1
                    continue
                value, next_idx = read_value(i + 1)
                if value:
                    headers[header_allowlist[key]] = value
                i = next_idx
                continue
            i += 1
            continue

        key_lower = line.lower()
        if key_lower == "cookie":
            extra, next_idx = read_cookie_parts(i + 1)
            cookie_parts.extend(extra)
            i = next_idx
            continue
        if key_lower in header_allowlist:
            value, next_idx = read_value(i + 1)
            if value:
                headers[header_allowlist[key_lower]] = value
            i = next_idx
            continue

        if not cookie_parts and "=" in line and ";" in line:
            if any(token in line for token in ("bnc-uuid=", "BNC_FV_KEY=", "aws-waf-token=")):
                cookie_parts.append(line)
        i += 1

    cookie_value = "".join(cookie_parts).strip()

    cookies: List[Dict[str, str]] = []
    seen = set()

    if not cookie_value:
        # Fallback: try to recover known cookies even if the cookie header is broken.
        for name in cookie_allowlist:
            match = re.search(rf"(?i){re.escape(name)}=([^;\\n]+)", text)
            if match:
                value = match.group(1).strip()
                if value:
                    cookies.append({"name": name, "value": value, "domain": ".binance.com"})
                    seen.add(name)
        return cookies, headers

    for part in cookie_value.split(";"):
        entry = part.strip()
        if not entry or "=" not in entry:
            continue
        name, value = entry.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        cookies.append({"name": name, "value": value, "domain": ".binance.com"})

    for key, output_name in cookie_inject_keys.items():
        value = headers.get(key)
        if value and output_name not in seen:
            cookies.append({"name": output_name, "value": value, "domain": ".binance.com"})
            seen.add(output_name)

    return cookies, headers


@app.get("/api/trade-config")
async def get_trade_config() -> Dict[str, object]:
    payload = load_trade_config().model_dump(mode="json")
    # Mask api_key/api_secret/passphrase on every account before returning.
    return _mask_in_place(payload)


@app.post("/api/trade-config")
async def update_trade_config(payload: TradeConfig) -> Dict[str, object]:
    save_trade_config(payload)
    return {"ok": True}


@app.get("/api/okx/copytrading/leading-positions")
async def okx_existing_leading_positions(
    account_id: Optional[str] = None,
    inst_id: str = "",
) -> Dict[str, object]:
    try:
        return await state.okx_executor.get_existing_leading_positions(account_id, inst_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/okx/copytrading/leading-positions/history")
async def okx_leading_position_history(
    account_id: Optional[str] = None,
    inst_id: str = "",
    after: str = "",
    before: str = "",
    limit: str = "",
) -> Dict[str, object]:
    try:
        return await state.okx_executor.get_leading_position_history(
            account_id=account_id,
            inst_id=inst_id,
            after=after,
            before=before,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/okx/copytrading/leading-positions/stop")
async def okx_place_leading_stop_order(
    payload: OKXStopOrderInput,
    account_id: Optional[str] = None,
) -> Dict[str, object]:
    try:
        return await state.okx_executor.place_leading_stop_order(
            account_id=account_id,
            sub_pos_id=payload.sub_pos_id,
            tp_trigger_px=payload.tp_trigger_px,
            sl_trigger_px=payload.sl_trigger_px,
            tp_trigger_px_type=payload.tp_trigger_px_type,
            sl_trigger_px_type=payload.sl_trigger_px_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/okx/copytrading/leading-positions/close")
async def okx_close_leading_position(
    payload: OKXClosePositionInput,
    account_id: Optional[str] = None,
) -> Dict[str, object]:
    try:
        return await state.okx_executor.close_leading_position(
            account_id=account_id,
            sub_pos_id=payload.sub_pos_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/okx/copytrading/instruments")
async def okx_get_leading_instruments(
    account_id: Optional[str] = None,
) -> Dict[str, object]:
    try:
        return await state.okx_executor.get_leading_instruments(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/okx/copytrading/instruments")
async def okx_amend_leading_instruments(
    payload: OKXAmendInstrumentsInput,
    account_id: Optional[str] = None,
) -> Dict[str, object]:
    try:
        return await state.okx_executor.amend_leading_instruments(
            account_id=account_id,
            inst_id=payload.inst_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/okx/copytrading/profit-sharing")
async def okx_profit_sharing_details(
    account_id: Optional[str] = None,
    after: str = "",
    before: str = "",
    limit: str = "",
) -> Dict[str, object]:
    try:
        return await state.okx_executor.get_profit_sharing_details(
            account_id=account_id,
            after=after,
            before=before,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/okx/copytrading/total-profit-sharing")
async def okx_total_profit_sharing(
    account_id: Optional[str] = None,
) -> Dict[str, object]:
    try:
        return await state.okx_executor.get_total_profit_sharing(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/okx/copytrading/unrealized-profit-sharing")
async def okx_unrealized_profit_sharing(
    account_id: Optional[str] = None,
) -> Dict[str, object]:
    try:
        return await state.okx_executor.get_unrealized_profit_sharing_details(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/follower-equity")
async def get_follower_equity(account_id: Optional[str] = None) -> Dict[str, object]:
    try:
        equity = await state.executor.get_follower_equity(account_id)
    except Exception as exc:
        return {"ok": False, "equity": None, "error": str(exc)}
    if equity is None or equity <= 0:
        return {"ok": False, "equity": equity}
    return {"ok": True, "equity": equity, "ts": now_ms()}


@app.get("/api/projects")
async def list_projects() -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []
    for project in state.list_projects():
        payload = project.model_dump()
        payload["project_id"] = state.project_key(project)
        # === Galaxy trader-card extension ===
        # Surface display fields + sparkline so the /trader cards in
        # kzt.html can render without a second round-trip. The underlying
        # ProjectConfig schema is NOT changed; everything here is derived
        # from existing config + live poller state.
        leader_id = payload.get("leader_id") or payload.get("portfolio_id") or ""
        # ProjectConfig has no `alias` field (extra="ignore" strips unknowns),
        # so display_name is always derived from leader_id; do not re-add an
        # alias lookup without first extending the schema.
        payload["display_name"] = str(leader_id)[:8] if leader_id else "Anon"
        # NOTE: dicebear is an external dep by design (see plan); leader_id is
        # URL-quoted so unusual ids (`&`, `?`, `#`, whitespace) cannot break
        # the URL silently.
        payload["avatar_url"] = (
            f"https://api.dicebear.com/7.x/identicon/svg?seed={urllib.parse.quote(str(leader_id), safe='')}"
            if leader_id
            else ""
        )
        hist = state.poller.equity_history(payload["project_id"], limit=30)
        sparkline = [float(p) for p in hist] if hist else []
        payload["sparkline"] = sparkline
        # sparkline[0] truthiness check is defense-in-depth: equity_history
        # already filters zero samples, but a 0.0 base would div-by-zero.
        if len(sparkline) >= 2 and sparkline[0]:
            base = sparkline[0]
            payload["total_pnl_pct"] = round(
                (sparkline[-1] - base) / base * 100, 2
            )
        else:
            payload["total_pnl_pct"] = None
        items.append(payload)
    return items


@app.get("/api/positions")
async def list_positions() -> List[Dict[str, object]]:
    return state.poller.list_positions()


@app.get("/api/leader-positions")
async def list_leader_positions() -> List[Dict[str, object]]:
    return state.poller.list_current_positions()


@app.post("/api/projects")
async def add_project(project: ProjectConfig) -> Dict[str, object]:
    if project.exchange == "okx":
        if project.leader_id and not project.portfolio_id:
            project.portfolio_id = project.leader_id
        elif project.portfolio_id and not project.leader_id:
            project.leader_id = project.portfolio_id
    await state.poller.stop_project(project.portfolio_id)
    state.upsert_project(project)
    if project.enabled:
        await state.poller.start_project(project)
    return {"ok": True}


@app.post("/api/projects/quick")
async def quick_add_project(payload: QuickProjectInput) -> Dict[str, object]:
    project = ProjectConfig(portfolio_id=payload.portfolio_id, enabled=payload.enabled)
    await state.poller.stop_project(project.portfolio_id)
    state.upsert_project(project)
    if project.enabled:
        await state.poller.start_project(project)
    return {"ok": True}


@app.post("/api/projects/{portfolio_id}/enable")
async def enable_project(
    portfolio_id: str,
    payload: Dict[str, bool] = Body(...),
) -> Dict[str, object]:
    enabled = payload.get("enabled")
    if enabled is None:
        raise HTTPException(status_code=400, detail="enabled is required")
    project = state.resolve_project(portfolio_id)
    project.enabled = bool(enabled)
    state.upsert_project(project)
    project_id = state.project_key(project)
    await state.poller.stop_project(project_id)
    if project.enabled:
        await state.poller.start_project(project)
    return {"ok": True}


@app.delete("/api/projects/{portfolio_id}")
async def remove_project(portfolio_id: str) -> Dict[str, object]:
    try:
        project = state.resolve_project(portfolio_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Project {portfolio_id} not found") from exc
    await state.poller.stop_project(state.project_key(project))
    state.remove_project(state.project_key(project))
    return {"ok": True}


@app.get("/api/events")
async def list_events(limit: int = 200) -> List[Dict[str, object]]:
    limit = max(1, min(limit, 1000))
    return [event.model_dump() for event in list(state.events)[:limit]]


@app.get("/api/onchain/events")
async def list_onchain_events(limit: int = 200) -> List[Dict[str, object]]:
    limit = max(1, min(limit, 1000))
    return [event.model_dump() for event in list(state.onchain_events)[:limit]]


@app.get("/api/follower-positions")
async def list_follower_positions(account_id: str = "") -> List[Dict[str, object]]:
    try:
        items = await state.executor.get_follower_positions(account_id or None)
    except Exception:
        logger.exception("list follower positions failed account_id=%s", account_id or "default")
        return []
    return items


@app.get("/api/allocation")
async def get_allocation(account_id: Optional[str] = None) -> Dict[str, object]:
    projects = [p for p in state.list_projects() if matches_account(p, account_id)]
    project_ids = {state.project_key(p) for p in projects if state.project_key(p)}
    allocations = {
        state.project_key(p): p.allocated_equity_pct
        for p in projects
        if state.project_key(p)
    }
    leverages = {
        state.project_key(p): p.follower_leverage
        for p in projects
        if state.project_key(p)
    }
    total = sum(allocations.values())
    return {
        "allocations": allocations,
        "leverages": leverages,
        "total": total,
        "account_id": account_id or "all",
    }


@app.post("/api/allocation")
async def update_allocation(
    payload: Dict[str, object],
    account_id: Optional[str] = None,
) -> Dict[str, object]:
    allocations_raw: Dict[str, float]
    leverages_raw: Dict[str, float]
    if "allocations" in payload:
        allocations_raw = payload.get("allocations") or {}
        leverages_raw = payload.get("leverages") or {}
    else:
        allocations_raw = payload
        leverages_raw = {}

    if not isinstance(allocations_raw, dict) or not isinstance(leverages_raw, dict):
        raise HTTPException(status_code=400, detail="invalid allocation payload")

    projects = [p for p in state.list_projects() if matches_account(p, account_id)]
    project_ids = {state.project_key(p) for p in projects if state.project_key(p)}

    def _resolve_project(project_id: str) -> ProjectConfig:
        try:
            return state.resolve_project(project_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    for project_id in allocations_raw.keys():
        _resolve_project(project_id)
        if project_id not in project_ids:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    for project_id in leverages_raw.keys():
        _resolve_project(project_id)
        if project_id not in project_ids:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    total = 0.0
    for project in projects:
        project_id = state.project_key(project)
        value = allocations_raw.get(project_id, project.allocated_equity_pct)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid allocation for {project_id}",
            )
        if parsed < 0 or parsed > 100:
            raise HTTPException(
                status_code=400,
                detail=f"Allocation must be between 0 and 100 for {project_id}",
            )
        total += parsed

    if total > 100.0:
        raise HTTPException(status_code=400, detail=f"Total allocation {total}% exceeds 100%")

    for project in projects:
        changed = False
        project_id = state.project_key(project)
        if project_id in allocations_raw:
            project.allocated_equity_pct = float(allocations_raw[project_id])
            changed = True
        if project_id in leverages_raw:
            project.follower_leverage = float(leverages_raw[project_id])
            changed = True
        if changed:
            state.upsert_project(project)

    return {"ok": True, "total": total, "account_id": account_id or "all"}


@app.get("/api/account-summary")
async def get_account_summary(account_id: Optional[str] = None) -> Dict[str, object]:
    balance: Optional[Dict[str, float]] = None
    try:
        balance = await state.executor.get_follower_balance(account_id)
    except Exception:
        logger.exception("get follower balance failed account_id=%s", account_id or "default")
    equity: float = 0.0
    if balance:
        equity = (
            balance.get("margin_balance")
            or balance.get("available_balance")
            or balance.get("wallet_balance")
            or 0.0
        )
    else:
        try:
            equity = await state.executor.get_follower_equity(account_id) or 0.0
        except Exception:
            equity = 0.0
    projects = [p for p in state.list_projects() if matches_account(p, account_id)]
    total_allocated = sum(p.allocated_equity_pct for p in projects)
    allocations = [
        {
            "portfolio_id": p.portfolio_id,
            "allocated_pct": p.allocated_equity_pct,
            "allocated_equity": equity * p.allocated_equity_pct / 100.0 if equity > 0 else 0.0,
            "enabled": p.enabled,
        }
        for p in projects
    ]
    return {
        "account_id": account_id or "default",
        "total_equity": equity,
        "total_allocated_pct": total_allocated,
        "available_pct": 100.0 - total_allocated,
        "margin_balance": balance.get("margin_balance") if balance else 0.0,
        "available_balance": balance.get("available_balance") if balance else 0.0,
        "wallet_balance": balance.get("wallet_balance") if balance else 0.0,
        "unrealized_pnl": balance.get("unrealized_pnl") if balance else 0.0,
        "allocations": allocations,
    }


# Account management endpoints
@app.get("/api/accounts")
async def list_accounts() -> List[Dict[str, object]]:
    try:
        items = [account.model_dump() for account in state.list_accounts()]
    except Exception:
        logger.exception("list accounts failed")
        return []
    # Mask credentials on every account in the list before returning.
    return [_mask_in_place(item) for item in items]


@app.get("/api/accounts/{account_id}")
async def get_account(account_id: str) -> Dict[str, object]:
    try:
        account = state.get_account(account_id)
        return _mask_in_place(account.model_dump())
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")


@app.post("/api/accounts")
async def upsert_account(account: TradingAccount) -> Dict[str, object]:
    state.upsert_account(account)
    return {"ok": True}


@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: str) -> Dict[str, object]:
    state.remove_account(account_id)
    return {"ok": True}


# Leader management endpoints
@app.get("/api/leaders")
async def list_leaders() -> List[Dict[str, object]]:
    return [leader.model_dump() for leader in state.list_leaders()]


@app.get("/api/leaders/{leader_id}")
async def get_leader(leader_id: str) -> Dict[str, object]:
    try:
        leader = state.get_leader(leader_id)
        return leader.model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Leader {leader_id} not found")


@app.post("/api/leaders")
async def upsert_leader(leader: LeaderConfig) -> Dict[str, object]:
    state.upsert_leader(leader)
    return {"ok": True}


@app.delete("/api/leaders/{leader_id}")
async def delete_leader(leader_id: str) -> Dict[str, object]:
    state.remove_leader(leader_id)
    return {"ok": True}


# Subscription management endpoints
@app.get("/api/accounts/{account_id}/subscriptions")
async def list_subscriptions(account_id: str) -> List[Dict[str, object]]:
    try:
        account = state.get_account(account_id)
        return [sub.model_dump() for sub in account.leader_subscriptions]
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")


@app.post("/api/accounts/{account_id}/subscriptions")
async def add_subscription(account_id: str, subscription: LeaderSubscription) -> Dict[str, object]:
    try:
        state.add_leader_subscription(account_id, subscription)
        return {"ok": True}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")


@app.delete("/api/accounts/{account_id}/subscriptions/{leader_id}")
async def remove_subscription(account_id: str, leader_id: str) -> Dict[str, object]:
    try:
        state.remove_leader_subscription(account_id, leader_id)
        return {"ok": True}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")


@app.post("/api/simulate")
async def simulate_order(payload: SimulateOrderInput) -> Dict[str, object]:
    # Hard refuse live execution via the simulate endpoint. The previous
    # behaviour allowed an authenticated caller to flip execute=true and
    # actually fire an order via state.executor.execute() — this is a
    # foot-gun and is now blocked at the entry point.
    if payload.execute:
        raise HTTPException(
            status_code=400,
            detail={"error": "execute=true disabled for safety"},
        )
    if payload.notional_usd <= 0:
        raise HTTPException(status_code=400, detail="notional_usd must be positive")
    portfolio_id = payload.portfolio_id
    if not portfolio_id:
        projects = state.list_projects()
        if not projects:
            raise HTTPException(status_code=400, detail="no projects available")
        portfolio_id = projects[0].portfolio_id
    project = None
    try:
        project = state.get_project(portfolio_id)
    except KeyError:
        project = None
    avg_price = payload.price if payload.price and payload.price > 0 else 0.0
    if avg_price <= 0:
        try:
            trade_config = load_trade_config()
            account = state.executor._resolve_account(
                trade_config,
                project.trade_account_id if project else None,
            )
            if account:
                runtime = state.executor._get_runtime(account.account_id)
                avg_price = await state.executor._get_price(
                    account,
                    runtime,
                    payload.symbol,
                ) or 0.0
        except Exception:
            avg_price = 0.0
    if avg_price <= 0:
        avg_price = 100.0
    leader_executed_qty = payload.notional_usd / avg_price
    side = payload.side.upper()
    position_side = payload.position_side.upper()
    scale_value = 1.0
    scale_mode = "fixed"
    if project and getattr(project, "scale_value", 0) > 0:
        scale_value = project.scale_value
    if project and getattr(project, "scale_mode", ""):
        scale_mode = project.scale_mode
    follower_notional = payload.notional_usd
    if project:
        leader_equity = state.poller.leader_equity(portfolio_id)
        follower_equity = project.follower_equity
        if scale_mode in {"ratio", "adaptive", "leader_margin"}:
            if (
                leader_equity > 0
                and follower_equity > 0
                and project.leader_leverage > 0
                and project.follower_leverage > 0
            ):
                open_pct = payload.notional_usd / (leader_equity * project.leader_leverage)
                open_pct = max(min(open_pct, 1.0), 0.0)
                follower_notional = (
                    follower_equity * project.follower_leverage * open_pct * scale_value
                )
            elif project.leader_leverage > 0 and project.follower_leverage > 0:
                follower_notional = (
                    payload.notional_usd
                    / project.leader_leverage
                    * project.follower_leverage
                    * scale_value
                )
        elif scale_mode == "fixed":
            follower_notional = payload.notional_usd * scale_value
    follower_qty = follower_notional / avg_price
    if side != "BUY":
        follower_qty = -follower_qty
    action = payload.action or "open"
    reduce_only = action in {"reduce", "close"}
    now = now_ms()
    event = OrderEvent(
        event_id=f"sim-{now}",
        portfolio_id=portfolio_id,
        exchange=project.exchange if project else "binance",
        trade_account_id=project.trade_account_id if project else None,
        order_id=f"SIM-{now}",
        trade_id=f"SIM-{now}",
        action=action,
        symbol=payload.symbol,
        position_side=position_side,
        side=side,
        executed_qty=leader_executed_qty,
        avg_price=avg_price,
        order_time=now,
        order_update_time=now,
        leader_delta=leader_executed_qty if side == "BUY" else -leader_executed_qty,
        scale=1.0,
        follower_qty=follower_qty,
        reduce_only=reduce_only,
        order_value=payload.notional_usd,
        follower_notional=follower_notional,
        leader_open_pct=None,
        leader_close_pct=None,
        follower_leverage=project.follower_leverage if project else None,
        status="queued",
        note="simulated",
        created_at=now,
    )
    state.record_event(event)
    # execute=true is rejected at the top of this handler; we never call
    # state.executor.execute(event) from this endpoint.
    result = None
    logger.info(
        "simulated order portfolio=%s symbol=%s side=%s position=%s notional=%s price=%s",
        portfolio_id,
        payload.symbol,
        side,
        position_side,
        payload.notional_usd,
        avg_price,
    )
    return {"ok": True, "event": event.model_dump(), "result": result}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.api.main:app", host="127.0.0.1", port=8000, reload=False)
