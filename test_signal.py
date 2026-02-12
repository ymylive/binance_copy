"""
模拟信号测试脚本
每10秒进行一次开仓、加仓、减仓、平仓的循环
使用BTCUSDT作为测试币种，通过 /api/simulate 接口发送信号
"""
import asyncio
import httpx

# 测试配置
BASE_URL = "https://cornna.dpdns.org"
SYMBOL = "BTCUSDT"
INTERVAL = 10  # 每个阶段间隔秒数

# 测试用例 - 通过 simulate API 发送
TEST_CASES = [
    {"phase": "开仓", "action": "open", "side": "BUY", "position_side": "LONG", "notional_usd": 1000},
    {"phase": "加仓", "action": "add", "side": "BUY", "position_side": "LONG", "notional_usd": 500},
    {"phase": "减仓", "action": "reduce", "side": "SELL", "position_side": "LONG", "notional_usd": 300},
    {"phase": "平仓", "action": "close", "side": "SELL", "position_side": "LONG", "notional_usd": 1200},
]


async def get_status():
    """获取系统状态"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}/api/status")
        return resp.json()


async def send_simulate(case: dict, execute: bool = True):
    """发送模拟信号"""
    payload = {
        "symbol": SYMBOL,
        "side": case["side"],
        "position_side": case["position_side"],
        "notional_usd": case["notional_usd"],
        "action": case["action"],
        "execute": execute,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE_URL}/api/simulate", json=payload)
        return resp.json()


async def get_events(limit: int = 5):
    """获取最近事件"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}/api/events?limit={limit}")
        return resp.json()


async def run_test():
    """运行测试循环"""
    print("\n" + "="*60)
    print("模拟信号测试 - BTCUSDT")
    print(f"每 {INTERVAL} 秒执行一个阶段")
    print("="*60)

    # 检查系统状态
    try:
        status = await get_status()
        print(f"\n系统状态: {'已连接' if status.get('connected') else '未连接'}")
        print(f"运行中项目: {list(status.get('running', {}).keys())}")
    except Exception as e:
        print(f"获取状态失败: {e}")
        return

    for i, case in enumerate(TEST_CASES):
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(TEST_CASES)}] {case['phase']}")
        print(f"{'='*60}")
        print(f"  动作: {case['action']}")
        print(f"  方向: {case['side']} {case['position_side']}")
        print(f"  金额: {case['notional_usd']} USDT")

        try:
            result = await send_simulate(case, execute=True)
            if result.get("ok"):
                event = result.get("event", {})
                print(f"\n  [OK] 信号已发送")
                print(f"    Symbol: {event.get('symbol')}")
                print(f"    Price: {event.get('avg_price', 0):.2f}")
                print(f"    Follower Qty: {event.get('follower_qty', 0):.8f}")
                print(f"    Notional: {event.get('follower_notional', 0):.2f} USDT")
                exec_result = result.get("result")
                if exec_result:
                    print(f"    执行结果: {exec_result.get('status', 'unknown')}")
            else:
                print(f"\n  [FAIL] 发送失败: {result}")
        except Exception as e:
            print(f"\n  [ERROR] 错误: {e}")

        if i < len(TEST_CASES) - 1:
            print(f"\n等待 {INTERVAL} 秒...")
            await asyncio.sleep(INTERVAL)

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)

    # 显示最近事件
    try:
        events = await get_events(5)
        print("\n最近事件:")
        for e in events[:5]:
            print(f"  {e.get('action')} {e.get('symbol')} {e.get('side')} qty={e.get('follower_qty', 0):.8f}")
    except Exception as ex:
        print(f"获取事件失败: {ex}")


if __name__ == "__main__":
    asyncio.run(run_test())
