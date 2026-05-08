import json, os, pathlib, urllib.request

def _token():
    p = pathlib.Path(__file__).parent / "runtime" / "api_token.txt"
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return os.getenv("BINANCE_COPY_API_TOKEN", "").strip()

def test_projects_returns_extended_fields():
    """项目列表必须含 avatar_url + sparkline + total_pnl_pct"""
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/projects",
        headers={"Authorization": f"Bearer {_token()}"},
    )
    r = urllib.request.urlopen(req, timeout=2)
    items = json.loads(r.read())
    assert isinstance(items, list)
    if not items:
        return  # 空账户跳过
    p = items[0]
    assert "avatar_url" in p, "缺 avatar_url"
    assert "sparkline" in p, "缺 sparkline"
    assert "total_pnl_pct" in p, "缺 total_pnl_pct"
    assert isinstance(p["sparkline"], list)
    assert all(isinstance(x, (int, float)) for x in p["sparkline"])

if __name__ == "__main__":
    test_projects_returns_extended_fields()
    print("PASS")
