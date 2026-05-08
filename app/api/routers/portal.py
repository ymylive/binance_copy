"""Portal-facing API matching the data shapes captured from the reference SaaS.

Every response is wrapped in ``{"data": <payload>, "code": 0, "message": ""}``
to match the shape the front-end (landing/referral/mall/wallet/profile/
tutorial/login) was built against.

Auth: most routes require either the existing admin API_TOKEN bearer
(handled by the global middleware in main.py) OR a per-user portal session
token. Login/register/tutorial are exempt and the global middleware skips
them by path prefix; we still resolve the session if one is present.

Persistence: file-backed via app.services.portal_store.PortalStore.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Cookie, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...core.logging import get_logger
from ...core.paths import ROOT_DIR, STATIC_DIR
from ...services.portal_store import get_portal_store

logger = get_logger()

PORTAL_RUNTIME_DIR = ROOT_DIR / "runtime" / "portal"
EQUITY_SNAPSHOT_DIR = PORTAL_RUNTIME_DIR / "equity_snapshots"

router = APIRouter(prefix="/portal")

TUTORIAL_FILE = STATIC_DIR / "tutorial.md"

# Hardcoded tier tables — match the captured payloads byte-for-byte so
# the front-end tier rendering doesn't need translation logic.
_BIZ_RULES = [
    {"inviteNumber": 0, "level": 1, "commissionRebateRate": 0.1, "triggerNumber": 3, "couponProportion": 0.95, "validDay": 30},
    {"inviteNumber": 7, "level": 2, "commissionRebateRate": 0.15, "triggerNumber": 3, "couponProportion": 0.9, "validDay": 30},
    {"inviteNumber": 16, "level": 3, "commissionRebateRate": 0.18, "triggerNumber": 3, "couponProportion": 0.85, "validDay": 30},
]

_COMMISSION_REBATE_RULES = [
    {"level": 1, "inviteNumber": 0, "commissionRebateRate": 0.1},
    {"level": 2, "inviteNumber": 7, "commissionRebateRate": 0.15},
    {"level": 3, "inviteNumber": 16, "commissionRebateRate": 0.18},
]

_COUPON_RULES = [
    {"typeId": 1, "describtion": "9.5折", "proportion": 0.95},
    {"typeId": 2, "describtion": "9折", "proportion": 0.9},
    {"typeId": 3, "describtion": "8.5折", "proportion": 0.85},
    {"typeId": 4, "describtion": "8折", "proportion": 0.8},
    {"typeId": 5, "describtion": "7.5折", "proportion": 0.75},
    {"typeId": 6, "describtion": "7折", "proportion": 0.7},
    {"typeId": 7, "describtion": "6.5折", "proportion": 0.65},
    {"typeId": 8, "describtion": "6折", "proportion": 0.6},
    {"typeId": 9, "describtion": "5.5折", "proportion": 0.55},
    {"typeId": 10, "describtion": "5折", "proportion": 0.5},
    {"typeId": 11, "describtion": "4.5折", "proportion": 0.45},
    {"typeId": 12, "describtion": "4折", "proportion": 0.4},
]

_TUTORIAL_FALLBACK = (
    "## 教程\r\n\r\n暂未配置教程内容。请将完整 Markdown 写入 "
    "`app/static/tutorial.md`（覆盖此后备文案）。\r\n"
)

_PUBLIC_USER_FIELDS = (
    "userName",
    "balance",
    "email",
    "phoneNumber",
    "authority",
    "invitationCode",
    "rebateLevel",
    "commissionRate",
    "brokerLevel",
    "acceptedAgreement",
    "points",
    "emailVerified",
    "deleted",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ok(data: Any) -> Dict[str, Any]:
    return {"data": data, "code": 0, "message": ""}


def _err(
    message: str,
    code: int = 1,
    status_code: int = 400,
    extra: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    payload: Dict[str, Any] = {"data": None, "code": code, "message": message}
    if extra:
        # Surface auxiliary fields alongside the envelope (e.g. lockedSeconds)
        # so the front-end can render countdowns without parsing the message.
        for k, v in extra.items():
            if k not in payload:
                payload[k] = v
    return JSONResponse(status_code=status_code, content=payload)


def _public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: user.get(k) for k in _PUBLIC_USER_FIELDS}
    # token field appeared in capture but was always null; keep parity.
    out["token"] = None
    return out


def _resolve_token(
    authorization: Optional[str],
    cookie_token: Optional[str],
) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        candidate = authorization.split(" ", 1)[1].strip()
        if candidate:
            return candidate
    return cookie_token or None


def _resolve_user(
    authorization: Optional[str],
    cookie_token: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Resolve a portal user from the bearer token or session cookie.

    Note: a request authenticated only with the admin API_TOKEN (which
    the global middleware accepts for all /api/portal/* routes) will not
    resolve to a portal user here. That is intentional — admin tokens
    are for service-to-service introspection, not end-user identity.
    """
    token = _resolve_token(authorization, cookie_token)
    if not token:
        return None
    return get_portal_store().get_session_user(token)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    if request.client:
        return request.client.host or ""
    return ""


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class LoginInput(BaseModel):
    """Identifier accepts email, userName, or any other string the user
    typed. Field is named `email` for backward compat; `identifier` and
    `username` are accepted aliases so newer clients can use the clearer name.
    """
    model_config = {"populate_by_name": True, "extra": "ignore"}
    email: str = Field(default="", validation_alias="email")
    identifier: Optional[str] = None
    username: Optional[str] = None
    password: str

    @property
    def login_id(self) -> str:
        return (self.identifier or self.username or self.email or "").strip()


class RegisterInput(BaseModel):
    email: str
    password: str
    invitationCode: Optional[str] = None


class RechargeInput(BaseModel):
    amount: float = Field(..., gt=0)


class WithdrawInput(BaseModel):
    amount: float = Field(..., gt=0)
    address: str


class ChangePasswordInput(BaseModel):
    oldPassword: str
    newPassword: str


class SendCodeInput(BaseModel):
    channel: str  # "phone" | "email"
    target: str


class ChangePhoneInput(BaseModel):
    phone: str
    code: str


class ChangeEmailInput(BaseModel):
    email: str
    code: str


class WithdrawAddressInput(BaseModel):
    alias: Optional[str] = ""
    value: str
    network: Optional[str] = "TRC20"


class BindApiKeyInput(BaseModel):
    exchange: str
    apiKey: str
    apiSecret: str
    passphrase: Optional[str] = ""
    alias: Optional[str] = ""


class MallPurchaseInput(BaseModel):
    planId: str
    alias: Optional[str] = ""


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@router.post("/auth/login")
async def login(payload: LoginInput, request: Request) -> Any:
    store = get_portal_store()
    identifier = payload.login_id

    # Step 1: hard lockout check before we leak whether the account exists.
    locked = store.is_locked(identifier)
    if locked:
        mins = max(1, locked // 60)
        return _err(
            f"账号已被临时锁定,请 {mins} 分钟后再试",
            code=2,
            status_code=200,
            extra={"lockedSeconds": locked},
        )

    user = store.get_user_by_identifier(identifier)
    if not user or not store.verify_password(user, payload.password):
        info = store.record_failed_login(identifier)
        if info.get("lockedSeconds"):
            mins = max(1, int(info["lockedSeconds"] / 60))
            return _err(
                f"密码错误次数过多,账号已锁定 {mins} 分钟",
                code=2,
                status_code=200,
                extra={"lockedSeconds": info["lockedSeconds"], "attempts": info["count"]},
            )
        remaining = info.get("remaining", 0)
        return _err(
            f"用户名或密码错误,还可尝试 {remaining} 次",
            code=1,
            status_code=200,
            extra={"remaining": remaining, "attempts": info.get("count", 0)},
        )

    # Successful auth — clear any lingering failure counter for this identifier.
    store.clear_failed_login(identifier)

    # Re-check admin allowlist on every login so operators can promote a user
    # by editing runtime/portal/admin_emails.txt without restarting the server.
    if store.is_admin_email(user.get("email", "")) and int(user.get("authority", 1)) < 9:
        store.update_user(user["id"], authority=9)
        user["authority"] = 9
    token = store.create_session(user["id"])
    store.add_login_record(user["id"], _client_ip(request), location="")
    response = JSONResponse(
        content=_ok({"token": token, "user": _public_user(user)})
    )
    response.set_cookie(
        "portal_session",
        token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/auth/register")
async def register(payload: RegisterInput, request: Request) -> Any:
    store = get_portal_store()
    try:
        user = store.create_user(
            payload.email,
            payload.password,
            invitation_code=payload.invitationCode,
        )
    except ValueError as exc:
        return _err(str(exc), code=1, status_code=200)
    # Grant a free 7-day trial business so the new user can immediately try
    # the platform without going through the wallet/mall flow.
    try:
        store.grant_signup_trial(user["id"], days=7)
    except Exception:
        logger.exception("register: trial grant failed for %s", user.get("id"))
    # Stash a 6-digit verification token in the pending-codes store keyed by
    # email; user clicks /verify-email?token=... or pastes the code.
    try:
        verify_code = f"{secrets.randbelow(900000) + 100000:06d}"
        store.set_pending_code(f"verify:{user['email']}", verify_code, ttl_seconds=24 * 3600)
        logger.info("register: verify code for %s = %s", user['email'], verify_code)
    except Exception:
        logger.exception("register: pending-code save failed")
    token = store.create_session(user["id"])
    store.add_login_record(user["id"], _client_ip(request), location="")
    response = JSONResponse(
        content=_ok({"token": token, "user": _public_user(user)})
    )
    response.set_cookie(
        "portal_session",
        token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/auth/logout")
async def logout(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    token = _resolve_token(authorization, portal_session)
    if token:
        get_portal_store().delete_session(token)
    response = JSONResponse(content=_ok({"ok": True}))
    response.delete_cookie("portal_session")
    return response


@router.get("/auth/me")
async def me(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    return _ok(_public_user(user))


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------
@router.get("/account/userInfo")
async def user_info(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    payload = _public_user(user)
    # Surface inviter email so /referral can credit "邀请人" without an extra
    # round-trip; null for users who registered without a code.
    payload["invitedByEmail"] = get_portal_store().get_inviter_email(user)
    return _ok(payload)


@router.get("/account/referrals")
async def account_referrals(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    """List of users this caller has invited. Powers /referral table."""
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    return _ok(get_portal_store().list_invitees(user["id"]))


# ---- Email verification -------------------------------------------------
class VerifyEmailIn(BaseModel):
    code: str
    email: Optional[str] = None  # falls back to logged-in user's email


class ResendVerifyIn(BaseModel):
    pass


@router.post("/account/verify-email")
async def verify_email(
    payload: VerifyEmailIn,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    target_email = (payload.email or (user or {}).get("email") or "").strip().lower()
    if not target_email:
        return _err("email required", code=1, status_code=200)
    store = get_portal_store()
    if not store.verify_pending_code(f"verify:{target_email}", payload.code.strip()):
        return _err("验证码无效或已过期", code=1, status_code=200)
    target_user = store.get_user_by_email(target_email)
    if not target_user:
        return _err("user not found", code=1, status_code=200)
    store.set_email_verified(target_user["id"], True)
    return _ok({"emailVerified": True})


@router.post("/account/resend-verify")
async def resend_verify(
    _: ResendVerifyIn = Body(default_factory=ResendVerifyIn),
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    if user.get("emailVerified"):
        return _ok({"alreadyVerified": True})
    code = f"{secrets.randbelow(900000) + 100000:06d}"
    get_portal_store().set_pending_code(f"verify:{user['email']}", code, ttl_seconds=24 * 3600)
    logger.info("resend-verify: code for %s = %s", user["email"], code)
    return _ok({"sent": True})


# ---- Account delete (soft archive) --------------------------------------
class AccountDeleteIn(BaseModel):
    password: str
    confirm: Optional[str] = None  # optional "DELETE" string for double-confirm


@router.post("/account/delete")
async def account_delete(
    payload: AccountDeleteIn,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    store = get_portal_store()
    if not store.verify_password(user, payload.password):
        return _err("密码错误,无法注销", code=1, status_code=200)
    if int(user.get("authority", 1)) >= 9:
        return _err("管理员账号禁止自助注销,请先在 /admin 中降权", code=1, status_code=200)
    archived = store.soft_delete_user(user["id"])
    if not archived:
        return _err("user not found", code=1, status_code=200)
    response = JSONResponse(content=_ok({"deleted": True, "deletedAt": archived.get("deletedAt")}))
    response.delete_cookie("portal_session")
    return response


@router.get("/account/funds")
async def funds(
    actionType: int = Query(default=-1),
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    return _ok(get_portal_store().list_funds(user["id"], action_type=actionType))


@router.get("/account/businesses")
async def businesses(
    effective: bool = Query(default=True),
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    return _ok(
        get_portal_store().list_businesses(user["id"], effective_only=effective)
    )


# ---------------------------------------------------------------------------
# Biz / rebate / coupon tier metadata
# ---------------------------------------------------------------------------
@router.get("/biz/rules")
async def biz_rules() -> Any:
    return _ok(_BIZ_RULES)


@router.get("/biz/commissionRebateRules")
async def biz_commission_rebate_rules() -> Any:
    return _ok(_COMMISSION_REBATE_RULES)


@router.get("/biz/couponRules")
async def biz_coupon_rules() -> Any:
    return _ok(_COUPON_RULES)


@router.get("/biz/allCoupons")
async def biz_all_coupons(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    # Per-user coupons; capture was empty so we return [] until a coupon
    # issuance flow exists. We still gate on auth so unauthenticated
    # callers can't probe endpoint shape.
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    return _ok([])


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
@router.get("/home/getInvitatCode")
async def get_invitat_code(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    return _ok(user.get("invitationCode") or "")


@router.get("/home/tutorial")
async def home_tutorial() -> Any:
    if TUTORIAL_FILE.is_file():
        try:
            text = TUTORIAL_FILE.read_text(encoding="utf-8")
        except OSError:
            text = _TUTORIAL_FALLBACK
    else:
        text = _TUTORIAL_FALLBACK
    return _ok(text)


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------
@router.post("/wallet/recharge")
async def wallet_recharge(
    payload: RechargeInput,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    store = get_portal_store()
    entry = store.add_fund_entry(user["id"], action_type=1, amount=payload.amount, source="")
    new_balance = float(user.get("balance") or 0.0) + float(payload.amount)
    store.update_user(user["id"], balance=new_balance)
    return _ok(entry)


@router.post("/wallet/withdraw")
async def wallet_withdraw(
    payload: WithdrawInput,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    current = float(user.get("balance") or 0.0)
    if payload.amount > current:
        return _err("insufficient balance", code=1, status_code=200)
    store = get_portal_store()
    entry = store.add_fund_entry(
        user["id"],
        action_type=3,
        amount=-float(payload.amount),
        source=payload.address,
    )
    store.update_user(user["id"], balance=current - float(payload.amount))
    return _ok(entry)


@router.get("/wallet/login-history")
async def wallet_login_history(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    history = get_portal_store().list_login_history(user["id"])
    if not history:
        # Provide stable mock data so the UI always has something to show
        # on a fresh account. Not persisted.
        history = [
            {"ip": "127.0.0.1", "location": "Localhost", "timestamp": 0},
        ]
    return _ok(history)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
class ForgotSendCodeInput(BaseModel):
    email: str


class ForgotResetInput(BaseModel):
    email: str
    code: str
    newPassword: str


@router.post("/auth/forgot-password/send-code")
async def forgot_send_code(payload: ForgotSendCodeInput) -> Any:
    """Public: send a 6-digit reset code to the operator-visible code log.

    Mirrors the dev-mode pattern of /security/send-code: the code is
    written to runtime/portal/pending_codes.json so an operator with shell
    access can read it. In production this should be wired to a real
    SMS/email gateway; the current build deliberately keeps the secret
    client-side-invisible so a forgotten-password attacker without VPS
    access cannot guess the code from the response.
    """
    target = (payload.email or "").strip().lower()
    if not target or "@" not in target:
        return _err("invalid email", code=1, status_code=200)
    store = get_portal_store()
    user = store.get_user_by_email(target)
    # Always return success even if the email is not registered, so the
    # endpoint cannot be used to enumerate accounts.
    if not user:
        logger.info("forgot-password: code requested for unknown email %s", target)
        return _ok({"sent": True})
    code = f"{secrets.randbelow(1_000_000):06d}"
    store.set_pending_code(target, code)
    logger.info("forgot-password: code for %s = %s (dev-mode log)", target, code)
    return _ok({"sent": True})


@router.post("/auth/forgot-password/reset")
async def forgot_reset(payload: ForgotResetInput) -> Any:
    """Public: verify a 6-digit reset code and set a new password.

    Always clears any failed-login lockout for the identifier so the user
    can immediately sign in with the new credentials.
    """
    target = (payload.email or "").strip().lower()
    code = (payload.code or "").strip()
    new_pwd = payload.newPassword or ""
    if not target or not code:
        return _err("missing email or code", code=1, status_code=200)
    store = get_portal_store()
    user = store.get_user_by_email(target)
    if not user:
        return _err("invalid code", code=1, status_code=200)
    if not store.verify_pending_code(target, code):
        return _err("invalid or expired code", code=1, status_code=200)
    try:
        store.set_password(user["id"], new_pwd)
    except ValueError as exc:
        return _err(str(exc), code=1, status_code=200)
    # Successful reset clears the lockout window for this identifier.
    store.clear_failed_login(target)
    return _ok({"ok": True})


@router.post("/security/change-password")
async def change_password(
    payload: ChangePasswordInput,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    store = get_portal_store()
    if not store.verify_password(user, payload.oldPassword):
        return _err("old password is incorrect", code=1, status_code=200)
    try:
        store.set_password(user["id"], payload.newPassword)
    except ValueError as exc:
        return _err(str(exc), code=1, status_code=200)
    return _ok({"ok": True})


# ---------------------------------------------------------------------------
# Dashboard (Workstream A backend)
# ---------------------------------------------------------------------------
_TICKER_CACHE: Dict[str, Any] = {"value": None, "fetchedAt": 0.0}
_TICKER_LOCK = threading.Lock()
_TICKER_TTL_SECONDS = 30.0


def _fetch_json(url: str, timeout: float = 5.0) -> Optional[Any]:
    """Best-effort fetch with httpx fallback to urllib. Returns None on error."""
    try:
        import httpx  # noqa: WPS433
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.debug("ticker httpx fetch failed (%s): %s; falling back to urllib", url, exc)
    try:
        import urllib.request  # noqa: WPS433
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc2:
        logger.debug("ticker urllib fetch failed (%s): %s", url, exc2)
        return None


def _fetch_btc_ticker() -> Dict[str, Any]:
    """Aggregate BTC market widgets from a few public REST endpoints.

    Cached for 30s in-process. Each upstream call is best-effort: any failure
    leaves the corresponding field at None / 0.0 so the front-end can show a
    `—` placeholder without breaking the rest of the strip.
    """
    now = time.time()
    with _TICKER_LOCK:
        cached = _TICKER_CACHE.get("value")
        fetched_at = float(_TICKER_CACHE.get("fetchedAt") or 0.0)
        if cached and (now - fetched_at) < _TICKER_TTL_SECONDS:
            return cached

    # We use OKX + CoinGecko here because Binance fapi/api are geo-blocked
    # (HTTP 451) from many CN-region VPS hosts. OKX's public REST is open.
    #
    # 1) BTC price + 24h % — volume-weighted across OKX BTC-USDT-SWAP and
    #    Bitget BTCUSDT perp. Each venue contributes proportional to its
    #    24h base-coin volume, so the headline reflects multi-venue depth.
    okx_ticker = _fetch_json("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP") or {}
    bg_ticker = _fetch_json(
        "https://api.bitget.com/api/v2/mix/market/ticker?symbol=BTCUSDT&productType=USDT-FUTURES"
    ) or {}

    okx_px = okx_open = okx_vol_btc = 0.0
    try:
        rows = okx_ticker.get("data") or []
        if rows:
            r = rows[0]
            okx_px = float(r.get("last") or 0.0)
            okx_open = float(r.get("open24h") or 0.0)
            okx_vol_btc = float(r.get("vol24h") or 0.0)  # in BTC contracts
    except (TypeError, ValueError):
        pass

    bg_px = bg_open = bg_vol_btc = 0.0
    try:
        rows = bg_ticker.get("data") or []
        if rows:
            r = rows[0]
            bg_px = float(r.get("lastPr") or 0.0)
            # Bitget exposes 24h % directly as `change24h` (decimal). Recover open.
            ch = float(r.get("change24h") or 0.0)
            if 1 + ch > 0 and bg_px > 0:
                bg_open = bg_px / (1 + ch)
            bg_vol_btc = float(r.get("baseVolume") or 0.0)
    except (TypeError, ValueError):
        pass

    total_vol = okx_vol_btc + bg_vol_btc
    if total_vol > 0:
        price = (okx_px * okx_vol_btc + bg_px * bg_vol_btc) / total_vol
        # Volume-weighted 24h open, then derive percent.
        weighted_open = (
            (okx_open * okx_vol_btc + bg_open * bg_vol_btc) / total_vol
            if (okx_open > 0 and bg_open > 0)
            else (okx_open or bg_open)
        )
        change24h = ((price - weighted_open) / weighted_open * 100.0) if weighted_open > 0 else 0.0
    else:
        # No volume from either venue → fall back to whichever price we have.
        price = okx_px or bg_px
        weighted_open = okx_open or bg_open
        change24h = ((price - weighted_open) / weighted_open * 100.0) if weighted_open > 0 else 0.0
    volume24h = okx_vol_btc + bg_vol_btc  # combined base volume in BTC

    # 2) Funding rate + next funding time from OKX.
    okx_funding = _fetch_json(
        "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP"
    ) or {}
    funding_rate = 0.0
    next_funding_ms = 0
    try:
        rows = okx_funding.get("data") or []
        if rows:
            funding_rate = float(rows[0].get("fundingRate") or 0.0) * 100.0
            next_funding_ms = int(rows[0].get("nextFundingTime") or 0)
    except (TypeError, ValueError):
        pass

    # 3) Long/short account ratio from OKX (BTC-USDT-SWAP, 5m).
    okx_ls = _fetch_json(
        "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio"
        "?ccy=BTC&period=5m"
    )
    long_pct = short_pct = None
    try:
        rows = (okx_ls or {}).get("data") or []
        if rows:
            # Each row: [ts, ratio] where ratio = long/short
            ratio = float(rows[0][1])
            if ratio > 0:
                long_pct = round(ratio / (1 + ratio) * 100.0, 1)
                short_pct = round(1 / (1 + ratio) * 100.0, 1)
    except (TypeError, ValueError, IndexError):
        pass

    # 4) Open interest USDT — OKX + Bitget public endpoints are reachable
    #    from this VPS. Binance fapi is geo-blocked (HTTP 451) so we leave
    #    that null and the frontend renders `—`.
    oi_okx = None
    okx_oi = _fetch_json(
        "https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP"
    ) or {}
    try:
        rows = okx_oi.get("data") or []
        if rows and price > 0:
            oi_ccy = float(rows[0].get("oiCcy") or 0.0)  # in BTC
            if oi_ccy > 0:
                oi_okx = oi_ccy * price
    except (TypeError, ValueError):
        pass

    oi_bitget = None
    bitget_oi = _fetch_json(
        "https://api.bitget.com/api/v2/mix/market/open-interest"
        "?symbol=BTCUSDT&productType=USDT-FUTURES"
    ) or {}
    try:
        rows = ((bitget_oi.get("data") or {}).get("openInterestList") or [])
        if rows and price > 0:
            oi_btc = float(rows[0].get("size") or 0.0)  # in BTC
            if oi_btc > 0:
                oi_bitget = oi_btc * price
    except (TypeError, ValueError):
        pass

    # 5) USDT/USD premium — derived from OKX BTC-USDT vs OKX BTC-USDC, since
    #    USDC trades 1:1 with USD on OKX. premium > 0 means USDT > USD.
    usdt_premium = None
    okx_usdc = _fetch_json("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDC") or {}
    try:
        rows = okx_usdc.get("data") or []
        if rows:
            usdc_px = float(rows[0].get("last") or 0.0)
            if usdc_px > 0 and okx_px > 0:
                usdt_premium = (okx_px - usdc_px) / usdc_px * 100.0
    except (TypeError, ValueError):
        pass

    # 5) Fear & Greed Index from alternative.me — the canonical free feed.
    fg_payload = _fetch_json("https://api.alternative.me/fng/?limit=1") or {}
    fear_greed = 50
    fear_greed_label = "中性"
    try:
        node = (fg_payload.get("data") or [{}])[0]
        fear_greed = int(node.get("value") or 50)
        fear_greed_label = node.get("value_classification") or "中性"
    except (TypeError, ValueError, IndexError):
        pass

    # 6) Liquidation 24H + 1H + USDT premium + quarterly basis are not in any
    #    free public endpoint without a vendor key. Leave at None so the
    #    widget shows `—`. Operator can plug in CoinGlass later.
    result = {
        "btc": {
            "price": price,
            "change24h": change24h,
            "volume24h": volume24h,
        },
        "fearGreed": fear_greed,
        "fearGreedLabel": fear_greed_label,
        "longShort": (long_pct / short_pct) if (long_pct and short_pct) else 1.0,
        "longShortPct": (
            {"long": long_pct, "short": short_pct}
            if long_pct is not None
            else None
        ),
        "fundingRate": funding_rate,
        "nextFundingMs": next_funding_ms,
        "openInterest": {
            # Binance fapi is geo-blocked from this VPS (HTTP 451). OKX +
            # Bitget public endpoints work. Frontend renders `—` for null.
            "binance": None,
            "okx": oi_okx,
            "bitget": oi_bitget,
        },
        "liquidations": {
            "h24": None,
            "h1": None,
        },
        "quarterlyBasis": None,
        "usdtPremium": usdt_premium,
    }
    with _TICKER_LOCK:
        _TICKER_CACHE["value"] = result
        _TICKER_CACHE["fetchedAt"] = now
    return result


@router.get("/dashboard/stats")
async def dashboard_stats(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        # Admin-token callers come through the global middleware without a
        # portal session; aggregate against the engine anyway.
        pass
    account_count = 0
    total_equity = 0.0
    cumulative_pnl = 0.0
    daily_pnl = 0.0
    try:
        from ...executors.binance import load_trade_config
        cfg = load_trade_config()
        account_count = sum(1 for a in cfg.accounts if a.enabled)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("dashboard_stats: load_trade_config failed: %s", exc)
    try:
        from ...services import state as _state_module
        # Best-effort: AppState exposes events; equity is gathered live in
        # /api/account-summary. We avoid awaiting that here to keep this
        # endpoint cheap; a future task will write equity snapshots.
        events = getattr(getattr(_state_module, "AppState", None), "events", None)
        if events:
            pass
    except Exception:
        pass
    return _ok({
        "totalEquity": float(total_equity),
        "accountCount": int(account_count),
        "cumulativePnl": float(cumulative_pnl),
        "dailyPnl": float(daily_pnl),
    })


@router.get("/dashboard/equity-curve")
async def dashboard_equity_curve(
    days: int = Query(default=30, ge=1, le=365),
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    """Return [{ts, equity}] of length `days`.

    Reads from runtime/portal/equity_snapshots/<user_id>.json if present,
    otherwise generates a flat zero-line series with one point per day.
    The snapshot writer is a future task.
    """
    user = _resolve_user(authorization, portal_session)
    user_id = user["id"] if user else "anonymous"
    snapshot_path = EQUITY_SNAPSHOT_DIR / f"{user_id}.json"
    if snapshot_path.is_file():
        try:
            data = json.loads(snapshot_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return _ok(data[-int(days):])
        except (OSError, json.JSONDecodeError):
            pass
    now_ms = int(time.time() * 1000)
    one_day = 86_400_000
    series = [
        {"ts": now_ms - (days - 1 - i) * one_day, "equity": 0.0}
        for i in range(int(days))
    ]
    return _ok(series)


@router.get("/dashboard/news")
async def dashboard_news(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    return _ok(get_portal_store().list_news())


def _signal_visible_to(user: Optional[Dict[str, Any]], badge: str) -> bool:
    """Filter rule for the public signal feed.

    Admins see every signal (admin-injected + auto-poller). Regular users
    only see auto-poller signals so they don't observe operator activity
    in the audit feed.
    """
    if badge != "admin":
        return True
    return _is_admin(user)


@router.get("/dashboard/signals/stream")
async def dashboard_signals_stream(
    request: Request,
    token: str = Query(default=""),
) -> Any:
    """Server-Sent Events stream of new signals for any logged-in portal user.

    Auth: portal session token via `?token=...` (EventSource cannot send
    Authorization headers). Each event has the same trimmed shape as
    /dashboard/recent-signals. Admin-tagged events are filtered for non-admins.
    """
    from fastapi.responses import StreamingResponse  # local import
    import asyncio  # noqa: WPS433

    store = get_portal_store()
    user = store.get_session_user(token) if token else None
    if not user:
        return _err("unauthorized", code=1, status_code=401)
    user_is_admin = _is_admin(user)

    try:
        from ...api.main import state as engine_state  # type: ignore
    except Exception:  # pragma: no cover
        return _err("engine not initialised", code=1, status_code=503)

    queue = engine_state.subscribe_signals()
    keepalive_s = 30.0

    def _trim(evt: Any) -> Dict[str, Any]:
        note = getattr(evt, "note", None) or ""
        return {
            "ts": getattr(evt, "created_at", None),
            "symbol": getattr(evt, "symbol", ""),
            "action": getattr(evt, "action", ""),
            "side": getattr(evt, "side", ""),
            "positionSide": getattr(evt, "position_side", ""),
            "qty": getattr(evt, "executed_qty", 0.0),
            "price": getattr(evt, "avg_price", 0.0),
            "leader": getattr(evt, "leader_id", None) or getattr(evt, "portfolio_id", "") or "",
            "badge": "admin" if note.startswith("[admin:") else "auto",
            "id": getattr(evt, "event_id", ""),
        }

    async def event_generator():
        yield b": connected\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=keepalive_s)
                except asyncio.TimeoutError:
                    yield b": ping\n\n"
                    continue
                trimmed = _trim(evt)
                # Filter admin-injected events from non-admin streams.
                if not user_is_admin and trimmed.get("badge") == "admin":
                    continue
                payload = json.dumps(trimmed, default=str)
                yield f"event: signal\ndata: {payload}\n\n".encode("utf-8")
        except asyncio.CancelledError:
            raise
        finally:
            engine_state.unsubscribe_signals(queue)

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.get("/dashboard/recent-signals")
async def dashboard_recent_signals(
    limit: int = Query(default=8, ge=1, le=30),
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    """Public-facing live signal feed for the /kzt home strip.

    Visible to any logged-in portal user. Returns trimmed OrderEvent fields
    (symbol, action, side, qty, price, ts, badge) — internal IDs and
    account_id are stripped. Admin-injected events are tagged `badge: "admin"`
    via the `[admin:` prefix on note; everything else is `badge: "auto"`.
    """
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=401)
    user_is_admin = _is_admin(user)
    try:
        from ...api.main import state as engine_state  # type: ignore
    except Exception:  # pragma: no cover
        return _ok([])
    out: List[Dict[str, Any]] = []
    for evt in list(engine_state.events):
        try:
            note = evt.note or ""
            badge = "admin" if note.startswith("[admin:") else "auto"
            # Hide admin-injected events from non-admins so the feed shape
            # matches what the SSE stream will deliver after first poll.
            if not user_is_admin and badge == "admin":
                continue
            out.append(
                {
                    "id": evt.event_id,
                    "ts": evt.created_at,
                    "symbol": evt.symbol,
                    "action": evt.action,
                    "side": evt.side,
                    "positionSide": evt.position_side,
                    "qty": evt.executed_qty,
                    "price": evt.avg_price,
                    "leader": evt.leader_id or evt.portfolio_id or "",
                    "badge": badge,
                }
            )
            if len(out) >= limit:
                break
        except Exception:
            continue
    return _ok(out)


@router.get("/dashboard/ticker")
async def dashboard_ticker(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    return _ok(_fetch_btc_ticker())


# ---------------------------------------------------------------------------
# Security: phone/email change with code verification (Workstream B)
# ---------------------------------------------------------------------------
def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


@router.post("/security/send-code")
async def security_send_code(
    payload: SendCodeInput,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    channel = (payload.channel or "").strip().lower()
    target = (payload.target or "").strip()
    if channel not in {"phone", "email"} or not target:
        return _err("invalid channel or target", code=1, status_code=200)
    code = _generate_code()
    get_portal_store().set_pending_code(target, code, ttl_seconds=300)
    # Dev stub: log to stdout (no real SMS/email delivery).
    logger.info("portal verification code (dev only) channel=%s target=%s code=%s", channel, target, code)
    return _ok({"sent": True})


@router.post("/security/change-phone")
async def security_change_phone(
    payload: ChangePhoneInput,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    phone = (payload.phone or "").strip()
    if not phone:
        return _err("phone is required", code=1, status_code=200)
    store = get_portal_store()
    if not store.verify_pending_code(phone, payload.code):
        return _err("invalid or expired code", code=1, status_code=200)
    if not store.set_phone(user["id"], phone):
        return _err("update failed", code=1, status_code=200)
    updated = store.get_user_by_id(user["id"]) or user
    return _ok(_public_user(updated))


@router.post("/security/change-email")
async def security_change_email(
    payload: ChangeEmailInput,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        return _err("invalid email", code=1, status_code=200)
    store = get_portal_store()
    if not store.verify_pending_code(email, payload.code):
        return _err("invalid or expired code", code=1, status_code=200)
    if not store.set_email(user["id"], email):
        return _err("email already in use or update failed", code=1, status_code=200)
    updated = store.get_user_by_id(user["id"]) or user
    return _ok(_public_user(updated))


# ---------------------------------------------------------------------------
# Withdraw addresses (Workstream B)
# ---------------------------------------------------------------------------
@router.get("/account/withdraw-addresses")
async def list_withdraw_addresses(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    return _ok(get_portal_store().list_withdraw_addresses(user["id"]))


@router.post("/account/withdraw-addresses")
async def add_withdraw_address(
    payload: WithdrawAddressInput,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    try:
        record = get_portal_store().add_withdraw_address(
            user["id"],
            payload.alias or "",
            payload.value,
            payload.network or "TRC20",
        )
    except ValueError as exc:
        return _err(str(exc), code=1, status_code=200)
    return _ok(record)


@router.delete("/account/withdraw-addresses/{addr_id}")
async def delete_withdraw_address(
    addr_id: str,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    ok = get_portal_store().remove_withdraw_address(user["id"], addr_id)
    if not ok:
        return _err("address not found", code=1, status_code=200)
    return _ok({"ok": True})


# ---------------------------------------------------------------------------
# Business <-> TradingAccount integration (Workstream C)
# ---------------------------------------------------------------------------
@router.post("/account/businesses/{biz_id}/bind-api-key")
async def bind_business_api_key(
    biz_id: str,
    payload: BindApiKeyInput,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    store = get_portal_store()
    biz = store.find_business(user["id"], biz_id)
    if not biz:
        return _err("business not found", code=1, status_code=404)
    exchange = (payload.exchange or "binance").strip().lower()
    if exchange not in {"binance", "okx"}:
        return _err("unsupported exchange", code=1, status_code=200)
    api_key = (payload.apiKey or "").strip()
    api_secret = (payload.apiSecret or "").strip()
    if not api_key or not api_secret:
        return _err("apiKey and apiSecret required", code=1, status_code=200)

    from ...domain.trade import TradingAccount
    from ...executors.binance import load_trade_config, save_trade_config

    new_account_id = secrets.token_hex(8)
    # Build a TradingAccount with sane defaults; base_url is left blank so
    # the executor can fill in the per-exchange default at runtime.
    new_account = TradingAccount(
        account_id=new_account_id,
        name=(payload.alias or "GalaxyAccount").strip() or "GalaxyAccount",
        exchange=exchange,
        enabled=False,
        base_url="",
        api_key=api_key,
        api_secret=api_secret,
        passphrase=(payload.passphrase or "").strip(),
    )
    cfg = load_trade_config()
    cfg.accounts.append(new_account)
    save_trade_config(cfg)

    updated = store.update_business(
        user["id"],
        biz_id,
        tradeAccountId=new_account_id,
        bindingExchange=exchange,
        bindingUid=api_key[:8],
    )
    return _ok(updated or biz)


def _mask_key(s: Optional[str]) -> str:
    if not s or len(s) < 8:
        return "******"
    return s[:4] + "******" + s[-4:]


@router.get("/account/{biz_id}/detail")
async def account_detail(
    biz_id: str,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    store = get_portal_store()
    biz = store.find_business(user["id"], biz_id)
    if not biz:
        return _err("business not found", code=2, status_code=200)

    # Resolve api/secret/exchange/active from the bound TradingAccount when present.
    api_key = biz.get("apiKey") or ""
    api_secret = ""
    exchange = biz.get("bindingExchange") or ""
    active = False
    account_id = biz.get("tradeAccountId")
    if account_id:
        try:
            from ...executors.binance import load_trade_config

            cfg = load_trade_config()
            for acct in cfg.accounts:
                if acct.account_id == account_id:
                    api_key = getattr(acct, "api_key", "") or api_key
                    api_secret = getattr(acct, "api_secret", "") or ""
                    exchange = getattr(acct, "exchange", "") or exchange
                    active = bool(getattr(acct, "enabled", False))
                    break
        except Exception:  # pragma: no cover - best effort
            pass

    expire_ms = int(biz.get("expirationTimestamp") or 0)
    now_ms = int(time.time() * 1000)
    remaining_days: Optional[int] = (
        max(0, (expire_ms - now_ms) // 86_400_000) if expire_ms else None
    )

    snapshot_path = EQUITY_SNAPSHOT_DIR / f"{user['id']}.json"
    equity_30d: list = []
    if snapshot_path.is_file():
        try:
            data = json.loads(snapshot_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                equity_30d = data[-30:]
        except (OSError, json.JSONDecodeError):
            pass

    return _ok({
        "biz_id": biz_id,
        "alias": biz.get("alias") or "账户",
        "exchange": exchange,
        "uid": biz.get("bindingUid"),
        "ip_whitelist": biz.get("ipWhitelist") or [],
        "api_key_masked": _mask_key(api_key),
        "secret_key_masked": _mask_key(api_secret),
        "total_assets": biz.get("totalAssets"),
        "futures_balance": biz.get("futuresBalance"),
        "active": active,
        "remaining_days": remaining_days,
        "equity_30d": equity_30d,
    })


def _toggle_business_account(user_id: str, biz_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
    store = get_portal_store()
    biz = store.find_business(user_id, biz_id)
    if not biz:
        return None
    account_id = biz.get("tradeAccountId")
    if not account_id:
        return biz
    from ...executors.binance import load_trade_config, save_trade_config
    cfg = load_trade_config()
    mutated = False
    for acct in cfg.accounts:
        if acct.account_id == account_id:
            acct.enabled = enabled
            mutated = True
            break
    if mutated:
        if enabled:
            cfg.enabled = True
        save_trade_config(cfg)
    return biz


@router.post("/account/businesses/{biz_id}/activate")
async def activate_business(
    biz_id: str,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    biz = _toggle_business_account(user["id"], biz_id, enabled=True)
    if not biz:
        return _err("business not found", code=1, status_code=404)
    return _ok(biz)


@router.post("/account/businesses/{biz_id}/deactivate")
async def deactivate_business(
    biz_id: str,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    biz = _toggle_business_account(user["id"], biz_id, enabled=False)
    if not biz:
        return _err("business not found", code=1, status_code=404)
    return _ok(biz)


@router.delete("/account/businesses/{biz_id}")
async def archive_business(
    biz_id: str,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    # Disable linked TradingAccount first so the engine stops mirroring.
    _toggle_business_account(user["id"], biz_id, enabled=False)
    store = get_portal_store()
    if not store.delete_business(user["id"], biz_id):
        return _err("business not found", code=1, status_code=404)
    return _ok({"ok": True})


# ---------------------------------------------------------------------------
# Mall purchase (Workstream C)
# ---------------------------------------------------------------------------
@router.post("/mall/purchase")
async def mall_purchase(
    payload: MallPurchaseInput,
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    store = get_portal_store()
    plans = store.list_plans()
    plan = plans.get(payload.planId)
    if not plan:
        return _err("plan not found", code=1, status_code=400)
    price = float(plan.get("price") or 0.0)
    days = int(plan.get("days") or 0)
    if price <= 0 or days <= 0:
        return _err("invalid plan configuration", code=1, status_code=400)
    fund = store.debit_balance(user["id"], price, source=f"mall:{payload.planId}")
    if fund is None:
        return _err("insufficient balance", code=1, status_code=400)
    expiration_ts = int(time.time() * 1000) + days * 86_400_000
    biz = store.add_business(
        user["id"],
        {
            "type": 1,
            "expirationTimestamp": expiration_ts,
            "alias": (payload.alias or plan.get("name") or payload.planId),
        },
    )
    return _ok(
        {
            "businessId": biz["id"],
            "expirationTimestamp": expiration_ts,
            "fund": fund,
        }
    )


# ---------------------------------------------------------------------------
# Console token bridge (Workstream A.4)
# ---------------------------------------------------------------------------
@router.post("/auth/console-token")
async def console_token(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    """Return the admin API_TOKEN to authed portal users with an active plan.

    This deliberately scopes admin-token visibility to paying users on a
    self-hosted single-operator deployment. A finer-grained per-user proxy
    is the natural follow-up if multi-tenant isolation becomes a goal.
    """
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=200)
    store = get_portal_store()
    effective = store.list_businesses(user["id"], effective_only=True)
    if not effective:
        return _err("未购买套餐", code=1, status_code=403)
    try:
        from ...api.main import API_TOKEN  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("console_token: failed to load API_TOKEN: %s", exc)
        return _err("admin token not available", code=1, status_code=503)
    return _ok(
        {
            "token": API_TOKEN,
            "expiresAt": int(time.time() * 1000) + 3600 * 1000,
        }
    )


# ---------------------------------------------------------------------------
# Admin control panel — admin-only routes for managing signals/users/businesses
# ---------------------------------------------------------------------------
# Role model: a user is an admin when authority >= 9. The demo user starts at
# authority=1; bootstrap an admin via the runtime/portal/admin_emails.txt file
# (one email per line). Any user listed there is auto-promoted on next login.
# ---------------------------------------------------------------------------
ADMIN_AUTHORITY = 9


def _is_admin(user: Optional[Dict[str, Any]]) -> bool:
    if not user:
        return False
    try:
        return int(user.get("authority", 1)) >= ADMIN_AUTHORITY
    except (TypeError, ValueError):
        return False


def _require_admin(
    authorization: Optional[str],
    portal_session: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Return the admin user or None — caller should _err on None.

    Legacy helper kept for routes that don't use Depends. New routes should
    take `admin: Dict = Depends(_admin_dep)` instead so the 403 fires before
    pydantic body validation (otherwise unauthorized callers can leak request
    schema via 422 errors).
    """
    user = _resolve_user(authorization, portal_session)
    if not _is_admin(user):
        return None
    return user


def _admin_dep(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Dict[str, Any]:
    """FastAPI dependency: 403 before body validation if caller is not admin.

    Returns the admin user record on success. Use this instead of calling
    `_require_admin` inside the handler so request-body schemas don't leak
    via 422 to unauthorized callers.
    """
    user = _resolve_user(authorization, portal_session)
    if not _is_admin(user):
        raise HTTPException(
            status_code=403,
            detail={"data": None, "code": 1, "message": "admin only"},
        )
    return user


class AdminSignalIn(BaseModel):
    leader_id: str
    portfolio_id: Optional[str] = None
    exchange: Optional[str] = "binance"
    symbol: str
    side: str  # BUY or SELL
    position_side: str = "BOTH"  # LONG / SHORT / BOTH
    action: str  # open / add / reduce / close
    executed_qty: float
    avg_price: float
    follower_leverage: Optional[float] = None
    note: Optional[str] = None


@router.post("/admin/signals")
async def admin_publish_signal(
    payload: AdminSignalIn,
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    """Publish a synthetic signal into the engine's event stream.

    Admin-only. The injected event flows through the same SSE/dashboard
    pipeline as poller-detected signals, but `note` is prefixed with
    ``[admin:{userName}]`` so audit trails can distinguish manual entries.
    """
    action = (payload.action or "").lower()
    if action not in {"open", "add", "reduce", "close"}:
        return _err("action must be one of: open, add, reduce, close", code=1, status_code=400)

    side = (payload.side or "").upper()
    if side not in {"BUY", "SELL"}:
        return _err("side must be BUY or SELL", code=1, status_code=400)

    position_side = (payload.position_side or "BOTH").upper()
    if position_side not in {"LONG", "SHORT", "BOTH"}:
        return _err("position_side must be LONG / SHORT / BOTH", code=1, status_code=400)

    try:
        from ...domain.events import OrderEvent
        from ...api.main import state as engine_state  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("admin_publish_signal: import failed: %s", exc)
        return _err("engine not initialised", code=1, status_code=503)

    now = int(time.time() * 1000)
    portfolio_id = payload.portfolio_id or payload.leader_id
    qty = float(payload.executed_qty)
    price = float(payload.avg_price)
    note_user = admin.get("userName") or admin.get("email") or "admin"
    note_full = f"[admin:{note_user}]" + (f" {payload.note}" if payload.note else "")

    event_id = secrets.token_hex(10)
    event = OrderEvent(
        event_id=event_id,
        portfolio_id=portfolio_id,
        exchange=payload.exchange,
        leader_id=payload.leader_id,
        account_id=None,
        trade_account_id=None,
        order_id=f"adm-{event_id[:12]}",
        trade_id=f"adm-{event_id[:12]}",
        action=action,
        symbol=payload.symbol.upper(),
        position_side=position_side,
        side=side,
        executed_qty=qty,
        avg_price=price,
        order_time=now,
        order_update_time=now,
        leader_delta=qty if action in {"open", "add"} else -qty,
        scale=1.0,
        follower_qty=qty,
        reduce_only=action in {"reduce", "close"},
        order_value=qty * price,
        follower_leverage=payload.follower_leverage,
        status="queued",
        note=note_full,
        created_at=now,
    )

    try:
        engine_state.record_event(event)
    except Exception as exc:
        logger.exception("admin_publish_signal: record_event failed")
        return _err(f"engine rejected event: {exc}", code=1, status_code=500)

    return _ok(
        {
            "event_id": event_id,
            "portfolio_id": portfolio_id,
            "symbol": event.symbol,
            "action": event.action,
            "side": event.side,
            "executed_qty": event.executed_qty,
            "avg_price": event.avg_price,
            "created_at": event.created_at,
            "publishedBy": note_user,
        }
    )


@router.get("/admin/users")
async def admin_list_users(
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    """List every portal user with summary stats. Admin-only."""
    store = get_portal_store()
    users = store.list_users()
    by_id = {u.get("id"): u for u in users}
    out: List[Dict[str, Any]] = []
    for u in users:
        uid = u.get("id")
        biz_total = len(store.list_businesses(uid))
        biz_active = len(store.list_businesses(uid, effective_only=True))
        invited_by = u.get("invitedBy")
        inviter = by_id.get(invited_by) if invited_by else None
        out.append(
            {
                "id": uid,
                "email": u.get("email"),
                "userName": u.get("userName"),
                "balance": u.get("balance", 0.0),
                "authority": u.get("authority", 1),
                "invitationCode": u.get("invitationCode"),
                "phoneNumber": u.get("phoneNumber"),
                "createdAt": u.get("createdAt"),
                "businessTotal": biz_total,
                "businessActive": biz_active,
                "emailVerified": bool(u.get("emailVerified")),
                "deleted": bool(u.get("deleted")),
                "deletedAt": u.get("deletedAt"),
                "invitedByEmail": inviter.get("email") if inviter else None,
                "invitedByCode": inviter.get("invitationCode") if inviter else None,
                "inviteeCount": sum(1 for x in users if x.get("invitedBy") == uid),
            }
        )
    return _ok(out)


class AdminAuthorityIn(BaseModel):
    authority: int = Field(ge=1, le=99)


@router.post("/admin/users/{user_id}/authority")
async def admin_set_authority(
    user_id: str,
    payload: AdminAuthorityIn,
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    """Promote/demote a user. Admin-only. Self-demote is blocked."""
    if user_id == admin.get("id") and payload.authority < ADMIN_AUTHORITY:
        return _err("cannot demote yourself", code=1, status_code=400)
    store = get_portal_store()
    target = store.get_user_by_id(user_id)
    if not target:
        return _err("user not found", code=1, status_code=404)
    updated = store.update_user(user_id, authority=int(payload.authority))
    return _ok({"id": user_id, "authority": updated.get("authority") if updated else None})


class AdminAdjustBalanceIn(BaseModel):
    amount: float
    reason: Optional[str] = None


@router.post("/admin/users/{user_id}/adjust-balance")
async def admin_adjust_balance(
    user_id: str,
    payload: AdminAdjustBalanceIn,
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    """Credit (positive) or debit (negative) a user's balance. Admin-only.

    Writes a funds-ledger entry with actionType=1 (credit) or 2 (debit) and
    the source string ``admin:{adminUserName}:{reason}`` so audits can trace
    every adjustment back to the operator.
    """
    store = get_portal_store()
    target = store.get_user_by_id(user_id)
    if not target:
        return _err("user not found", code=1, status_code=404)
    amount = float(payload.amount)
    if amount == 0:
        return _err("amount must be non-zero", code=1, status_code=400)
    new_balance = float(target.get("balance", 0.0)) + amount
    if new_balance < 0:
        return _err("resulting balance would be negative", code=1, status_code=400)
    store.update_user(user_id, balance=new_balance)
    action_type = 1 if amount > 0 else 2
    reason = (payload.reason or "manual").strip()[:80]
    source = f"admin:{admin.get('userName') or 'admin'}:{reason}"
    fund = store.add_fund_entry(user_id, action_type=action_type, amount=amount, source=source)
    return _ok({"id": user_id, "newBalance": new_balance, "fund": fund})


@router.get("/admin/businesses")
async def admin_list_businesses(
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    """Return every business across every user (operational view). Admin-only."""
    store = get_portal_store()
    out: List[Dict[str, Any]] = []
    for u in store.list_users():
        uid = u.get("id")
        for b in store.list_businesses(uid):
            out.append({**b, "userId": uid, "userEmail": u.get("email")})
    out.sort(key=lambda b: b.get("createTimestamp", 0), reverse=True)
    return _ok(out)


@router.get("/admin/signals/recent")
async def admin_recent_signals(
    limit: int = Query(default=50, ge=1, le=500),
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    """Recent signals (read-only mirror of state.events). Admin-only.

    Distinct from /api/signals which uses the admin Bearer token; this one
    uses the portal session, so admins can view signals from /admin without
    minting an admin token.
    """
    try:
        from ...api.main import state as engine_state  # type: ignore
    except Exception:  # pragma: no cover
        return _ok([])
    out: List[Dict[str, Any]] = []
    for evt in list(engine_state.events)[:limit]:
        # Return raw OrderEvent shape so the admin view keeps every field
        # (note, mirror_status, executed_qty, avg_price). serialize_signal()
        # strips note + uses different key names; we want full audit detail.
        try:
            out.append(evt.model_dump())
        except Exception:
            continue
    return _ok(out)


@router.get("/admin/telegram/config")
async def admin_telegram_get(
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    from ...services.telegram_notifier import get_notifier
    return _ok(get_notifier().get_config())


class AdminTelegramConfigIn(BaseModel):
    enabled: Optional[bool] = None
    botToken: Optional[str] = None
    chatIds: Optional[List[str]] = None
    notifyAdminSignals: Optional[bool] = None
    notifyAutoSignals: Optional[bool] = None
    includePnl: Optional[bool] = None
    dingtalkWebhook: Optional[str] = None
    feishuWebhook: Optional[str] = None
    discordWebhook: Optional[str] = None
    language: Optional[str] = None
    batchWindowSec: Optional[int] = None
    consoleBaseUrl: Optional[str] = None


@router.post("/admin/telegram/config")
async def admin_telegram_set(
    payload: AdminTelegramConfigIn,
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    from ...services.telegram_notifier import get_notifier
    patch = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    return _ok(get_notifier().update_config(patch))


class AdminTelegramTestIn(BaseModel):
    chatId: Optional[str] = None


@router.post("/admin/telegram/test")
async def admin_telegram_test(
    payload: AdminTelegramTestIn,
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    from ...services.telegram_notifier import get_notifier
    res = await get_notifier().send_test(payload.chatId)
    return _ok(res)


@router.get("/admin/whoami")
async def admin_whoami(
    authorization: Optional[str] = Header(default=None),
    portal_session: Optional[str] = Cookie(default=None),
) -> Any:
    """Lightweight check that the caller is an admin (used by /admin page guard)."""
    user = _resolve_user(authorization, portal_session)
    if not user:
        return _err("not logged in", code=1, status_code=401)
    return _ok(
        {
            "id": user.get("id"),
            "email": user.get("email"),
            "userName": user.get("userName"),
            "authority": user.get("authority", 1),
            "isAdmin": _is_admin(user),
        }
    )


# ---------------------------------------------------------------------------
# First-run admin setup + security-question password recovery
# ---------------------------------------------------------------------------
#
# Goals:
#   - On a fresh install the operator should be able to set their own
#     admin username/password through the UI, instead of editing
#     runtime/portal/admin_seed.json.
#   - If they later forget the password, they can recover it by answering
#     the 3 security questions they configured during setup.
#
# Public surface (callable without a session):
#   GET  /admin/setup/status        — am I in first-run mode?
#   POST /admin/setup/init          — only when needsSetup==true
#   GET  /admin/recover/questions   — fetch question text for an admin email
#   POST /admin/recover/reset       — verify answers + set new password
#
# Authenticated surface (admin Bearer):
#   GET  /admin/security-questions/me — show the questions I have set
#   POST /admin/security-questions    — replace my own questions

class AdminSetupQuestion(BaseModel):
    question: str
    answer: str


class AdminSetupInitIn(BaseModel):
    userName: str
    email: str
    password: str
    questions: List[AdminSetupQuestion] = Field(min_length=3, max_length=8)


class AdminRecoverResetIn(BaseModel):
    email: str
    answers: List[str]
    newPassword: str


class AdminUpdateQuestionsIn(BaseModel):
    questions: List[AdminSetupQuestion] = Field(min_length=3, max_length=8)


@router.get("/admin/setup/status")
async def admin_setup_status() -> Any:
    """Public probe: should the UI redirect to /admin-setup?

    The bootstrap script in /admin (and /login) reads this on page load to
    decide whether to send the operator into the first-run wizard.
    """
    store = get_portal_store()
    return _ok(
        {
            "needsSetup": store.is_admin_setup_needed(),
        }
    )


@router.post("/admin/setup/init")
async def admin_setup_init(payload: AdminSetupInitIn, request: Request) -> Any:
    """First-run wizard endpoint. Idempotent-refused once setup is done."""
    store = get_portal_store()
    if not store.is_admin_setup_needed():
        return _err(
            "admin setup is already complete — use the recover flow instead",
            code=1,
            status_code=409,
        )
    try:
        user = store.complete_admin_setup(
            userName=payload.userName,
            email=payload.email,
            password=payload.password,
            questions=[q.model_dump() for q in payload.questions],
        )
    except ValueError as exc:
        return _err(str(exc), code=1, status_code=400)

    # Drop the operator straight into a logged-in admin session so they
    # can finish the first-run flow without an extra login round-trip.
    token = store.create_session(user["id"])
    logger.info(
        "admin setup completed for %s (ip=%s)",
        user.get("email"),
        _client_ip(request),
    )
    return _ok(
        {
            "token": token,
            "user": _public_user(user),
        }
    )


@router.get("/admin/recover/questions")
async def admin_recover_questions(email: str = Query(..., min_length=3)) -> Any:
    """Return the question prompts (no answers) for an admin email.

    Returns 404 for non-admins or unknown emails so attackers can't use
    this to enumerate which user accounts exist (vs. just admins).
    """
    store = get_portal_store()
    items = store.get_security_questions_for_email(email)
    if not items:
        return _err("no recovery questions configured for that email", code=1, status_code=404)
    return _ok({"questions": items})


@router.post("/admin/recover/reset")
async def admin_recover_reset(payload: AdminRecoverResetIn, request: Request) -> Any:
    """Verify all 3 answers, then set a new password.

    Throttled by the same failed-login backoff used by /auth/login so a
    misconfigured recovery flow can't be brute-forced unattended.
    """
    if not payload.newPassword or len(payload.newPassword) < 6:
        return _err("password too short (min 6)", code=1, status_code=400)

    store = get_portal_store()
    ip = _client_ip(request)
    lock_key = f"recover:{(payload.email or '').strip().lower()}:{ip}"
    if store.is_locked(lock_key):
        return _err(
            "too many failed attempts — try again in 30 minutes",
            code=1,
            status_code=429,
        )

    user_id = store.verify_security_answers(payload.email, payload.answers)
    if not user_id:
        attempt = store.record_failed_login(lock_key)
        msg = "answers do not match"
        if attempt.get("lockedSeconds"):
            msg = f"too many failed attempts — locked for {attempt['lockedSeconds']}s"
        elif attempt.get("remaining", 0) > 0:
            msg = f"answers do not match ({attempt['remaining']} attempts remaining)"
        return _err(msg, code=1, status_code=403)

    try:
        store.set_password(user_id, payload.newPassword)
    except ValueError as exc:
        return _err(str(exc), code=1, status_code=400)

    store.clear_failed_login(lock_key)
    logger.info("admin password recovered via questions for %s (ip=%s)", payload.email, ip)
    return _ok({"ok": True})


@router.get("/admin/security-questions/me")
async def admin_security_questions_me(
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    """Show the *prompts* configured by the current admin (no answers)."""
    items = admin.get("securityQuestions") or []
    return _ok(
        {
            "questions": [
                {"question": item.get("question", "")} for item in items
            ],
            "updatedAt": admin.get("securityQuestionsUpdatedAt"),
        }
    )


@router.post("/admin/security-questions")
async def admin_security_questions_set(
    payload: AdminUpdateQuestionsIn,
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    store = get_portal_store()
    try:
        store.set_security_questions(
            admin["id"],
            [q.model_dump() for q in payload.questions],
        )
    except ValueError as exc:
        return _err(str(exc), code=1, status_code=400)
    return _ok({"updated": True, "count": len(payload.questions)})


# ---------------------------------------------------------------------------
# One-click Binance bind wizard
# ---------------------------------------------------------------------------
#
# The flow:
#   1. Admin clicks 「生成一次性令牌」 in the /admin Binance tab → POST
#      /admin/binance/bind-token returns a 10-min one-shot token.
#   2. Admin pastes a cURL command (DevTools → copy as cURL), a JSON cookie
#      array (DevTools → Application → Cookies → export), or a raw HTTP
#      header dump into the textarea, hits 提交.
#   3. Frontend sends `{token, raw}` to POST /portal/binance/cookies (a
#      *public* route — the token is the auth). The route auto-detects the
#      input shape and reuses `parse_cookie_payload` from main.py.
#   4. Cookies + headers are written via state.update_config → poller picks
#      up the new credentials on its next loop. Status card polls
#      /admin/binance/status every 3s and turns green.

_CURL_HEADER_RE_DOUBLE = None  # lazy-compiled


def _curl_command_to_raw_headers(text: str) -> Optional[str]:
    """If `text` looks like a `curl` command, extract its -H headers and
    rebuild a header-block string the existing parser understands.

    Returns None if the input is not a cURL command (let the caller fall
    through to the JSON / raw-header parser instead).
    """
    import re as _re
    stripped = (text or "").strip()
    if not stripped:
        return None
    # We tolerate the line-continuation backslashes and either single- or
    # double-quoted -H values that browsers emit.
    if "curl " not in stripped and not stripped.lstrip().startswith("curl"):
        return None
    pattern = _re.compile(
        r"-H\s+(?:'([^']+)'|\"((?:[^\"\\]|\\.)*)\")",
        _re.MULTILINE,
    )
    parts: List[str] = []
    for match in pattern.finditer(stripped):
        header = match.group(1) or match.group(2) or ""
        # Decode the simple `\"` escape used in `-H "name: \"value\""` form.
        header = header.replace('\\"', '"').strip()
        if header:
            parts.append(header)
    if not parts:
        return None
    return "\n".join(parts)


def _binance_session_status() -> Dict[str, Any]:
    """Snapshot of the live BinanceSession for the status card.

    Returns hasCookies / cookieCount / lastUpdated (mtime) / connected /
    headerStatus. Never throws — degrades to safe defaults if the engine
    state isn't ready yet.
    """
    from .. import main as api_main  # lazy: main imports this router
    from ..main import resolve_cookie_path, state, config_store

    cookie_path_value = state.config.cookie_path or "cookies.json"
    try:
        path = resolve_cookie_path(cookie_path_value)
    except Exception:
        path = None

    has_cookies = bool(path and path.exists())
    cookie_count = 0
    last_updated = 0
    if has_cookies:
        try:
            raw = path.read_text(encoding="utf-8-sig")
            data = json.loads(raw)
            if isinstance(data, list):
                cookie_count = len(data)
            elif isinstance(data, dict) and isinstance(data.get("cookies"), list):
                cookie_count = len(data["cookies"])
        except Exception:
            cookie_count = 0
        try:
            last_updated = int(path.stat().st_mtime * 1000)
        except Exception:
            last_updated = 0

    header_status = None
    leader = getattr(state, "leader", None)
    if leader is not None and hasattr(leader, "header_status"):
        try:
            header_status = leader.header_status()
        except Exception:
            header_status = None
    connected = bool(getattr(leader, "connected", False))
    last_error = getattr(leader, "last_error", None)
    return {
        "hasCookies": has_cookies,
        "cookieCount": cookie_count,
        "lastUpdated": last_updated,
        "cookiePath": cookie_path_value,
        "authMode": state.config.auth_mode,
        "connected": connected,
        "lastError": last_error,
        "headerStatus": header_status,
    }


@router.post("/admin/binance/bind-token")
async def admin_binance_bind_token(
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    """Mint a 10-minute one-shot token used by the bind wizard.

    The token is stored under key ``binance_bind:<token>`` so it lives in
    the same pending-code namespace we already use for email codes — that
    means it auto-expires and one-shot-consumes via the existing helpers.
    """
    token = secrets.token_urlsafe(24)
    ttl = 600
    entry = get_portal_store().set_pending_code(
        f"binance_bind:{token}", token, ttl_seconds=ttl
    )
    return _ok(
        {
            "token": token,
            "expiresAt": entry.get("expiresAt"),
            "ttlSeconds": ttl,
        }
    )


class BinanceCookiesIn(BaseModel):
    token: str
    raw: Optional[str] = None
    cookies: Optional[List[Dict[str, Any]]] = None


@router.post("/binance/cookies")
async def portal_binance_cookies(payload: BinanceCookiesIn, request: Request) -> Any:
    """Public route — auth is the one-shot bind token (not a session).

    Accepts ``raw`` (cURL command / JSON / raw HTTP headers) or a structured
    ``cookies`` array. Auto-detects which form the user pasted and delegates
    to ``parse_cookie_payload`` from main.py.
    """
    token = (payload.token or "").strip()
    if not token:
        return _err("token required", code=1, status_code=400)

    store = get_portal_store()
    if not store.verify_pending_code(f"binance_bind:{token}", token):
        return _err("token invalid or expired", code=1, status_code=403)

    cookies: List[Dict[str, str]]
    headers: Dict[str, str] = {}
    cookie_payload = payload.cookies
    raw_text = (payload.raw or "").strip()

    if cookie_payload:
        cookies = [
            {
                "name": str(c.get("name") or "").strip(),
                "value": str(c.get("value") or "").strip(),
                "domain": str(c.get("domain") or ".binance.com"),
            }
            for c in cookie_payload
            if c.get("name") and c.get("value") is not None
        ]
    elif raw_text:
        from ..main import parse_cookie_payload  # lazy: avoid circular import
        curl_rebuilt = _curl_command_to_raw_headers(raw_text)
        target = curl_rebuilt if curl_rebuilt else raw_text
        cookies, headers = parse_cookie_payload(target)
    else:
        return _err("raw or cookies is required", code=1, status_code=400)

    if not cookies:
        return _err(
            "no cookies recognised — paste DevTools cURL or cookie JSON",
            code=1,
            status_code=400,
        )

    from ..main import resolve_cookie_path, state
    from ...domain.config import ConfigPatch

    cookie_path_value = state.config.cookie_path or "cookies.json"
    cookie_path = resolve_cookie_path(cookie_path_value)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(
        json.dumps(cookies, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    merged_headers = dict(state.config.leader_headers or {})
    for key, value in (headers or {}).items():
        if value:
            merged_headers[key] = value

    await state.update_config(
        ConfigPatch(
            auth_mode="cookie",
            cookie_path=cookie_path_value,
            leader_headers=merged_headers or None,
        )
    )

    # Best-effort: poke the leader session so the status card flips to
    # connected immediately instead of waiting for the next poll tick.
    leader = getattr(state, "leader", None)
    connect_ok: Optional[bool] = None
    if leader is not None and hasattr(leader, "connect"):
        try:
            connect_ok = await leader.connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning("post-bind leader.connect() failed: %s", exc)

    return _ok(
        {
            "cookieCount": len(cookies),
            "headerCount": len(headers or {}),
            "cookiePath": cookie_path_value,
            "connected": bool(connect_ok),
        }
    )


@router.get("/admin/binance/status")
async def admin_binance_status(
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    return _ok(_binance_session_status())


@router.delete("/admin/binance/cookies")
async def admin_binance_clear_cookies(
    admin: Dict[str, Any] = Depends(_admin_dep),
) -> Any:
    from ..main import resolve_cookie_path, state

    cookie_path_value = state.config.cookie_path or "cookies.json"
    cookie_path = resolve_cookie_path(cookie_path_value)
    deleted = False
    if cookie_path.exists():
        try:
            cookie_path.unlink()
            deleted = True
        except Exception as exc:  # noqa: BLE001
            return _err(f"failed to delete cookies: {exc}", code=1, status_code=500)

    return _ok({"deleted": deleted, "cookiePath": cookie_path_value})


__all__ = ["router"]
