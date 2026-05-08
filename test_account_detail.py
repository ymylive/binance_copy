"""
Smoke test for /api/portal/account/{biz_id}/detail.
Requires:
- runtime/api_token.txt OR a fresh /api/portal/auth/login
- A real biz_id existing for that user

Set REAL_USER_TOKEN and REAL_BIZ_ID env vars before running.
"""
import json, os, urllib.request, urllib.error

TOKEN = os.getenv("REAL_USER_TOKEN", "")
BIZ_ID = os.getenv("REAL_BIZ_ID", "")

def test_account_detail_shape():
    if not TOKEN or not BIZ_ID:
        print("SKIP: REAL_USER_TOKEN and REAL_BIZ_ID env not set")
        return
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/api/portal/account/{BIZ_ID}/detail",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
    assert body.get("code") == 0, f"got {body}"
    d = body["data"]
    for k in ("biz_id", "alias", "exchange", "ip_whitelist",
              "api_key_masked", "secret_key_masked",
              "total_assets", "futures_balance", "active", "equity_30d"):
        assert k in d, f"missing field: {k}"
    assert d["api_key_masked"].count("*") >= 4, "API key must be masked"
    assert isinstance(d["equity_30d"], list)

if __name__ == "__main__":
    test_account_detail_shape()
    print("PASS")
