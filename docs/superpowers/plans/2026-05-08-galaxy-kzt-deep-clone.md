# 银河量化 kzt 深度复刻 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `app/static/kzt.html` 的"智能跟单"4 个子菜单从都路由到一个 view 拆成 4 个独立 hash route，每个 1:1 对齐银河 `/trader /documentary /thirdPartyDocumentary /position`；同时给"账户管理"加单账户 hero 卡（IP/API Key 掩码/UID/合约余额/收益曲线）；最后起真 FastAPI 后端用 browser-use 拍三页验证集成。

**Architecture:** 后端只在 `app/api/routers/portal.py` 新增 1 个端点（单账户详情聚合），扩展 `app/api/main.py:list_projects` 返回字段；前端只动 `app/static/kzt.html`（已有银河骨架，加 hash router + 4 view + hero 卡）；不创建新文件，不动 `portal.css`，不动 `galaxy-tokens.css`。

**Tech Stack:** FastAPI 0.122 / Pydantic v2 / Vue-style vanilla JS (kzt.html inline `<script>`) / Chart.js 4 / browser-use CLI / pytest (existing project ad-hoc style)

**Visual reference:** `_design/galaxy_live/bu-1-dashboard.png` (首页) / `bu-2-accounts.png` (账户 hero 卡) / `bu-3-traders-plaza.png` (交易员广场) / `bu-3-positions.png` (持仓详情) / `bu-3-exchange-watchlist.png` & `bu-3-coin-watchlist.png` (两种自选)

**Spec:** `_design/galaxy_live/brand-spec.md` (色板、组件签名、几何) — 视觉唯一真相

---

## Phase 1 · 后端端点扩展

### Task 1.1: 扩展 `/api/projects` 输出 trader 卡片所需字段

**Files:**
- Modify: `app/api/main.py:1105-1114` (函数 `list_projects`)
- Modify: `app/services/state.py` (如果 ProjectConfig 在那；先 grep 定位)

银河 `/trader` 卡片每张需要：交易所标签、leader_id、显示名、avatar URL、近期收益百分比、迷你 sparkline 数据点。我们的 `ProjectConfig` 现在只有 `leader_id, portfolio_id, exchange, enabled` 这些。要加：
- `display_name` (str, 可选；默认 leader_id 前 8 位)
- `avatar_url` (str, 可选；默认 `https://api.dicebear.com/7.x/identicon/svg?seed=<leader_id>`)
- `total_pnl_pct` (float, 可选；从 poller state 取最近一次 PnL %)
- `sparkline` (List[float], 长度 ≤ 30；从 poller cache 取最近 30 个权益点的相对变化)

新字段都从 poller / state 计算得出，**不改 ProjectConfig 持久化 schema**。

- [ ] **Step 1: 定位 `state.list_projects` 与 poller 缓存接口**

```bash
grep -n "list_projects\|class ProjectConfig" app/services/state.py app/services/project_store.py 2>/dev/null
grep -n "def list_positions\|def list_current_positions\|equity_history\|pnl_history" app/services/poller/*.py 2>/dev/null
```

记下 `state.list_projects()` 返回类型 + poller 暴露的历史数据接口名。

- [ ] **Step 2: 写一个失败的 smoke test**

Create: `test_projects_extended.py` (项目根，与现有 test_api.py 同级)

```python
import json, urllib.request

def test_projects_returns_extended_fields():
    """项目列表必须含 avatar_url + sparkline + total_pnl_pct"""
    r = urllib.request.urlopen("http://127.0.0.1:8000/api/projects", timeout=2)
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
```

- [ ] **Step 3: 启动后端，运行 test，验证失败**

```bash
# 后台起 FastAPI（用项目现有 entrypoint）
PYTHONPATH=. uvicorn app.api.main:app --port 8000 --log-level warning &
sleep 3
python3 test_projects_extended.py
```

期望：`AssertionError: 缺 avatar_url`

- [ ] **Step 4: 在 `list_projects` 里组装新字段**

修改 `app/api/main.py:1105-1114`：

```python
@app.get("/api/projects")
async def list_projects() -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []
    for project in state.list_projects():
        payload = project.model_dump()
        payload["project_id"] = state.project_key(project)
        # === Galaxy trader-card extension ===
        leader_id = payload.get("leader_id") or payload.get("portfolio_id") or ""
        payload["display_name"] = payload.get("alias") or (str(leader_id)[:8] or "Anon")
        payload["avatar_url"] = (
            f"https://api.dicebear.com/7.x/identicon/svg?seed={leader_id}"
            if leader_id else ""
        )
        # PnL + sparkline 从 poller 拿；没有就给 [] 不要造数
        try:
            hist = state.poller.equity_history(payload["project_id"], limit=30)
        except (AttributeError, KeyError):
            hist = []
        payload["sparkline"] = [float(p) for p in hist] if hist else []
        if len(payload["sparkline"]) >= 2:
            base = payload["sparkline"][0] or 1.0
            payload["total_pnl_pct"] = round(
                (payload["sparkline"][-1] - base) / base * 100, 2
            )
        else:
            payload["total_pnl_pct"] = None
        items.append(payload)
    return items
```

如果 Step 1 发现 poller 没暴露 `equity_history(project_id, limit)`，先在 poller 类里加一个最简方法：返回 `self._equity_cache.get(project_id, [])[-limit:]` 或类似（具体实现按 poller 现有缓存结构来）。**绝不编造假数据**。

- [ ] **Step 5: 重启后端 + 重跑 test，验证通过**

```bash
pkill -f "uvicorn app.api.main" 2>/dev/null; sleep 1
PYTHONPATH=. uvicorn app.api.main:app --port 8000 --log-level warning &
sleep 3
python3 test_projects_extended.py
```

期望：`PASS`

- [ ] **Step 6: Commit**

```bash
git add app/api/main.py app/services/poller/*.py test_projects_extended.py
git commit -m "feat(api): /api/projects expose avatar_url + sparkline + total_pnl_pct for Galaxy trader cards"
```

---

### Task 1.2: 新增 `/api/portal/account/{biz_id}/detail` 单账户 hero 卡聚合端点

**Files:**
- Modify: `app/api/routers/portal.py` (在 `account/businesses/{biz_id}/bind-api-key` 附近 line 1252 后插入)
- Modify: `app/services/portal_store.py` (如果需要新增 `get_business_with_credentials(user_id, biz_id)`)

银河 `/account` hero 卡显示：账户类型 (账户1(标准)) + 激活开关 + IP 地址列表 + 交易所 + UID + 合约账户余额 + 总资产 + API Key/Secret Key (掩码) + 30 天收益曲线。

新端点返回结构：

```json
{
  "code": 0,
  "data": {
    "biz_id": "abc123",
    "alias": "账户3(标准)",
    "exchange": "Gate",
    "uid": "12345678",
    "ip_whitelist": ["8.211.140.223", "101.36.105.169"],
    "api_key_masked": "5b0a******2d56",
    "secret_key_masked": "8fb5******fd6f",
    "total_assets": 0.0,
    "futures_balance": 0.0,
    "active": true,
    "remaining_days": 54,
    "equity_30d": [{"ts": 1714521600000, "equity": 2000.0}, ...]
  }
}
```

- [ ] **Step 1: 定位 portal_store 现有 business 查询接口**

```bash
grep -n "def list_businesses\|def get_business\|business" app/services/portal_store.py | head -20
```

记下要用到的 row 字段名（biz_id, alias, exchange, api_key_enc, secret_key_enc, status, expire_at 等）。

- [ ] **Step 2: 写失败 test**

Create: `test_account_detail.py`

```python
import json, urllib.request

TOKEN = "REPLACE_WITH_REAL_LOGIN_TOKEN"  # 跑前手动登一次拿

def test_account_detail_shape():
    biz_id = "TEST_BIZ_ID"  # 跑前手动填一个真实的
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/api/portal/account/{biz_id}/detail",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    r = urllib.request.urlopen(req, timeout=3)
    body = json.loads(r.read())
    assert body.get("code") == 0
    d = body["data"]
    for k in ("biz_id", "alias", "exchange", "ip_whitelist",
              "api_key_masked", "secret_key_masked",
              "total_assets", "futures_balance", "active", "equity_30d"):
        assert k in d, f"missing {k}"
    assert d["api_key_masked"].count("*") >= 4, "API key 必须掩码"
    assert isinstance(d["equity_30d"], list)

if __name__ == "__main__":
    test_account_detail_shape()
    print("PASS")
```

- [ ] **Step 3: 启动后端 + 跑 test 验证 404**

```bash
pkill -f "uvicorn app.api.main" 2>/dev/null; sleep 1
PYTHONPATH=. uvicorn app.api.main:app --port 8000 --log-level warning &
sleep 3
python3 test_account_detail.py 2>&1 | head -5
```

期望：`HTTPError 404` 或类似（端点尚未注册）。

- [ ] **Step 4: 添加 portal_store 辅助函数**

如果 portal_store 缺 `get_business_by_id(user_id, biz_id)`（含 enc 字段），在 `app/services/portal_store.py` 加：

```python
def get_business_by_id(self, user_id: str, biz_id: str) -> Optional[Dict[str, Any]]:
    """返回完整 business row（含 enc 字段，调用方负责掩码）"""
    rows = self._read_businesses()
    for row in rows:
        if row.get("user_id") == user_id and row.get("biz_id") == biz_id:
            return dict(row)
    return None
```

掩码工具复用 main.py 已有的 `_mask_in_place`，必要时把它提到 `app/services/_mask.py` 共享。本任务**不重构**，直接在 portal.py 内联一个小函数：

```python
def _mask_key(s: Optional[str]) -> str:
    if not s or len(s) < 8:
        return "******"
    return s[:4] + "******" + s[-4:]
```

- [ ] **Step 5: 在 portal.py line 1252 之后注册端点**

```python
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
    biz = store.get_business_by_id(user["id"], biz_id)
    if not biz:
        return _err("business not found", code=2, status_code=200)
    # IP whitelist 来自配置；UID / 合约余额需要异步从 exchange adapter 拉
    # 第一版只返回静态字段，余额/UID 留 None,前端容忍
    api_key = biz.get("api_key") or biz.get("api_key_enc") or ""
    sec_key = biz.get("secret_key") or biz.get("secret_key_enc") or ""
    expire_ms = int(biz.get("expire_at") or 0)
    remaining_days = max(0, (expire_ms - int(time.time() * 1000)) // 86_400_000) if expire_ms else None
    # equity 30d 复用 dashboard/equity-curve 的逻辑
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
        "alias": biz.get("alias") or biz.get("name") or "账户",
        "exchange": biz.get("exchange") or "",
        "uid": biz.get("uid"),
        "ip_whitelist": biz.get("ip_whitelist") or [],
        "api_key_masked": _mask_key(api_key),
        "secret_key_masked": _mask_key(sec_key),
        "total_assets": biz.get("total_assets"),
        "futures_balance": biz.get("futures_balance"),
        "active": bool(biz.get("active") or biz.get("status") == "active"),
        "remaining_days": remaining_days,
        "equity_30d": equity_30d,
    })
```

字段缺失全部用 None / 空 list / 空字符串，**绝不伪造**。

- [ ] **Step 6: 重启 + 跑 test 验证 PASS**

```bash
pkill -f "uvicorn app.api.main" 2>/dev/null; sleep 1
PYTHONPATH=. uvicorn app.api.main:app --port 8000 --log-level warning &
sleep 3
# 注意：先用真账号登一次拿 token + biz_id 填进 test_account_detail.py
python3 test_account_detail.py
```

期望：`PASS`

- [ ] **Step 7: Commit**

```bash
git add app/api/routers/portal.py app/services/portal_store.py test_account_detail.py
git commit -m "feat(portal): /api/portal/account/{biz_id}/detail aggregates IP/UID/balance/equity for Galaxy hero card"
```

---

## Phase 2 · 前端 kzt.html 4-view 拆分 + Hero 卡

### Task 2.1: 给 kzt.html 加 hash router + 4 子菜单独立 view

**Files:**
- Modify: `app/static/kzt.html` (重做左侧 sidebar 智能跟单子菜单的 routing + 主区 view 切换)

银河左侧菜单展开 4 个子项：交易员广场 / 交易所自选 / 币Coin自选 / 持仓详情。每点一个切到对应 view，路由到 hash：
- `#traders-plaza` → 调 `/api/projects` 渲染 4 列网格卡片（avatar + sparkline + 收益% + 跟单按钮）
- `#exchange-watch` → 调 `/api/projects?source=exchange` 或前端按 `exchange ∈ {binance,okx,gate,bitget}` 过滤
- `#coin-watch` → 同样但 `exchange ∈ {bicoin,smart_money,onchain,hyperliquid}` 过滤
- `#positions` → 调 `/api/positions` 渲染 9 列表格（沿用现有 `gq-data-table`）

- [ ] **Step 1: 在 kzt.html 找到现有 `<script>` 路由处，改成扩展的 hashchange 监听**

定位现有路由代码：

```bash
grep -nE "addEventListener\\('hashchange'|location\\.hash|switchView|renderView" app/static/kzt.html | head -10
```

把现有"智能跟单 → 单一 view"逻辑改为：

```javascript
const VIEWS = {
  'home': renderHome,
  'accounts': renderAccounts,
  'traders-plaza': renderTradersPlaza,
  'exchange-watch': renderExchangeWatch,
  'coin-watch': renderCoinWatch,
  'positions': renderPositions,
  'system': renderSystem,
};

function route() {
  const hash = (location.hash || '#home').slice(1);
  const fn = VIEWS[hash] || VIEWS['home'];
  document.querySelectorAll('.gq-view').forEach(el => el.style.display = 'none');
  const target = document.getElementById(`view-${hash}`);
  if (target) target.style.display = '';
  // 同步左侧菜单 active 态
  document.querySelectorAll('.gq-menu-item').forEach(el => {
    el.classList.toggle('active', el.dataset.view === hash);
  });
  fn();
}
addEventListener('hashchange', route);
addEventListener('DOMContentLoaded', route);
```

- [ ] **Step 2: 在 sidebar 4 个子菜单 `<li>` 加 `data-view` 属性 + 各自 `href="#xxx"`**

```html
<li class="gq-submenu-item" data-view="traders-plaza">
  <a href="#traders-plaza">交易员广场</a>
</li>
<li class="gq-submenu-item" data-view="exchange-watch">
  <a href="#exchange-watch">交易所自选</a>
</li>
<li class="gq-submenu-item" data-view="coin-watch">
  <a href="#coin-watch">币Coin自选</a>
</li>
<li class="gq-submenu-item" data-view="positions">
  <a href="#positions">持仓详情</a>
</li>
```

- [ ] **Step 3: 主内容区添加 4 个 `<section class="gq-view" id="view-xxx">`**

每个 section 默认 `display:none`，被 router 按 hash 激活。每个 section 内部结构：

```html
<section class="gq-view" id="view-traders-plaza" style="display:none;">
  <h1 class="gq-page-title">交易员广场</h1>
  <div class="gq-card gq-banner-warn" id="tp-banner">
    <span>请选择下单账户：<strong id="tp-account-name">--</strong></span>
  </div>
  <div class="gq-tabs" id="tp-exchange-filter">
    <button class="gq-tab active" data-filter="all">全部</button>
    <button class="gq-tab" data-filter="binance">Binance</button>
    <button class="gq-tab" data-filter="okx">OKX</button>
    <button class="gq-tab" data-filter="gate">Gate</button>
    <button class="gq-tab" data-filter="bitget">Bitget</button>
  </div>
  <div class="gq-trader-grid" id="tp-grid">
    <div class="gq-empty">加载中…</div>
  </div>
</section>

<section class="gq-view" id="view-exchange-watch" style="display:none;">
  <h1 class="gq-page-title">交易所自选</h1>
  <div class="gq-card"><div class="gq-empty">暂无自选</div></div>
</section>

<section class="gq-view" id="view-coin-watch" style="display:none;">
  <h1 class="gq-page-title">币Coin自选</h1>
  <div class="gq-card"><div class="gq-empty">暂无自选</div></div>
</section>

<section class="gq-view" id="view-positions" style="display:none;">
  <h1 class="gq-page-title">持仓详情</h1>
  <div class="gq-card">
    <div class="gq-tabs-underline">
      <button class="gq-tab-underline active" data-tab="positions">持仓列表</button>
      <button class="gq-tab-underline" data-tab="orders">操作记录</button>
      <button class="gq-tab-underline" data-tab="analysis">跟单分析</button>
    </div>
    <table class="gq-data-table" id="positions-table">
      <thead>
        <tr>
          <th>交易对(0)</th><th>数量(张)</th><th>开仓均价</th>
          <th>标记价格</th><th>强平价格</th><th>保证金</th>
          <th>保证金率</th><th>已实现盈亏</th><th>盈亏及回报率</th>
        </tr>
      </thead>
      <tbody><tr><td colspan="9" class="gq-empty">暂无数据</td></tr></tbody>
    </table>
  </div>
</section>
```

`.gq-trader-grid` 和 `.gq-banner-warn` 在 galaxy-tokens.css 已有（Agent A Phase 1 写的）；如果没有就在 head 内联补一段（kzt.html 自包含原则）。

- [ ] **Step 4: 实现 4 个 render 函数**

```javascript
async function renderTradersPlaza() {
  const grid = document.getElementById('tp-grid');
  grid.innerHTML = '<div class="gq-empty">加载中…</div>';
  try {
    const r = await fetch('/api/projects');
    const items = await r.json();
    if (!items.length) {
      grid.innerHTML = '<div class="gq-empty">暂无交易员</div>';
      return;
    }
    grid.innerHTML = items.map(p => `
      <div class="gq-trader-card" data-exchange="${p.exchange}">
        <div class="gq-trader-head">
          <span class="gq-pill-info">${p.exchange.toUpperCase()}</span>
          <img class="gq-trader-avatar" src="${p.avatar_url}" alt="${p.display_name}" />
          <span class="gq-trader-name">${p.display_name}</span>
        </div>
        <svg class="gq-trader-spark" viewBox="0 0 100 30">${sparklinePath(p.sparkline)}</svg>
        <div class="gq-trader-pnl ${(p.total_pnl_pct||0) >= 0 ? 'gq-up' : 'gq-down'}">
          ${p.total_pnl_pct == null ? '--' : (p.total_pnl_pct > 0 ? '+' : '') + p.total_pnl_pct + '%'}
        </div>
        <button class="gq-btn ${p.enabled ? 'gq-btn-ghost' : 'gq-btn-primary'}"
                data-action="toggle" data-id="${p.project_id}">
          ${p.enabled ? '已跟单' : '跟单'}
        </button>
      </div>
    `).join('');
    grid.querySelectorAll('[data-action="toggle"]').forEach(btn => {
      btn.addEventListener('click', () => toggleProject(btn.dataset.id, !btn.classList.contains('gq-btn-ghost')));
    });
  } catch (e) {
    grid.innerHTML = `<div class="gq-empty">加载失败：${e.message}</div>`;
  }
}

function sparklinePath(points) {
  if (!points || points.length < 2) return '';
  const min = Math.min(...points), max = Math.max(...points);
  const range = max - min || 1;
  const pts = points.map((v, i) => {
    const x = (i / (points.length - 1)) * 100;
    const y = 30 - ((v - min) / range) * 30;
    return `${x},${y}`;
  });
  const pos = points[points.length - 1] >= points[0];
  const stroke = pos ? 'var(--gq-up)' : 'var(--gq-down)';
  return `<polyline points="${pts.join(' ')}" fill="none" stroke="${stroke}" stroke-width="1.5" />`;
}

async function renderExchangeWatch() {
  const wrap = document.querySelector('#view-exchange-watch .gq-card');
  // 复用 /api/projects 但前端过滤
  const r = await fetch('/api/projects');
  const items = (await r.json()).filter(p =>
    ['binance', 'okx', 'gate', 'bitget'].includes(p.exchange)
  );
  if (!items.length) {
    wrap.innerHTML = '<div class="gq-empty">暂无自选</div>';
    return;
  }
  wrap.innerHTML = `<table class="gq-data-table">
    <thead><tr><th>交易所</th><th>交易员</th><th>状态</th><th>操作</th></tr></thead>
    <tbody>${items.map(p => `
      <tr>
        <td><span class="gq-pill-info">${p.exchange.toUpperCase()}</span></td>
        <td>${p.display_name}</td>
        <td>${p.enabled ? '<span class="gq-pill-up">跟随中</span>' : '<span class="gq-pill-info">已暂停</span>'}</td>
        <td><button class="gq-btn-ghost" data-action="toggle" data-id="${p.project_id}">${p.enabled ? '暂停' : '启用'}</button></td>
      </tr>
    `).join('')}</tbody>
  </table>`;
}

async function renderCoinWatch() {
  const wrap = document.querySelector('#view-coin-watch .gq-card');
  const r = await fetch('/api/projects');
  const items = (await r.json()).filter(p =>
    ['bicoin', 'smart_money', 'onchain', 'hyperliquid'].includes(p.exchange)
  );
  if (!items.length) {
    wrap.innerHTML = '<div class="gq-empty">暂无自选</div>';
    return;
  }
  wrap.innerHTML = `<table class="gq-data-table">
    <thead><tr><th>来源</th><th>地址 / 标识</th><th>状态</th></tr></thead>
    <tbody>${items.map(p => `
      <tr>
        <td><span class="gq-pill-info">${p.exchange}</span></td>
        <td><code>${(p.leader_id || '').slice(0,16)}…</code></td>
        <td>${p.enabled ? '<span class="gq-pill-up">监听中</span>' : '<span class="gq-pill-info">已暂停</span>'}</td>
      </tr>
    `).join('')}</tbody>
  </table>`;
}

async function renderPositions() {
  const tbody = document.querySelector('#positions-table tbody');
  tbody.innerHTML = '<tr><td colspan="9" class="gq-empty">加载中…</td></tr>';
  try {
    const r = await fetch('/api/positions');
    const rows = await r.json();
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="gq-empty">暂无数据</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(p => `
      <tr>
        <td>${p.symbol}<span class="gq-text-3">(${p.side})</span></td>
        <td>${p.qty ?? '--'}</td>
        <td>${p.entry_price ?? '--'}</td>
        <td>${p.mark_price ?? '--'}</td>
        <td>${p.liq_price ?? '--'}</td>
        <td>${p.margin ?? '--'}</td>
        <td>${p.margin_ratio == null ? '--' : (p.margin_ratio*100).toFixed(2)+'%'}</td>
        <td class="${(p.realized_pnl||0) >= 0 ? 'gq-up' : 'gq-down'}">${p.realized_pnl ?? '--'}</td>
        <td class="${(p.pnl_pct||0) >= 0 ? 'gq-up' : 'gq-down'}">${p.pnl_pct == null ? '--' : (p.pnl_pct > 0 ? '+' : '') + p.pnl_pct + '%'}</td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" class="gq-empty">加载失败：${e.message}</td></tr>`;
  }
}
```

- [ ] **Step 5: 用 browser-use 验证 4 路由都能切换**

```bash
# 后端要在跑（前面 task 已起）
# 注 fake token（kzt 有 auth gate）
browser-use close 2>/dev/null
browser-use open "http://localhost:8000/static/kzt.html" && sleep 1
browser-use eval "localStorage.setItem('appToken','fake-test'); location.reload(); 'ok'"
sleep 3
for hash in traders-plaza exchange-watch coin-watch positions; do
  browser-use eval "location.hash = '#${hash}'; 'set'"
  sleep 2
  browser-use screenshot "_design/galaxy_live/our-kzt-${hash}.png"
  TITLE=$(browser-use eval "document.querySelector('.gq-view:not([style*=none]) .gq-page-title')?.textContent" 2>&1 | tail -1)
  echo "${hash}: ${TITLE}"
done
```

期望每行打印 view 的中文标题，4 张截图存到磁盘且每张都跟之前的不一样（用 `wc -c` 比对）。

- [ ] **Step 6: Commit**

```bash
git add app/static/kzt.html
git commit -m "feat(kzt): split 智能跟单 submenu into 4 distinct hash routes (traders-plaza/exchange-watch/coin-watch/positions)"
```

---

### Task 2.2: 给 #accounts 加单账户 hero 卡（点击 tab 切账户）

**Files:**
- Modify: `app/static/kzt.html` (#view-accounts section)

银河 `/account` 顶部是账户 tabs（"账户1(标准) / 账户2(标准) / 账户3(标准)"），点击切换显示该账户的 hero 卡 + 30 天收益曲线（用 Chart.js 渲染薄荷绿单线）。

- [ ] **Step 1: 在 #view-accounts 写 tabs + hero 占位 + 图表 canvas**

```html
<section class="gq-view" id="view-accounts" style="display:none;">
  <h1 class="gq-page-title">账户管理</h1>
  <div class="gq-tabs" id="acc-tabs">
    <div class="gq-empty">加载账户中…</div>
  </div>
  <div class="gq-card gq-account-hero" id="acc-hero" style="display:none;">
    <div class="gq-hero-row">
      <span>当前账户类型：</span>
      <strong id="acc-alias">--</strong>
      <span>激活</span>
      <label class="gq-switch"><input type="checkbox" id="acc-active" /><span></span></label>
    </div>
    <div class="gq-hero-row">
      <span>IP地址：</span>
      <span id="acc-ips" class="gq-link">--</span>
    </div>
    <div class="gq-hero-row">
      <span>交易所：</span><strong id="acc-exchange">--</strong>
      <span>UID：</span><strong id="acc-uid">--</strong>
    </div>
    <div class="gq-hero-row">
      <span>合约账户：</span><strong id="acc-fut">--</strong>
      <span>账户总资产：</span><strong id="acc-total">--</strong>
      <button class="gq-btn-ghost">修改杠杆</button>
      <button class="gq-btn-primary">编辑Apikey</button>
      <button class="gq-btn-danger">删除当前账户</button>
    </div>
    <div class="gq-hero-row gq-text-3">
      <span>API Key:</span><code id="acc-api">--</code>
      <span>Secret Key:</span><code id="acc-sec">--</code>
    </div>
  </div>
  <div class="gq-card" id="acc-equity-wrap" style="display:none;">
    <div class="gq-card-head">
      <h3>收益曲线 <small class="gq-text-3 gq-up" id="acc-equity-summary"></small></h3>
      <div class="gq-tabs-underline">
        <button class="gq-tab-underline active">收益曲线</button>
        <button class="gq-tab-underline">盈亏日历</button>
      </div>
    </div>
    <canvas id="acc-equity-chart" height="280"></canvas>
  </div>
</section>
```

- [ ] **Step 2: 实现 renderAccounts**

```javascript
let _accChart;
async function renderAccounts() {
  const tabsBox = document.getElementById('acc-tabs');
  tabsBox.innerHTML = '<div class="gq-empty">加载账户中…</div>';
  try {
    const r = await fetch('/api/portal/account/businesses?effective=true', { credentials: 'include' });
    const env = await r.json();
    const list = (env.data || env || []);
    if (!list.length) {
      tabsBox.innerHTML = '<div class="gq-empty">尚无账户，请先购买套餐绑定 API Key</div>';
      return;
    }
    tabsBox.innerHTML = list.map((b, i) =>
      `<button class="gq-tab ${i === 0 ? 'active' : ''}" data-biz="${b.biz_id}">${b.alias || `账户${i+1}(标准)`}</button>`
    ).join('');
    tabsBox.querySelectorAll('[data-biz]').forEach(btn => {
      btn.addEventListener('click', () => {
        tabsBox.querySelectorAll('[data-biz]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        loadAccountDetail(btn.dataset.biz);
      });
    });
    loadAccountDetail(list[0].biz_id);
  } catch (e) {
    tabsBox.innerHTML = `<div class="gq-empty">加载失败：${e.message}</div>`;
  }
}

async function loadAccountDetail(biz_id) {
  const hero = document.getElementById('acc-hero');
  const wrap = document.getElementById('acc-equity-wrap');
  hero.style.display = 'none';
  wrap.style.display = 'none';
  try {
    const r = await fetch(`/api/portal/account/${encodeURIComponent(biz_id)}/detail`, { credentials: 'include' });
    const env = await r.json();
    if (env.code !== 0) {
      hero.style.display = '';
      hero.innerHTML = `<div class="gq-empty">${env.msg || '加载失败'}</div>`;
      return;
    }
    const d = env.data;
    document.getElementById('acc-alias').textContent = d.alias;
    document.getElementById('acc-active').checked = !!d.active;
    document.getElementById('acc-ips').textContent = (d.ip_whitelist || []).join(', ') || '--';
    document.getElementById('acc-exchange').textContent = d.exchange || '--';
    document.getElementById('acc-uid').textContent = d.uid || '--';
    document.getElementById('acc-fut').textContent = (d.futures_balance != null) ? d.futures_balance : '--';
    document.getElementById('acc-total').textContent = (d.total_assets != null) ? d.total_assets : '--';
    document.getElementById('acc-api').textContent = d.api_key_masked || '--';
    document.getElementById('acc-sec').textContent = d.secret_key_masked || '--';
    hero.style.display = '';
    if ((d.equity_30d || []).length) {
      wrap.style.display = '';
      drawEquityChart(d.equity_30d);
    }
  } catch (e) {
    hero.style.display = '';
    hero.innerHTML = `<div class="gq-empty">加载失败：${e.message}</div>`;
  }
}

function drawEquityChart(points) {
  const ctx = document.getElementById('acc-equity-chart').getContext('2d');
  const labels = points.map(p => new Date(p.ts).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }));
  const data = points.map(p => p.equity);
  if (_accChart) _accChart.destroy();
  _accChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data,
        borderColor: 'rgb(58, 203, 190)',
        backgroundColor: 'rgba(58, 203, 190, 0.18)',
        fill: true,
        tension: 0.35,
        pointRadius: 0,
      }],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.05)' } },
      },
    },
  });
  // summary
  const first = data[0] || 0, last = data[data.length-1] || 0;
  const pct = first ? ((last - first) / first * 100).toFixed(2) : 0;
  const el = document.getElementById('acc-equity-summary');
  el.textContent = `(${pct >= 0 ? '+' : ''}${pct}% 近 30 日)`;
  el.classList.toggle('gq-up', pct >= 0);
  el.classList.toggle('gq-down', pct < 0);
}
```

- [ ] **Step 3: 用 browser-use 验证 hero 卡渲染**

```bash
browser-use close 2>/dev/null
browser-use open "http://localhost:8000/static/kzt.html"
sleep 1
browser-use eval "localStorage.setItem('appToken','fake-test'); location.hash='#accounts'; location.reload(); 'ok'"
sleep 3
browser-use screenshot _design/galaxy_live/our-kzt-accounts.png
ls -la _design/galaxy_live/our-kzt-accounts.png
```

期望产出大于 50KB（说明渲染了内容，不是 404 页）。

- [ ] **Step 4: Commit**

```bash
git add app/static/kzt.html
git commit -m "feat(kzt): account hero card with tabs + equity chart wired to /api/portal/account/{biz_id}/detail"
```

---

## Phase 3 · 集成验证

### Task 3.1: 起真后端，全程跑过 admin/kzt/console 三页

**Files:**
- Read only: `deploy_vps.py`, `app/api/main.py`, runtime config

- [ ] **Step 1: 阅 `deploy_vps.py` 找 dev 启动指令**

```bash
grep -nE "uvicorn|run_app|main:app|--reload" deploy_vps.py | head -10
```

记下 host/port + 任何必填 env vars (DB / redis / 加密 key)。

- [ ] **Step 2: 启动后端**

```bash
pkill -f "uvicorn app.api.main" 2>/dev/null; sleep 1
PYTHONPATH=. uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --log-level info > /tmp/fastapi.log 2>&1 &
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/static/kzt.html
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/static/admin.html
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/static/console.html
curl -s http://127.0.0.1:8000/api/projects | head -c 200
tail -20 /tmp/fastapi.log
```

期望：3 个 200 + `/api/projects` 返回 JSON list（即使空）+ log 无错误。

- [ ] **Step 3: 用 browser-use 拍 9 张集成截图**

```bash
TOKEN_FAKE="fake-visual-only"  # admin/kzt 都需要 token，但后端 401 就过 hero card；视觉验证够用
browser-use close 2>/dev/null

for page in admin.html kzt.html console.html; do
  browser-use open "http://127.0.0.1:8000/static/${page}"
  sleep 2
  browser-use eval "localStorage.setItem('appToken', '${TOKEN_FAKE}'); location.reload(); 'reloaded'"
  sleep 3
  browser-use screenshot "_design/galaxy_live/integ-${page%.html}.png"
  browser-use screenshot "_design/galaxy_live/integ-${page%.html}-full.png" --full
done

# kzt 各 view
browser-use open "http://127.0.0.1:8000/static/kzt.html"
sleep 1
browser-use eval "localStorage.setItem('appToken','${TOKEN_FAKE}'); 'set'"
for h in home accounts traders-plaza positions system; do
  browser-use eval "location.hash='#${h}'; 'set'"
  sleep 2
  browser-use screenshot "_design/galaxy_live/integ-kzt-${h}.png"
done

ls -la _design/galaxy_live/integ-*.png
```

- [ ] **Step 4: 对比银河实拍**

```bash
echo "=== 大小对比 ==="
for f in dashboard accounts traders-plaza positions system; do
  bu=$(stat -f '%z' _design/galaxy_live/bu-1-dashboard.png 2>/dev/null || stat -c '%s' _design/galaxy_live/bu-1-dashboard.png)
  ours=$(stat -f '%z' "_design/galaxy_live/integ-kzt-${f}.png" 2>/dev/null || echo missing)
  echo "kzt #${f}: 银河 ${bu}B vs 我们 ${ours}B"
done
```

人工逐张 Read 9 张图，记录视觉差距：哪个 view 缺哪些组件、哪里间距不一致、哪里色值偏差。

- [ ] **Step 5: 把差距整理到报告文件**

Create: `_design/galaxy_live/integration-diff-2026-05-08.md`

格式：每页一段，按 "已对齐 / 待补 / 偏差" 三块写。无差距就空。

- [ ] **Step 6: Commit**

```bash
git add _design/galaxy_live/integ-*.png _design/galaxy_live/integration-diff-2026-05-08.md
git commit -m "test(integration): captured 8 integ screenshots vs Galaxy bu-* recon, logged visual diffs"
```

- [ ] **Step 7: 关后端**

```bash
pkill -f "uvicorn app.api.main" 2>/dev/null
```

---

## 自检清单

- [x] 每个 task 路径精确（不写 "the file"）
- [x] 每段代码完整（没有 "// ... rest of code"）
- [x] 命令带预期输出（"期望 PASS / 200 / 大于 50KB"）
- [x] 不动 `portal.css` ✓
- [x] 不动 `galaxy-tokens.css` ✓
- [x] 所有现有 fetch endpoint 行为不变 ✓（只新增端点 + 扩展返回字段）
- [x] 前端样式只用 `.gq-*` 类 / `--gq-*` 变量 ✓

## 不确定点（执行 agent 可能要回头问）

1. **`state.poller.equity_history(project_id, limit)` 不一定存在** —— Step 1.1.1 grep 结果决定是直接调用还是先在 poller 加方法；如果 poller 完全没缓存历史 PnL，回退方案是直接给 `sparkline: []` + `total_pnl_pct: None`，前端容忍空。

2. **portal_store 的 business row 字段命名** 可能与 `_mask_in_place` 期望不一致；Step 1.2.1 grep 后再适配 `_mask_key`。

3. **`/api/positions` 返回字段** 可能不是 `{symbol, qty, entry_price, mark_price, ...}` 这种命名；Step 2.1.4 实现前先 `curl /api/positions` 看真实 shape，按它适配 renderPositions 的字段读取。

4. **后端启动可能依赖加密 key / runtime 文件** —— Task 3.1.1 阅 `deploy_vps.py` 时如果发现需要 `ENCRYPT_KEY` 等 env，先在 `/tmp/.fastapi.env` 设好再跑 uvicorn。

任何一处不确定停下问 dispatcher，**绝不编造数据**。
