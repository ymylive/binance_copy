#!/usr/bin/env python3
"""测试 DOM 抓取仓位数据"""
import asyncio
import json
import sys
sys.path.insert(0, '.')
from app.binance import BinanceSession

async def test():
    client = BinanceSession(
        cdp_url="http://127.0.0.1:9222",
        api_base="https://www.binance.com",
        auth_mode="cdp",
    )

    if not await client.connect():
        print(f"连接失败: {client.last_error}")
        return

    portfolio_id = "4826460952808447745"

    print("=== 测试 DOM 抓取仓位 ===")
    result = await client.fetch_positions_from_page(portfolio_id)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result.get("success") and result.get("positions"):
        print(f"\n找到 {len(result['positions'])} 个仓位:")
        for pos in result["positions"]:
            print(f"  - {pos.get('symbol')} {pos.get('side', 'LONG')} qty={pos.get('qty')} leverage={pos.get('leverage')}x entry={pos.get('entryPrice')}")

    await client.close()

if __name__ == "__main__":
    asyncio.run(test())
