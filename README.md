# Binance Copy Sync (Local)

This project polls Binance copy-trade order history at high frequency and mirrors the leader order flow into a local event stream. It is designed for ultra-fast polling (100-300ms) when true WebSocket push is not available.

## Requirements

- Python 3.10+
- Chrome started with remote debugging (CDP mode)

## Install

```bash
pip install -r requirements.txt
python -m playwright install  # only needed for CDP mode
```

## Start Chrome (remote debugging)

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:TEMP\binance-debug-profile"
```

Login to Binance and open a copy trading leader page before starting the server.

## Server deployment (no GUI)

For VPS or servers without a desktop, use cookie auth to avoid Chrome/CDP.

1. On a desktop browser, log in to Binance or testnet and export cookies to `cookies.json`.
   The file can be either a list of cookie objects or `{"cookies": [...]}` from Playwright storage.
2. Copy `cookies.json` to the server.
3. Update `config.json`:

```json
{
  "auth_mode": "cookie",
  "cookie_path": "cookies.json",
  "api_base": "https://testnet.binancefuture.com"
}
```

Replace `cookies.json` whenever the session expires.

## Run the server

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

## Testnet

Set `api_base` in `config.json` to the testnet domain you are using (for U-M futures this is often `https://testnet.binancefuture.com`).
You must also open the corresponding testnet website in Chrome so the session cookies match.

## Direct API trading

This app sends orders through the official USDS-M Futures REST API using direct HTTP.
Signed endpoints require `X-MBX-APIKEY` header and HMAC SHA256 signature over the query string.

Example flow:

1. Fill `trade_config.json` with your **testnet** API key/secret.
2. Keep `"enabled": false` until you are ready.
3. Start the server and observe events.
4. Set `"enabled": true` to send real orders.

`trade_config.json` uses `/fapi/v1/order` (MARKET) by default and can sync time via `/fapi/v1/time`.

## Notes

- Set `poll_interval_ms` to 100-300 for the lowest latency. This still depends on Binance API update timing.
- The executor sends orders only if `trade_config.json` is enabled and correctly filled.
- `config.json` is persisted on edits.
