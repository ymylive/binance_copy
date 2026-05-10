"""JSON-file-backed singleton store for the portal API.

Persists everything under runtime/portal/. Every write is atomic
(write to .tmp then rename). All public methods are thread-safe via a
single re-entrant lock; portal traffic is low-volume so this is fine.

No third-party crypto dependency required: passwords are stored as
sha256(salt + password) hex with a per-user 16-byte hex salt. We expose
verify_password / hash_password helpers that accept the full record so
we can swap to a stronger KDF later without touching call sites.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..core.paths import ROOT_DIR

PORTAL_DIR = ROOT_DIR / "runtime" / "portal"

USERS_FILE = "users.json"
SESSIONS_FILE = "sessions.json"
FUNDS_FILE = "funds.json"
BUSINESSES_FILE = "businesses.json"
LOGIN_HISTORY_FILE = "login_history.json"
REFERRALS_FILE = "referrals.json"
LOGIN_ATTEMPTS_FILE = "login_attempts.json"
ADMIN_SEED_FILE = "admin_seed.json"

# Login throttle: 3 failures within the window locks the identifier for 30
# minutes. Cleared on the first successful login.
MAX_FAILED_ATTEMPTS = 3
LOCKOUT_DURATION_MS = 30 * 60 * 1000
WITHDRAW_ADDRESSES_FILE = "withdraw_addresses.json"
PENDING_CODES_FILE = "pending_codes.json"
PLANS_FILE = "plans.json"
NEWS_FILE = "news.json"

DEFAULT_PLANS: Dict[str, Dict[str, Any]] = {
    "monthly": {"price": 80.0, "days": 30, "name": "月度套餐"},
    "quarterly": {"price": 220.0, "days": 90, "name": "季度套餐"},
    "yearly": {"price": 800.0, "days": 365, "name": "年度套餐"},
}

DEFAULT_NEWS: List[Dict[str, Any]] = [
    {
        "id": "n1",
        "title": "市场观察：BTC在关键阻力位震荡",
        "summary": "近期主流币种成交量放大，机构资金流入趋势延续，量化策略表现分化。",
        "timestamp": 1714867200000,
        "source": "Galaxy Quant Insights",
    },
    {
        "id": "n2",
        "title": "量化策略周报：动量因子表现回暖",
        "summary": "本周横截面动量因子在永续合约市场中显著跑赢均值回归，多头敞口建议小幅上调。",
        "timestamp": 1714780800000,
        "source": "Galaxy Quant Insights",
    },
    {
        "id": "n3",
        "title": "平台公告：跟单引擎升级完成",
        "summary": "新版本引入更稳健的下单重试机制，订单同步延迟较前一版本降低约 30%。",
        "timestamp": 1714694400000,
        "source": "Platform Notice",
    },
    {
        "id": "n4",
        "title": "风险提示：高杠杆使用须谨慎",
        "summary": "近 24 小时全网爆仓金额上升，建议关注保证金率并合理控制持仓集中度。",
        "timestamp": 1714608000000,
        "source": "Risk Desk",
    },
    {
        "id": "n5",
        "title": "新增功能：提现地址管理",
        "summary": "您现在可以在「钱包」页面统一维护常用提现地址，减少手动输入失误。",
        "timestamp": 1714521600000,
        "source": "Product Update",
    },
]

DEMO_EMAIL = "demo@galaxyquantitative.local"
DEMO_PASSWORD = "demo1234"
DEMO_USERNAME = "demo"

# Far-future "never expires" sentinel matching what we observed in the
# captured SaaS payloads (Dec 31 9999 in ms).
NEVER_EXPIRES_MS = 253402185600000


def _now_ms() -> int:
    return int(time.time() * 1000)


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _gen_invitation_code() -> str:
    # 4-digit numeric code padded with leading zeroes to match captured shape.
    return f"{secrets.randbelow(10000):04d}"


class PortalStore:
    """Singleton JSON-file store. Use get_portal_store()."""

    _instance: Optional["PortalStore"] = None
    _instance_lock = threading.Lock()

    def __init__(self, base_dir: Path = PORTAL_DIR) -> None:
        self._base = base_dir
        self._lock = threading.RLock()
        self._base.mkdir(parents=True, exist_ok=True)
        # Lazy-load on first access; bootstrap demo user on first ever run.
        self._bootstrap_demo_user_if_needed()
        self._seed_default_plans()
        self._seed_default_news()
        self._promote_admins_from_file()
        self._bootstrap_admin_seed()

    # ---- file IO -------------------------------------------------------
    def _path(self, name: str) -> Path:
        return self._base / name

    def _read(self, name: str, default: Any) -> Any:
        path = self._path(name)
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _write(self, name: str, payload: Any) -> None:
        path = self._path(name)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            os.replace(tmp, path)
        except OSError:
            # Best-effort cleanup of the tmp file on failure.
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    # ---- bootstrap -----------------------------------------------------
    def _bootstrap_demo_user_if_needed(self) -> None:
        with self._lock:
            users = self._read(USERS_FILE, [])
            if any(u.get("email", "").lower() == DEMO_EMAIL for u in users):
                return
            salt = secrets.token_hex(16)
            user = {
                "id": secrets.token_hex(12),
                "userName": DEMO_USERNAME,
                "email": DEMO_EMAIL,
                "phoneNumber": None,
                "passwordSalt": salt,
                "passwordHash": _hash_password(DEMO_PASSWORD, salt),
                "balance": 0.0,
                "authority": 1,
                "invitationCode": _gen_invitation_code(),
                "rebateLevel": 1,
                "commissionRate": 0.1,
                "brokerLevel": None,
                "acceptedAgreement": True,
                "points": 0,
                "createdAt": _now_ms(),
                "invitedBy": None,
            }
            users.append(user)
            self._write(USERS_FILE, users)

    # ---- users ---------------------------------------------------------
    def list_users(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._read(USERS_FILE, []))

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        target = (email or "").strip().lower()
        if not target:
            return None
        for u in self.list_users():
            if u.get("email", "").lower() == target:
                return u
        return None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        for u in self.list_users():
            if u.get("id") == user_id:
                return u
        return None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        target = (username or "").strip().lower()
        if not target:
            return None
        for u in self.list_users():
            if (u.get("userName") or "").lower() == target:
                return u
        return None

    def get_user_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Match by email first (presence of '@'), else by userName."""
        s = (identifier or "").strip()
        if not s:
            return None
        if "@" in s:
            return self.get_user_by_email(s)
        # Username login: try exact userName, fallback to email-prefix match.
        u = self.get_user_by_username(s)
        if u:
            return u
        for u in self.list_users():
            email = (u.get("email") or "").lower()
            if email.startswith(s.lower() + "@"):
                return u
        return None

    def create_user(
        self,
        email: str,
        password: str,
        invitation_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise ValueError("invalid email")
        if not password or len(password) < 6:
            raise ValueError("password too short (min 6)")
        with self._lock:
            users = self._read(USERS_FILE, [])
            if any(u.get("email", "").lower() == email for u in users):
                raise ValueError("email already registered")
            invited_by: Optional[str] = None
            if invitation_code:
                code = invitation_code.strip()
                inviter = next(
                    (u for u in users if u.get("invitationCode") == code), None
                )
                if inviter is not None:
                    invited_by = inviter["id"]
            salt = secrets.token_hex(16)
            user = {
                "id": secrets.token_hex(12),
                "userName": email.split("@", 1)[0][:32] or "user",
                "email": email,
                "phoneNumber": None,
                "passwordSalt": salt,
                "passwordHash": _hash_password(password, salt),
                "balance": 0.0,
                "authority": 1,
                "invitationCode": _gen_invitation_code(),
                "rebateLevel": 1,
                "commissionRate": 0.1,
                "brokerLevel": None,
                "acceptedAgreement": True,
                "points": 0,
                "createdAt": _now_ms(),
                "invitedBy": invited_by,
                # Verification + soft-delete state
                "emailVerified": False,
                "deleted": False,
                "deletedAt": None,
            }
            users.append(user)
            self._write(USERS_FILE, users)
            if invited_by:
                refs = self._read(REFERRALS_FILE, [])
                refs.append(
                    {
                        "inviterId": invited_by,
                        "inviteeId": user["id"],
                        "timestamp": _now_ms(),
                    }
                )
                self._write(REFERRALS_FILE, refs)
            return user

    def update_user(self, user_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        with self._lock:
            users = self._read(USERS_FILE, [])
            for u in users:
                if u.get("id") == user_id:
                    u.update(fields)
                    self._write(USERS_FILE, users)
                    return u
            return None

    def verify_password(self, user: Dict[str, Any], password: str) -> bool:
        salt = user.get("passwordSalt") or ""
        expected = user.get("passwordHash") or ""
        if not salt or not expected:
            return False
        return secrets.compare_digest(_hash_password(password, salt), expected)

    def set_password(self, user_id: str, new_password: str) -> bool:
        if not new_password or len(new_password) < 6:
            raise ValueError("password too short (min 6)")
        salt = secrets.token_hex(16)
        return bool(
            self.update_user(
                user_id,
                passwordSalt=salt,
                passwordHash=_hash_password(new_password, salt),
            )
        )

    # ---- security questions (admin password recovery) ------------------
    @staticmethod
    def _normalize_answer(s: str) -> str:
        # Case- and whitespace-insensitive so "Beijing" == "  beijing  ".
        return (s or "").strip().casefold()

    @staticmethod
    def _hash_answer(answer: str, salt: str) -> str:
        return hashlib.sha256(
            (salt + PortalStore._normalize_answer(answer)).encode("utf-8")
        ).hexdigest()

    def set_security_questions(
        self, user_id: str, items: List[Dict[str, str]]
    ) -> bool:
        """Store per-user security questions.

        ``items`` is a list of ``{question, answer}`` dicts (plaintext on
        the wire, hashed at rest with a per-question salt). Requires at
        least 3 questions. Empty questions or answers are rejected.
        """
        if not isinstance(items, list) or len(items) < 3:
            raise ValueError("at least 3 security questions required")
        records = []
        for entry in items:
            q = (entry.get("question") or entry.get("q") or "").strip()
            a = entry.get("answer") if "answer" in entry else entry.get("a")
            if not q or not a:
                raise ValueError("each question must have non-empty question + answer")
            salt = secrets.token_hex(12)
            records.append({
                "question": q,
                "salt": salt,
                "answerHash": self._hash_answer(str(a), salt),
            })
        return bool(
            self.update_user(
                user_id,
                securityQuestions=records,
                securityQuestionsUpdatedAt=_now_ms(),
            )
        )

    def get_security_questions_for_email(
        self, email: str
    ) -> Optional[List[Dict[str, str]]]:
        """Return ONLY the question text (no salt, no hash) for an admin user.

        Public-route safe: this never leaks the answer hashes. Returns None
        if the email isn't registered, isn't an admin, or has no questions
        configured. Non-admins are excluded so this can't be used as a
        general-purpose user-enumeration oracle.
        """
        user = self.get_user_by_email(email)
        if not user or int(user.get("authority", 1)) < 9:
            return None
        items = user.get("securityQuestions") or []
        if not items:
            return None
        return [{"question": item.get("question", "")} for item in items if item.get("question")]

    def verify_security_answers(
        self, email: str, answers: List[str]
    ) -> Optional[str]:
        """Return the user_id if every answer matches the stored hash.

        All-or-nothing: every configured question must be answered
        correctly. Returns None on any mismatch (or when the user has no
        questions). Comparison is case-insensitive and trims whitespace.
        """
        user = self.get_user_by_email(email)
        if not user or int(user.get("authority", 1)) < 9:
            return None
        items = user.get("securityQuestions") or []
        if not items or not isinstance(answers, list):
            return None
        if len(answers) != len(items):
            return None
        for stored, supplied in zip(items, answers):
            salt = stored.get("salt") or ""
            expected = stored.get("answerHash") or ""
            if not salt or not expected:
                return None
            actual = self._hash_answer(str(supplied or ""), salt)
            if not secrets.compare_digest(expected, actual):
                return None
        return user.get("id")

    # ---- first-run admin setup -----------------------------------------
    def is_admin_setup_needed(self) -> bool:
        """True until the operator has finished the first-run wizard.

        We treat "setup complete" as: at least one user with authority>=9
        AND that user has security questions configured. The seeded
        ``cornna`` factory account does NOT count as complete because it
        has no questions yet — the wizard must be run before recovery
        flows are usable.
        """
        for u in self.list_users():
            if int(u.get("authority", 1)) >= 9 and (u.get("securityQuestions") or []):
                return False
        return True

    def complete_admin_setup(
        self,
        userName: str,
        email: str,
        password: str,
        questions: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Idempotent first-run wizard: creates or upgrades the admin user.

        Logic:
          - If ``setup_needed`` is False, raises ValueError (the public
            route should refuse to call this — defence-in-depth here).
          - If a user with the same email or userName exists, that record
            is upgraded to authority=9 and its credentials + questions are
            replaced (this lets the operator overwrite the seeded
            ``cornna`` admin without manually editing JSON).
          - Otherwise a fresh admin user is created.
        """
        if not self.is_admin_setup_needed():
            raise ValueError("admin setup is already complete")

        userName = (userName or "").strip()
        email_norm = (email or "").strip().lower()
        if not userName or not email_norm or "@" not in email_norm:
            raise ValueError("userName and a valid email are required")
        if not password or len(password) < 6:
            raise ValueError("password too short (min 6)")
        if not isinstance(questions, list) or len(questions) < 3:
            raise ValueError("at least 3 security questions required")

        # Validate + hash questions up-front so we don't half-write users.
        prepared: List[Dict[str, str]] = []
        for entry in questions:
            q = (entry.get("question") or entry.get("q") or "").strip()
            a = entry.get("answer") if "answer" in entry else entry.get("a")
            if not q or not a:
                raise ValueError("each question must have non-empty question + answer")
            salt = secrets.token_hex(12)
            prepared.append({
                "question": q,
                "salt": salt,
                "answerHash": self._hash_answer(str(a), salt),
            })

        salt = secrets.token_hex(16)
        with self._lock:
            users = self._read(USERS_FILE, [])
            target = None
            for u in users:
                if (
                    (u.get("email") or "").lower() == email_norm
                    or (u.get("userName") or "").lower() == userName.lower()
                ):
                    target = u
                    break

            if target is None:
                target = {
                    "id": secrets.token_hex(12),
                    "userName": userName,
                    "email": email_norm,
                    "phoneNumber": None,
                    "balance": 0.0,
                    "invitationCode": _gen_invitation_code(),
                    "rebateLevel": 1,
                    "commissionRate": 0.1,
                    "brokerLevel": None,
                    "acceptedAgreement": True,
                    "points": 0,
                    "createdAt": _now_ms(),
                    "invitedBy": None,
                }
                users.append(target)

            target["userName"] = userName
            target["email"] = email_norm
            target["authority"] = 9
            target["passwordSalt"] = salt
            target["passwordHash"] = _hash_password(password, salt)
            target["securityQuestions"] = prepared
            target["securityQuestionsUpdatedAt"] = _now_ms()
            target["adminSetupCompletedAt"] = _now_ms()
            self._write(USERS_FILE, users)
            return dict(target)

    # ---- sessions ------------------------------------------------------
    def create_session(self, user_id: str, ttl_seconds: int = 7 * 24 * 3600) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            sessions = self._read(SESSIONS_FILE, {})
            sessions[token] = {
                "userId": user_id,
                "createdAt": _now_ms(),
                "expiresAt": _now_ms() + ttl_seconds * 1000,
            }
            self._write(SESSIONS_FILE, sessions)
        return token

    def get_session_user(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with self._lock:
            sessions = self._read(SESSIONS_FILE, {})
            entry = sessions.get(token)
            if not entry:
                return None
            if entry.get("expiresAt", 0) < _now_ms():
                sessions.pop(token, None)
                self._write(SESSIONS_FILE, sessions)
                return None
        return self.get_user_by_id(entry["userId"])

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            sessions = self._read(SESSIONS_FILE, {})
            if token in sessions:
                sessions.pop(token, None)
                self._write(SESSIONS_FILE, sessions)

    # ---- funds ledger --------------------------------------------------
    def list_funds(self, user_id: str, action_type: int = -1) -> List[Dict[str, Any]]:
        with self._lock:
            ledger = self._read(FUNDS_FILE, {})
            entries = list(ledger.get(user_id, []))
        if action_type == -1:
            return entries
        return [e for e in entries if int(e.get("actionType", 0)) == int(action_type)]

    def add_fund_entry(
        self,
        user_id: str,
        action_type: int,
        amount: float,
        source: Optional[str] = "",
    ) -> Dict[str, Any]:
        entry = {
            "actionType": int(action_type),
            "timestamp": _now_ms(),
            "amount": float(amount),
            "source": source if source is not None else "",
        }
        with self._lock:
            ledger = self._read(FUNDS_FILE, {})
            ledger.setdefault(user_id, []).append(entry)
            self._write(FUNDS_FILE, ledger)
        return entry

    # ---- businesses ----------------------------------------------------
    def list_businesses(
        self,
        user_id: str,
        effective_only: bool = False,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            store = self._read(BUSINESSES_FILE, {})
            items = list(store.get(user_id, []))
        if effective_only:
            now = _now_ms()
            items = [
                b
                for b in items
                if int(b.get("expirationTimestamp", 0)) > now and b.get("visibled", True)
            ]
        return items

    def add_business(self, user_id: str, biz: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "id": biz.get("id") or secrets.token_hex(12),
            "correlationId": biz.get("correlationId"),
            "type": int(biz.get("type", 2)),
            "accountIndex": biz.get("accountIndex"),
            "apiKey": biz.get("apiKey"),
            "createTimestamp": int(biz.get("createTimestamp") or _now_ms()),
            "activationTimestamp": int(biz.get("activationTimestamp") or _now_ms()),
            "expirationTimestamp": int(biz.get("expirationTimestamp") or NEVER_EXPIRES_MS),
            "autoRenewal": bool(biz.get("autoRenewal", False)),
            "bindingExchange": biz.get("bindingExchange"),
            "bindingUid": biz.get("bindingUid"),
            "alias": biz.get("alias", ""),
            "visibled": bool(biz.get("visibled", True)),
            "tradeAccountId": biz.get("tradeAccountId"),
        }
        with self._lock:
            store = self._read(BUSINESSES_FILE, {})
            store.setdefault(user_id, []).append(record)
            self._write(BUSINESSES_FILE, store)
        return record

    def find_business(
        self, user_id: str, biz_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            store = self._read(BUSINESSES_FILE, {})
            for biz in store.get(user_id, []):
                if biz.get("id") == biz_id:
                    return dict(biz)
        return None

    def update_business(
        self, user_id: str, biz_id: str, **fields: Any
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            store = self._read(BUSINESSES_FILE, {})
            items = store.get(user_id, [])
            for biz in items:
                if biz.get("id") == biz_id:
                    biz.update(fields)
                    self._write(BUSINESSES_FILE, store)
                    return dict(biz)
        return None

    def delete_business(self, user_id: str, biz_id: str) -> bool:
        """Soft-archive: visibled=False rather than hard delete."""
        return self.update_business(user_id, biz_id, visibled=False) is not None

    def find_business_by_trade_account(
        self, account_id: str
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        if not account_id:
            return None
        with self._lock:
            store = self._read(BUSINESSES_FILE, {})
            for user_id, items in store.items():
                for biz in items:
                    if biz.get("tradeAccountId") == account_id:
                        return user_id, dict(biz)
        return None

    def get_active_business_for_account(
        self, account_id: str
    ) -> Optional[Dict[str, Any]]:
        match = self.find_business_by_trade_account(account_id)
        if not match:
            return None
        _, biz = match
        if not biz.get("visibled", True):
            return None
        if int(biz.get("expirationTimestamp", 0)) <= _now_ms():
            return None
        return biz

    def sweep_expired(self) -> List[Dict[str, Any]]:
        """Mark businesses that just expired and return them.

        We tag each expired record with `_sweptAt` so subsequent passes don't
        report the same record twice. Caller is responsible for disabling
        whatever TradingAccount(s) the records reference.
        """
        now = _now_ms()
        newly_expired: List[Dict[str, Any]] = []
        with self._lock:
            store = self._read(BUSINESSES_FILE, {})
            mutated = False
            for user_id, items in store.items():
                for biz in items:
                    if not biz.get("tradeAccountId"):
                        continue
                    if int(biz.get("expirationTimestamp", 0)) > now:
                        continue
                    if biz.get("_sweptAt"):
                        continue
                    biz["_sweptAt"] = now
                    biz["visibled"] = False
                    mutated = True
                    record = dict(biz)
                    record["_userId"] = user_id
                    newly_expired.append(record)
            if mutated:
                self._write(BUSINESSES_FILE, store)
        return newly_expired

    # ---- login history -------------------------------------------------
    def list_login_history(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            store = self._read(LOGIN_HISTORY_FILE, {})
            return list(store.get(user_id, []))

    def add_login_record(
        self,
        user_id: str,
        ip: str,
        location: str = "Unknown",
    ) -> Dict[str, Any]:
        entry = {"ip": ip or "", "location": location or "Unknown", "timestamp": _now_ms()}
        with self._lock:
            store = self._read(LOGIN_HISTORY_FILE, {})
            history = store.setdefault(user_id, [])
            history.append(entry)
            # Cap history at 50 entries to avoid runaway growth.
            if len(history) > 50:
                store[user_id] = history[-50:]
            self._write(LOGIN_HISTORY_FILE, store)
        return entry

    # ---- referrals -----------------------------------------------------
    def list_referrals_of(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            refs = self._read(REFERRALS_FILE, [])
        return [r for r in refs if r.get("inviterId") == user_id]

    def list_invitees(self, user_id: str) -> List[Dict[str, Any]]:
        """For /referral page: every user the given inviter brought in,
        joined with their email + verified state + active-business flag."""
        refs = self.list_referrals_of(user_id)
        if not refs:
            return []
        with self._lock:
            users = self._read(USERS_FILE, [])
            biz_store = self._read(BUSINESSES_FILE, {})
        by_id = {u.get("id"): u for u in users}
        now = _now_ms()
        out: List[Dict[str, Any]] = []
        for r in refs:
            invitee_id = r.get("inviteeId")
            u = by_id.get(invitee_id)
            if not u:
                continue
            if u.get("deleted"):
                continue
            biz_list = biz_store.get(invitee_id) or []
            has_active = any(
                int(b.get("expirationTimestamp", 0)) > now
                and b.get("visibled", True)
                and int(b.get("type", 0)) == 1  # type=1 = paid quota
                for b in biz_list
            )
            out.append({
                "inviteeId": invitee_id,
                "email": u.get("email"),
                "userName": u.get("userName"),
                "registeredAt": r.get("timestamp") or u.get("createdAt"),
                "emailVerified": bool(u.get("emailVerified")),
                "hasActivePlan": has_active,
            })
        # Newest first
        out.sort(key=lambda r: int(r.get("registeredAt") or 0), reverse=True)
        return out

    def get_inviter_email(self, user: Dict[str, Any]) -> Optional[str]:
        inviter_id = user.get("invitedBy")
        if not inviter_id:
            return None
        inviter = self.get_user_by_id(inviter_id)
        return inviter.get("email") if inviter else None

    # ---- email verification --------------------------------------------
    def set_email_verified(self, user_id: str, verified: bool = True) -> Optional[Dict[str, Any]]:
        return self.update_user(user_id, emailVerified=bool(verified))

    # ---- soft delete ---------------------------------------------------
    def soft_delete_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Archive the account: rename email to a sentinel, blank password,
        clear sessions. The user record itself is kept for audit + referral
        history. Caller is responsible for verifying the user's password
        before invoking this."""
        ts = _now_ms()
        sentinel_email = f"deleted-{user_id}@archive.local"
        with self._lock:
            users = self._read(USERS_FILE, [])
            target = None
            for u in users:
                if u.get("id") == user_id:
                    target = u
                    u["email"] = sentinel_email
                    u["userName"] = f"deleted-{user_id[:8]}"
                    u["passwordSalt"] = ""
                    u["passwordHash"] = ""
                    u["phoneNumber"] = None
                    u["balance"] = 0.0
                    u["deleted"] = True
                    u["deletedAt"] = ts
                    u["emailVerified"] = False
                    break
            if not target:
                return None
            self._write(USERS_FILE, users)
            # Wipe sessions for this user.
            sessions = self._read(SESSIONS_FILE, {})
            kept = {tok: rec for tok, rec in sessions.items() if rec.get("userId") != user_id}
            if len(kept) != len(sessions):
                self._write(SESSIONS_FILE, kept)
            # Soft-archive any active businesses (visibled=False).
            biz_store = self._read(BUSINESSES_FILE, {})
            biz_list = biz_store.get(user_id) or []
            for b in biz_list:
                b["visibled"] = False
            biz_store[user_id] = biz_list
            self._write(BUSINESSES_FILE, biz_store)
            return target

    # ---- new-user perks ------------------------------------------------
    def grant_signup_trial(self, user_id: str, days: int = 7, alias: str = "新人 7 天试用") -> Dict[str, Any]:
        """Auto-create a Business that grants the new user a free quota."""
        return self.add_business(user_id, {
            "type": 1,  # quota / 下单名额 (matches Mall purchases so /wallet shows it the same)
            "expirationTimestamp": _now_ms() + days * 86400000,
            "alias": alias,
            "autoRenewal": False,
        })

    # ---- profile field updates ----------------------------------------
    def set_phone(self, user_id: str, phone: Optional[str]) -> bool:
        return self.update_user(user_id, phoneNumber=phone) is not None

    def set_email(self, user_id: str, email: str) -> bool:
        normalized = (email or "").strip().lower()
        if not normalized or "@" not in normalized:
            return False
        with self._lock:
            users = self._read(USERS_FILE, [])
            if any(
                u.get("email", "").lower() == normalized and u.get("id") != user_id
                for u in users
            ):
                return False
            for u in users:
                if u.get("id") == user_id:
                    u["email"] = normalized
                    self._write(USERS_FILE, users)
                    return True
        return False

    # ---- pending verification codes ------------------------------------
    def set_pending_code(
        self, target: str, code: str, ttl_seconds: int = 300
    ) -> Dict[str, Any]:
        target = (target or "").strip()
        if not target:
            raise ValueError("target is required")
        entry = {
            "code": code,
            "expiresAt": _now_ms() + int(ttl_seconds) * 1000,
        }
        with self._lock:
            store = self._read(PENDING_CODES_FILE, {})
            store[target] = entry
            self._write(PENDING_CODES_FILE, store)
        return entry

    def verify_pending_code(self, target: str, code: str) -> bool:
        target = (target or "").strip()
        code = (code or "").strip()
        if not target or not code:
            return False
        with self._lock:
            store = self._read(PENDING_CODES_FILE, {})
            entry = store.get(target)
            if not entry:
                return False
            if int(entry.get("expiresAt", 0)) < _now_ms():
                store.pop(target, None)
                self._write(PENDING_CODES_FILE, store)
                return False
            if not secrets.compare_digest(str(entry.get("code", "")), code):
                return False
            store.pop(target, None)
            self._write(PENDING_CODES_FILE, store)
            return True

    # ---- withdraw addresses --------------------------------------------
    def list_withdraw_addresses(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            store = self._read(WITHDRAW_ADDRESSES_FILE, {})
            return list(store.get(user_id, []))

    def add_withdraw_address(
        self,
        user_id: str,
        alias: str,
        value: str,
        network: str = "TRC20",
    ) -> Dict[str, Any]:
        alias = (alias or "").strip()
        value = (value or "").strip()
        if not value:
            raise ValueError("address value required")
        record = {
            "id": secrets.token_hex(8),
            "alias": alias or value[:8],
            "value": value,
            "network": (network or "TRC20").strip() or "TRC20",
            "createdAt": _now_ms(),
        }
        with self._lock:
            store = self._read(WITHDRAW_ADDRESSES_FILE, {})
            store.setdefault(user_id, []).append(record)
            self._write(WITHDRAW_ADDRESSES_FILE, store)
        return record

    def remove_withdraw_address(self, user_id: str, addr_id: str) -> bool:
        with self._lock:
            store = self._read(WITHDRAW_ADDRESSES_FILE, {})
            items = store.get(user_id, [])
            new_items = [a for a in items if a.get("id") != addr_id]
            if len(new_items) == len(items):
                return False
            store[user_id] = new_items
            self._write(WITHDRAW_ADDRESSES_FILE, store)
            return True

    # ---- plans ----------------------------------------------------------
    def list_plans(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            data = self._read(PLANS_FILE, None)
            if not isinstance(data, dict) or not data:
                self._write(PLANS_FILE, DEFAULT_PLANS)
                return dict(DEFAULT_PLANS)
            return dict(data)

    # ---- balance debit (atomic) ----------------------------------------
    def debit_balance(
        self, user_id: str, amount: float, source: str
    ) -> Optional[Dict[str, Any]]:
        amount = float(amount)
        if amount <= 0:
            return None
        with self._lock:
            users = self._read(USERS_FILE, [])
            target = next((u for u in users if u.get("id") == user_id), None)
            if target is None:
                return None
            current = float(target.get("balance") or 0.0)
            if current < amount:
                return None
            target["balance"] = current - amount
            self._write(USERS_FILE, users)
            entry = {
                "actionType": 2,
                "timestamp": _now_ms(),
                "amount": -amount,
                "source": source or "",
            }
            ledger = self._read(FUNDS_FILE, {})
            ledger.setdefault(user_id, []).append(entry)
            self._write(FUNDS_FILE, ledger)
            return entry

    # ---- seed helpers ---------------------------------------------------
    def _seed_default_plans(self) -> None:
        with self._lock:
            if not self._path(PLANS_FILE).is_file():
                self._write(PLANS_FILE, DEFAULT_PLANS)

    def _seed_default_news(self) -> None:
        with self._lock:
            if not self._path(NEWS_FILE).is_file():
                self._write(NEWS_FILE, DEFAULT_NEWS)

    def list_news(self) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._read(NEWS_FILE, None)
            if not isinstance(data, list) or not data:
                self._write(NEWS_FILE, DEFAULT_NEWS)
                return list(DEFAULT_NEWS)
            return list(data)

    # ---- admin promotion -----------------------------------------------
    # Declarative admin list at runtime/portal/admin_emails.txt — one email
    # per line, '#' comments allowed. On boot we set authority=9 for any
    # matching user. Demote-by-removing-the-line is intentional NOT supported
    # here (that would let an operator accidentally lock themselves out by
    # deleting the file) — demotion goes through the admin endpoint instead.
    def _admin_emails_file(self) -> Path:
        return self._base / "admin_emails.txt"

    def _promote_admins_from_file(self) -> None:
        path = self._admin_emails_file()
        if not path.is_file():
            return
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        targets = {
            ln.strip().lower()
            for ln in lines
            if ln.strip() and not ln.strip().startswith("#")
        }
        if not targets:
            return
        with self._lock:
            users = self._read(USERS_FILE, [])
            changed = False
            for u in users:
                email = (u.get("email") or "").lower()
                if email in targets and int(u.get("authority", 1)) < 9:
                    u["authority"] = 9
                    changed = True
            if changed:
                self._write(USERS_FILE, users)

    # ---- login throttle / lockout --------------------------------------
    # Stored as {identifier_lower: {count, firstAt, lastAt, lockedUntil}}.
    # `identifier` is whatever the operator typed (email or userName) so
    # locking does NOT bypass when the same actor toggles the field. Cleared
    # on first successful login.
    def _load_attempts(self) -> Dict[str, Dict[str, int]]:
        return self._read(LOGIN_ATTEMPTS_FILE, {})

    def _save_attempts(self, data: Dict[str, Dict[str, int]]) -> None:
        self._write(LOGIN_ATTEMPTS_FILE, data)

    @staticmethod
    def _attempt_key(identifier: str) -> str:
        return (identifier or "").strip().lower()

    def is_locked(self, identifier: str) -> Optional[int]:
        """Return remaining lockout seconds if currently locked, else None."""
        key = self._attempt_key(identifier)
        if not key:
            return None
        with self._lock:
            attempts = self._load_attempts()
            entry = attempts.get(key)
            if not entry:
                return None
            locked_until = int(entry.get("lockedUntil", 0))
            if locked_until <= 0:
                return None
            remaining_ms = locked_until - _now_ms()
            if remaining_ms <= 0:
                # Lock expired — clear silently so the next login starts fresh.
                attempts.pop(key, None)
                self._save_attempts(attempts)
                return None
            return max(1, int(remaining_ms / 1000))

    def record_failed_login(self, identifier: str) -> Dict[str, int]:
        """Increment fail counter; return {count, remaining, lockedSeconds}."""
        key = self._attempt_key(identifier)
        if not key:
            return {"count": 0, "remaining": MAX_FAILED_ATTEMPTS, "lockedSeconds": 0}
        now = _now_ms()
        with self._lock:
            attempts = self._load_attempts()
            entry = attempts.get(key) or {"count": 0, "firstAt": now, "lastAt": now, "lockedUntil": 0}
            # If a previous lockout is still in effect, do NOT increment further —
            # report the existing lock window. (Defensive: caller usually checks
            # is_locked first.)
            locked_until = int(entry.get("lockedUntil", 0))
            if locked_until > now:
                return {
                    "count": int(entry.get("count", 0)),
                    "remaining": 0,
                    "lockedSeconds": int((locked_until - now) / 1000),
                }
            entry["count"] = int(entry.get("count", 0)) + 1
            entry["lastAt"] = now
            entry.setdefault("firstAt", now)
            locked_seconds = 0
            if entry["count"] >= MAX_FAILED_ATTEMPTS:
                entry["lockedUntil"] = now + LOCKOUT_DURATION_MS
                locked_seconds = int(LOCKOUT_DURATION_MS / 1000)
            else:
                entry["lockedUntil"] = 0
            attempts[key] = entry
            self._save_attempts(attempts)
            return {
                "count": entry["count"],
                "remaining": max(0, MAX_FAILED_ATTEMPTS - entry["count"]),
                "lockedSeconds": locked_seconds,
            }

    def clear_failed_login(self, identifier: str) -> None:
        key = self._attempt_key(identifier)
        if not key:
            return
        with self._lock:
            attempts = self._load_attempts()
            if key in attempts:
                attempts.pop(key, None)
                self._save_attempts(attempts)

    # ---- admin seed (operator-provisioned account) ---------------------
    # Reads runtime/portal/admin_seed.json on boot. Schema:
    #   {"userName": "cornna", "password": "...", "email": "...", "authority": 9}
    # If the user does not exist, it's created with that password and
    # authority=9. If it exists, only authority is kept current (>=9); the
    # password is NOT silently overwritten — operators rotate via the admin
    # endpoint or by deleting the user from users.json first.
    def _bootstrap_admin_seed(self) -> None:
        path = self._path(ADMIN_SEED_FILE)
        if not path.is_file():
            return
        try:
            seed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(seed, dict):
            return
        username = (seed.get("userName") or "").strip()
        password = seed.get("password") or ""
        email = (seed.get("email") or "").strip().lower()
        authority = int(seed.get("authority") or 9)
        if not username or not password:
            return
        if not email:
            email = f"{username.lower()}@galaxyquantitative.local"
        with self._lock:
            users = self._read(USERS_FILE, [])
            existing = next(
                (
                    u for u in users
                    if (u.get("userName") or "").lower() == username.lower()
                    or (u.get("email") or "").lower() == email
                ),
                None,
            )
            if existing:
                # Make sure they keep admin rights; don't touch password.
                if int(existing.get("authority", 1)) < authority:
                    existing["authority"] = authority
                    self._write(USERS_FILE, users)
                return
            salt = secrets.token_hex(16)
            user = {
                "id": secrets.token_hex(12),
                "userName": username,
                "email": email,
                "phoneNumber": None,
                "passwordSalt": salt,
                "passwordHash": _hash_password(password, salt),
                "balance": 0.0,
                "authority": authority,
                "invitationCode": _gen_invitation_code(),
                "rebateLevel": 1,
                "commissionRate": 0.1,
                "brokerLevel": None,
                "acceptedAgreement": True,
                "points": 0,
                "createdAt": _now_ms(),
                "invitedBy": None,
            }
            users.append(user)
            self._write(USERS_FILE, users)

    def is_admin_email(self, email: str) -> bool:
        """Used by login flow to auto-promote on next sign-in if file changed."""
        path = self._admin_emails_file()
        if not path.is_file():
            return False
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False
        target = (email or "").strip().lower()
        for ln in lines:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if ln.lower() == target:
                return True
        return False


def get_portal_store() -> PortalStore:
    if PortalStore._instance is None:
        with PortalStore._instance_lock:
            if PortalStore._instance is None:
                PortalStore._instance = PortalStore()
    return PortalStore._instance


__all__ = ["PortalStore", "get_portal_store", "DEMO_EMAIL", "DEMO_PASSWORD"]
