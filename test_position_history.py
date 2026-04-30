#!/usr/bin/env python3
import asyncio
import json
import sys
sys.path.insert(0, '.')
from app.exchanges.binance import BinanceSession

async def test():
    client = BinanceSession(
        cdp_url="http://127.0.0.1:9222",
        api_base="https://www.binance.com",
        auth_mode="cdp",
        cookie_path="cookies.json",
    )
    if not await client.connect():
        print(f"connect failed: {client.last_error}")
        return

    portfolio_id = "4826460952808447745"

    print("=== Position History (DOM/CDP) ===")
    history = await client.fetch_position_history_from_page(portfolio_id, 1, 200)

    if history.get("data"):
        items = history["data"].get("list", [])
        print(f"Total items: {len(items)}")

        opening = [p for p in items if p.get("status") in {"OPENING", "Holding"}]
        print(f"OPENING positions: {len(opening)}")

        if opening:
            print("\nOpening positions:")
            for p in opening:
                print(
                    f"  - {p.get('symbol')} {p.get('side')} qty={p.get('qty') or p.get('closedVolume')}"
                )
        else:
            print("\nNo OPENING positions found")
            print("Sample items (first 3):")
            for p in items[:3]:
                print(f"  - {p.get('symbol')} status={p.get('status')} qty={p.get('closedVolume')}")
    else:
        print(f"Error: {json.dumps(history, indent=2)[:500]}")

    await client.close()

if __name__ == "__main__":
    asyncio.run(test())
