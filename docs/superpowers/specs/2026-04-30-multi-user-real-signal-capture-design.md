# Multi-User Real Signal Capture Design

Date: 2026-04-30
Status: Approved for planning

## Goal

Build a Docker-deployable, HTTPS-served copy-trading signal platform where multiple users can connect their own Binance and OKX web login sessions from the frontend, persist those sessions securely, and receive all supported real trading signals in an isolated per-user signal stream.

The first production path focuses on Binance and OKX leader/copy-trading signals. Telegram and Discord text signals are unified into the same pipeline next. Hyperliquid, BiCoin, and Binance Smart Money follow as later adapters behind the same source interface.

The system must default to signal capture only. Real order execution remains opt-in per user, per account, and per subscription.

## Confirmed Requirements

- Deployment target is a server with a public HTTPS domain.
- Users initiate exchange login from the web frontend.
- Login opens a standalone one-time remote browser link, not an embedded frame.
- The browser runs inside the Docker service environment with an isolated exchange profile.
- Users complete Binance or OKX login themselves, including QR, password, and 2FA flows.
- The backend persists only the resulting session state, not exchange passwords.
- The platform supports multiple users, each with private exchange login state, leader subscriptions, signal history, and optional trading API keys.
- Version 1 uses built-in accounts and passwords. Later, third-party login such as Google, GitHub, or Telegram is added without changing business ownership.

## Recommended Architecture

Use a platform-style multi-tenant data model immediately, but run the first version inside one service process with shared managers:

- `AuthService`: built-in user login, session cookies/JWTs, admin role checks.
- `CredentialVault`: encrypted storage for exchange web sessions and API secrets.
- `RemoteLoginService`: creates one-time login sessions and isolated browser profiles.
- `ExchangeSessionManager`: loads stored web sessions for Binance/OKX capture clients.
- `SignalIngestionManager`: schedules per-user source polling and normalizes signals.
- `SignalStore`: durable signal history keyed by `user_id`.
- `ExecutionRouter`: optional order execution, disabled by default.

This keeps the first implementation simpler than per-user containers while preserving the boundaries needed to split workers later.

## User And Permission Model

The first version adds a built-in account system:

- `users`: email, password hash, role, status, timestamps.
- `user_sessions`: active app sessions with expiry and revocation.
- `auth_identities`: reserved for later OAuth/Telegram identities.

Every user-owned object must include `user_id`: exchange sessions, leader subscriptions, trading accounts, signals, and execution settings.

Admin permissions are operational only. Admins may see service health, task status, user counts, stale login state, and masked metadata. Admins must not receive plaintext cookies, storage state, API secrets, passphrases, or exchange passwords.

## Remote Exchange Login

The frontend exposes actions such as "Connect Binance" and "Connect OKX". When clicked:

1. Backend creates a `login_session` row for the current `user_id`, exchange, nonce, expiry, and state.
2. Backend starts or reserves an isolated browser profile directory under the persisted runtime volume.
3. Backend returns a one-time HTTPS login URL.
4. User opens the URL in a separate page and interacts with the remote browser.
5. After successful exchange login, backend captures cookies, storage state, selected localStorage values, and important request headers.
6. Backend encrypts the captured state and writes it to the user's vault record.
7. Login session is marked consumed or expired, and the exchange connection becomes active.

The login URL must be short-lived, bound to the initiating user, and invalid after completion. Audit events should record create, open, success, expiry, and revoke events.

The system should not ask for or store exchange account passwords.

## Credential Persistence

Credentials are stored in an encrypted vault backed by Docker volumes. Encryption uses an application key supplied by environment variable, for example `APP_ENCRYPTION_KEY`.

Vault records:

- Binance/OKX web session state for signal capture.
- Optional Binance/OKX trading API credentials for execution.
- Metadata such as exchange, status, created time, last verified time, and expiry hints.

Plaintext credential material should exist only in memory during active capture or execution. API responses return only masked credential status.

## Signal Capture Pipeline

All source adapters emit normalized events into one pipeline:

- `open`
- `add`
- `reduce`
- `close`

Phase 1 covers Binance and OKX:

- Use each user's stored web session to fetch leader details, current positions, and position history where available.
- Detect position changes per leader subscription.
- Persist normalized signals to a database, not only the current in-memory deque.
- Publish new signals to the frontend over the existing realtime stream, filtered by `user_id`.

Phase 2 covers Telegram and Discord:

- Existing text parsing is retained but routed through the same user-owned signal pipeline.
- Telegram/Discord tokens and channel IDs become user-owned credentials/configuration.

Phase 3 covers additional sources:

- Hyperliquid, BiCoin, and Binance Smart Money adapters replace current stub implementations.
- Each adapter conforms to the same normalized position/signal contract.

## Execution Boundary

Real order execution is separate from signal capture.

Defaults:

- `execute_signals = false`
- trading accounts disabled
- leader subscription execution disabled

Execution can occur only when all are true:

- user has configured and enabled a trading account,
- the relevant leader subscription has execution enabled,
- the source signal passes validation and deduplication,
- the executor account belongs to the same `user_id`,
- risk limits allow the order.

This preserves a safe observation mode for most usage while allowing opt-in automated mirroring.

## Frontend Changes

Add user-facing flows:

- Login/register screen for built-in accounts.
- User account menu and logout.
- Exchange connection panel with "Connect Binance" and "Connect OKX".
- Login session status: pending, active, expired, failed, revoked.
- Per-user leader subscription management.
- Per-user signal history and realtime feed.
- Optional execution account setup, clearly disabled by default.

Admin views show health and masked metadata only.

## API Surface

Initial endpoints:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/me`
- `POST /api/exchange-logins/{exchange}/sessions`
- `GET /api/exchange-logins/sessions/{session_id}`
- `POST /api/exchange-logins/sessions/{session_id}/complete`
- `POST /api/exchange-logins/sessions/{session_id}/revoke`
- `GET /api/exchange-credentials`
- `POST /api/leaders`
- `GET /api/leaders`
- `GET /api/signals`
- `GET /api/signals/stream`
- `GET /api/admin/health`

Existing endpoints must be migrated or wrapped so they derive user context from authentication instead of acting globally.

## Docker Deployment

The Docker image needs browser runtime support in addition to Python dependencies. The compose setup should persist:

- app config and database,
- encrypted credential vault,
- browser profiles/session state,
- API token or app secret,
- encryption key supplied via environment,
- logs or runtime diagnostics as needed.

The public HTTPS domain should terminate TLS at a reverse proxy. The application remains bound behind the proxy. Login links are generated with the configured public base URL and short expiry.

## Data Model Sketch

Core tables:

- `users`
- `user_sessions`
- `auth_identities`
- `exchange_credentials`
- `exchange_login_sessions`
- `leader_subscriptions`
- `trading_accounts`
- `signals`
- `signal_executions`
- `audit_events`

Existing project/account configuration can be migrated into `leader_subscriptions` and `trading_accounts`, preserving compatibility where practical.

## Error Handling And Safety

- Expired login sessions are cleaned up automatically.
- Stale exchange sessions are marked `needs_login`.
- Failed capture attempts produce user-visible health status without exposing secrets.
- Signal deduplication must use stable source identifiers where available, with fallback signatures for position deltas.
- Polling errors should not cross user boundaries.
- SSE/WebSocket streams must filter by authenticated user.
- Admin APIs must mask all secret fields.

## Testing Strategy

Unit tests:

- user scoping and permission checks,
- vault encryption/decryption and masking,
- login session lifecycle,
- signal normalization and deduplication,
- execution gating defaults.

Integration tests:

- authenticated API isolation between two users,
- Binance/OKX session loading from stored state,
- signal persistence and realtime delivery,
- disabled execution does not place orders.

Deployment checks:

- Docker image includes browser dependencies,
- persistent volumes survive restart,
- HTTPS public URL is used for one-time login links,
- expired/revoked login links cannot be reused.

## Phased Delivery

1. Add multi-user auth, user-scoped data model, and encrypted vault.
2. Add Docker browser runtime and one-time remote login sessions.
3. Migrate Binance and OKX capture to per-user stored sessions.
4. Persist signals and filter realtime streams by user.
5. Add optional per-user execution controls with safe defaults.
6. Fold Telegram and Discord into the same pipeline.
7. Implement Hyperliquid, BiCoin, and Smart Money adapters.
8. Add third-party login identities.

## Open Implementation Choices

- Choose the exact remote browser presentation mechanism for the one-time URL.
- Choose the durable database layer for multi-user records.
- Choose whether first production uses SSE only or upgrades to WebSocket for richer login session status.

These choices are implementation details for the planning phase; they do not change the confirmed product behavior.
