#!/usr/bin/env python3
import asyncio
import json
import sys
sys.path.insert(0, '.')
from app.binance import BinanceSession

async def test():
    client = BinanceSession(
        cdp_url="http://127.0.0.1:9222",
        api_base="https://www.binance.com",
        auth_mode="cookie",
        cookie_path="cookies.json"
    )
    client._load_cookie_jar()

    portfolio_id = "4826460952808447745"

    # 测试 fetch_order_history
    print("=== Order History API ===")
    end_time = int(asyncio.get_event_loop().time() * 1000) + 8 * 3600 * 1000
    start_time = end_time - 24 * 3600 * 1000  # 过去24小时

    history = await client.fetch_order_history(portfolio_id, start_time, end_time, 20)
    if history.get("data"):
        items = history["data"].get("list", [])
        print(f"Found {len(items)} orders in last 24h")
        if items:
            print("Recent orders:")
            for item in items[:5]:
                print(f"  - {item.get('symbol')} {item.get('side')} qty={item.get('qty')} time={item.get('time')}")
    else:
        print(f"Response: {json.dumps(history, indent=2)[:500]}")

    # 测试 position-history API
    print("\n=== Position History API ===")
    pos_history = await client.fetch_position_history(portfolio_id, "OPENING", 20)
    if pos_history.get("data"):
        items = pos_history["data"].get("list", [])
        opening = [p for p in items if p.get("status") == "OPENING"]
        print(f"Total: {len(items)}, OPENING: {len(opening)}")
        if opening:
            print("Opening positions:")
            for p in opening[:5]:
                print(f"  - {p.get('symbol')} {p.get('side')} qty={p.get('qty')}")
    else:
        print(f"Response: {json.dumps(pos_history, indent=2)[:500]}")

    await client.close()

if __name__ == "__main__":
    asyncio.run(test())
