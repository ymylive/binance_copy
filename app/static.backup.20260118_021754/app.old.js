const statusConnected = document.getElementById("status-connected");
const statusDot = document.getElementById("status-dot");
const statusError = document.getElementById("status-error");
const statusApiBase = document.getElementById("status-api-base");
const statusTradeBase = document.getElementById("status-trade-base");
const statusApiText = document.getElementById("status-api");
const statusAuthText = document.getElementById("status-auth");
const statusCookieText = document.getElementById("status-cookie");
const statusTradeText = document.getElementById("status-trade");
const connectBtn = document.getElementById("connect-btn");
const projectsTable = document.getElementById("projects-table");
const positionsTable = document.getElementById("positions-table");
const positionsPagination = document.getElementById("positions-pagination");
const leaderPositionsTable = document.getElementById("leader-positions-table");
const logsTable = document.getElementById("events-table");
const logsPagination = document.getElementById("logs-pagination");
const historyTable = document.getElementById("history-table");
const historyPagination = document.getElementById("history-pagination");
const actionAccountSelect = document.getElementById("action-account-select");
const positionAccountSelect = document.getElementById("position-account-select");
const accountPositionsTable = document.getElementById("account-positions-table");
const projectForm = document.getElementById("project-form");
const envForm = document.getElementById("env-form");
const resetFormBtn = document.getElementById("reset-form");
const projectFeedback = document.getElementById("project-feedback");
const envFeedback = document.getElementById("env-feedback");
const cookieForm = document.getElementById("cookie-form");
const cookieFileInput = document.getElementById("cookie-file");
const cookieFeedback = document.getElementById("cookie-feedback");
const actionCards = document.querySelectorAll(".action-card");
const tradeBaseUrlInput = document.getElementById("trade-base-url");
const tradeEnabledInput = document.getElementById("trade-enabled");
const tradeAccountSelect = document.getElementById("trade-account-select");
const tradeAccountNameInput = document.getElementById("trade-account-name");
const tradeAccountEnabledInput = document.getElementById("trade-account-enabled");
const addTradeAccountBtn = document.getElementById("add-trade-account");
const removeTradeAccountBtn = document.getElementById("remove-trade-account");
const tradeApiKeyInput = document.getElementById("trade-api-key");
const tradeApiSecretInput = document.getElementById("trade-api-secret");
const tradeRecvWindowInput = document.getElementById("trade-recv-window");
const tradeTimeoutInput = document.getElementById("trade-timeout-ms");
const tradeMinQtyInput = document.getElementById("trade-min-qty");
const tradeMaxQtyInput = document.getElementById("trade-max-qty");
const tradeOrderTypeSelect = document.getElementById("trade-order-type");
const tradePriceSourceSelect = document.getElementById("trade-price-source");
const tradeUsdtOrderModeInput = document.getElementById("trade-usdt-order-mode");
const tradeSendPositionSideInput = document.getElementById("trade-send-position-side");
const tradeTimeSyncInput = document.getElementById("trade-time-sync");
const tradeTimeSyncIntervalInput = document.getElementById("trade-time-sync-interval");
const tradeAutoAdjustQtyInput = document.getElementById("trade-auto-adjust-qty");
const tradeMinNotionalModeSelect = document.getElementById("trade-min-notional-mode");
const tradeExchangeInfoTtlInput = document.getElementById("trade-exchange-info-ttl");
const tradePriceTtlInput = document.getElementById("trade-price-ttl");
const tradeAutoPositionModeInput = document.getElementById("trade-auto-position-mode");
const tradePositionModeTtlInput = document.getElementById("trade-position-mode-ttl");
const tradeAutoSetLeverageInput = document.getElementById("trade-auto-set-leverage");
const tradeLeverageTtlInput = document.getElementById("trade-leverage-ttl");
const tradeNetworkSelect = document.getElementById("trade-network");
const refreshEnvBtn = document.getElementById("refresh-env");
const followerEquityInput = document.querySelector('[name="follower_equity"]');
const projectAccountSelect = document.getElementById("project-account-select");
const scaleModeSelect = document.getElementById("scale-mode-select");

// 服务控制元素
const serviceDot = document.getElementById("service-dot");
const serviceStatusText = document.getElementById("service-status-text");
const serviceProjects = document.getElementById("service-projects");
const serviceInterval = document.getElementById("service-interval");
const serviceLastFetch = document.getElementById("service-last-fetch");
const serviceStartBtn = document.getElementById("service-start-btn");
const serviceStopBtn = document.getElementById("service-stop-btn");
const serviceRefreshBtn = document.getElementById("service-refresh-btn");

const SCALE_MODE_LABELS = {
  margin_ratio: "保证金比例",
  ratio: "固定比例",
  fixed: "固定数量",
  adaptive: "自适应",
  leader_margin: "带单保证金",
};

let projectFormDirty = false;
const feedbackTimers = new Map();
let tradeConfig = null;
let tradeAccounts = [];
let selectedAccountId = "";
const POSITIONS_PAGE_SIZE = 8;
let positionsPage = 1;
let positionsCache = [];
const HISTORY_PAGE_SIZE = 5;
let historyPage = 1;
let historyCache = [];
const LOGS_PAGE_SIZE = 10;
let logsPage = 1;
let logsCache = [];
let actionAccountId = "";
let positionAccountId = "";
const TRADE_NETWORKS = {
  mainnet: "https://fapi.binance.com",
  testnet: "https://testnet.binancefuture.com",
};
const TRADE_ACCOUNT_DEFAULTS = {
  name: "Default",
  enabled: false,
  base_url: TRADE_NETWORKS.testnet,
  api_key: "",
  api_secret: "",
  recv_window: 5000,
  timeout_ms: 10000,
  min_qty: 0.0,
  max_qty: 0.0,
  send_position_side: true,
  order_type: "MARKET",
  usdt_order_mode: true,
  price_source: "mark",
  time_sync: true,
  time_sync_interval_ms: 30000,
  auto_adjust_qty: true,
  min_notional_mode: "raise",
  exchange_info_ttl_ms: 3600000,
  price_ttl_ms: 2000,
  auto_position_mode: true,
  position_mode_ttl_ms: 60000,
  auto_set_leverage: true,
  leverage_ttl_ms: 60000,
};
const ACTIONS = ["open", "add", "reduce", "close"];
const actionCardMap = new Map();
actionCards.forEach((card) => {
  const action = card.dataset.action;
  if (!action) {
    return;
  }
  actionCardMap.set(action, {
    count: card.querySelector(".action-count"),
    symbol: card.querySelector(".action-symbol"),
    meta: card.querySelector(".action-meta"),
  });
});

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    let message = text;
    try {
      const data = JSON.parse(text);
      if (data && data.detail) {
        message = data.detail;
      } else if (data) {
        message = JSON.stringify(data);
      }
    } catch (err) {
      // text is already set
    }
    throw new Error(message || res.statusText);
  }
  return res.json();
}

function formatTime(ms) {
  if (!ms) return "-";
  const d = new Date(ms);
  return d.toLocaleTimeString();
}

function shortUrl(value) {
  if (!value) return "-";
  return value.replace(/^https?:\/\//, "");
}

function toNumber(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function formatQty(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return Math.abs(n).toFixed(6);
}

function formatPrice(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(4);
}

function formatDateTime(ms) {
  if (!ms) return "-";
  const d = new Date(ms);
  return d.toLocaleString();
}

function getEventBinanceTime(event) {
  if (!event) return 0;
  return event.order_update_time || event.order_time || 0;
}

function formatLatency(ms) {
  if (!Number.isFinite(ms) || ms < 0) return "-";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatSignedQty(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  const abs = Math.abs(n).toFixed(6);
  return n < 0 ? `-${abs}` : abs;
}

function formatNotional(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return Math.abs(n).toFixed(2);
}

function buildAccountLabel(account) {
  if (!account) return "-";
  const name = account.name ? account.name.trim() : "";
  return name ? `${name} (${account.account_id})` : account.account_id;
}

function accountLabelById(accountId) {
  if (!accountId) return "-";
  const account = tradeAccounts.find((acc) => acc.account_id === accountId);
  return account ? buildAccountLabel(account) : accountId;
}

function normalizeAccount(account) {
  return { ...TRADE_ACCOUNT_DEFAULTS, ...account };
}

function getSelectedAccount() {
  if (!tradeAccounts.length) return null;
  return tradeAccounts.find((acc) => acc.account_id === selectedAccountId) || tradeAccounts[0];
}

function renderAccountSelects() {
  const options = tradeAccounts
    .map((acc) => {
      const label = buildAccountLabel(acc);
      return `<option value="${acc.account_id}">${label}</option>`;
    })
    .join("");
  if (tradeAccountSelect) {
    tradeAccountSelect.innerHTML = options;
    if (selectedAccountId) {
      tradeAccountSelect.value = selectedAccountId;
    }
  }
  if (projectAccountSelect) {
    projectAccountSelect.innerHTML = `<option value="">默认账户</option>` + options;
  }
  if (actionAccountSelect) {
    actionAccountSelect.innerHTML = `<option value="">全部账户</option>` + options;
    if (actionAccountId) {
      actionAccountSelect.value = actionAccountId;
    }
  }
  if (positionAccountSelect) {
    positionAccountSelect.innerHTML = options;
    if (positionAccountId) {
      positionAccountSelect.value = positionAccountId;
    }
  }
}

function applySelectedAccount() {
  const account = getSelectedAccount();
  if (!account) return;
  if (tradeAccountNameInput) {
    tradeAccountNameInput.value = account.name || "";
  }
  if (tradeAccountEnabledInput) {
    tradeAccountEnabledInput.checked = Boolean(account.enabled);
  }
  if (tradeBaseUrlInput) {
    tradeBaseUrlInput.value = account.base_url || TRADE_NETWORKS.mainnet;
  }
  if (tradeApiKeyInput) {
    tradeApiKeyInput.value = account.api_key || "";
  }
  if (tradeApiSecretInput) {
    tradeApiSecretInput.value = account.api_secret || "";
  }
  if (tradeRecvWindowInput) {
    tradeRecvWindowInput.value = toNumber(account.recv_window, TRADE_ACCOUNT_DEFAULTS.recv_window);
  }
  if (tradeTimeoutInput) {
    tradeTimeoutInput.value = toNumber(account.timeout_ms, TRADE_ACCOUNT_DEFAULTS.timeout_ms);
  }
  if (tradeMinQtyInput) {
    tradeMinQtyInput.value = toNumber(account.min_qty, TRADE_ACCOUNT_DEFAULTS.min_qty);
  }
  if (tradeMaxQtyInput) {
    tradeMaxQtyInput.value = toNumber(account.max_qty, TRADE_ACCOUNT_DEFAULTS.max_qty);
  }
  if (tradeOrderTypeSelect) {
    const orderType = (account.order_type || TRADE_ACCOUNT_DEFAULTS.order_type).toUpperCase();
    tradeOrderTypeSelect.value = orderType;
  }
  if (tradePriceSourceSelect) {
    const source = (account.price_source || TRADE_ACCOUNT_DEFAULTS.price_source).toLowerCase();
    tradePriceSourceSelect.value = source;
  }
  if (tradeUsdtOrderModeInput) {
    tradeUsdtOrderModeInput.checked = account.usdt_order_mode !== false;
  }
  if (tradeSendPositionSideInput) {
    tradeSendPositionSideInput.checked = account.send_position_side !== false;
  }
  if (tradeTimeSyncInput) {
    tradeTimeSyncInput.checked = account.time_sync !== false;
  }
  if (tradeTimeSyncIntervalInput) {
    tradeTimeSyncIntervalInput.value = toNumber(
      account.time_sync_interval_ms,
      TRADE_ACCOUNT_DEFAULTS.time_sync_interval_ms,
    );
  }
  if (tradeAutoAdjustQtyInput) {
    tradeAutoAdjustQtyInput.checked = account.auto_adjust_qty !== false;
  }
  if (tradeMinNotionalModeSelect) {
    const mode = (account.min_notional_mode || TRADE_ACCOUNT_DEFAULTS.min_notional_mode).toLowerCase();
    tradeMinNotionalModeSelect.value = mode;
  }
  if (tradeExchangeInfoTtlInput) {
    tradeExchangeInfoTtlInput.value = toNumber(
      account.exchange_info_ttl_ms,
      TRADE_ACCOUNT_DEFAULTS.exchange_info_ttl_ms,
    );
  }
  if (tradePriceTtlInput) {
    tradePriceTtlInput.value = toNumber(account.price_ttl_ms, TRADE_ACCOUNT_DEFAULTS.price_ttl_ms);
  }
  if (tradeAutoPositionModeInput) {
    tradeAutoPositionModeInput.checked = account.auto_position_mode !== false;
  }
  if (tradePositionModeTtlInput) {
    tradePositionModeTtlInput.value = toNumber(
      account.position_mode_ttl_ms,
      TRADE_ACCOUNT_DEFAULTS.position_mode_ttl_ms,
    );
  }
  if (tradeAutoSetLeverageInput) {
    tradeAutoSetLeverageInput.checked = account.auto_set_leverage !== false;
  }
  if (tradeLeverageTtlInput) {
    tradeLeverageTtlInput.value = toNumber(
      account.leverage_ttl_ms,
      TRADE_ACCOUNT_DEFAULTS.leverage_ttl_ms,
    );
  }
  if (tradeNetworkSelect) {
    tradeNetworkSelect.value = guessTradeNetwork(account.base_url || "");
  }
  if (statusTradeBase) {
    statusTradeBase.textContent = shortUrl(account.base_url);
  }
}

function setConnectionStatus(connected) {
  statusConnected.textContent = connected ? "已连接" : "未连接";
  statusDot.classList.toggle("connected", connected);
}

let positionHiddenAlertShown = false;
function showPositionHiddenAlert() {
  if (positionHiddenAlertShown) return;
  positionHiddenAlertShown = true;
  const msg = "带单员已隐藏仓位数据，请先在币安加入该跟单项目后再使用本系统跟单。";
  alert(msg);
  setTimeout(() => {
    positionHiddenAlertShown = false;
  }, 60000);
}

function clearFormFeedback(target) {
  if (!target) return;
  const timer = feedbackTimers.get(target);
  if (timer) {
    clearTimeout(timer);
    feedbackTimers.delete(target);
  }
  target.textContent = "";
  target.classList.remove("success", "error");
}

function showFormFeedback(target, type, message) {
  if (!target) return;
  clearFormFeedback(target);
  if (!message) return;
  target.textContent = message;
  if (type) {
    target.classList.add(type);
  }
  const timer = setTimeout(() => {
    clearFormFeedback(target);
  }, 3500);
  feedbackTimers.set(target, timer);
}

function fillProjectForm(project) {
  if (!project || !projectForm) return;
  const formData = new FormData(projectForm);
  for (const [key] of formData.entries()) {
    if (key === "follower_equity") {
      continue;
    }
    if (project[key] !== undefined) {
      const field = projectForm.elements.namedItem(key);
      if (field) {
        field.value = project[key];
      }
    }
  }
  // 设置 scale_mode 选择器
  if (scaleModeSelect && project.scale_mode) {
    scaleModeSelect.value = project.scale_mode;
  }
}

async function loadStatus() {
  try {
    const data = await api("/api/status");
    const connected = Boolean(data.connected);
    const authMode = data.auth_mode || "cookie";
    const hasCookie = Boolean(data.cookie_exists);
    setConnectionStatus(connected);
    if (connectBtn) {
      connectBtn.disabled = authMode === "cookie";
      connectBtn.textContent = authMode === "cookie" ? "Cookie 模式" : "重新连接";
    }
    if (statusApiText) {
      statusApiText.textContent = connected ? "正常" : "断开";
    }
    if (statusAuthText) {
      statusAuthText.textContent = authMode === "cookie" ? "Cookie" : "CDP";
    }
    if (statusCookieText) {
      statusCookieText.textContent =
        authMode === "cookie" ? (hasCookie ? "已上传" : "未上传") : "-";
    }
    if (authMode === "cookie" && !hasCookie) {
      statusError.textContent = "请上传 cookies.json";
      return;
    }
    // 检查仓位是否被隐藏
    if (data.position_hidden) {
      statusError.textContent = "仓位数据被隐藏";
      showPositionHiddenAlert();
    } else {
      statusError.textContent = data.last_error || "";
    }
  } catch (err) {
    setConnectionStatus(false);
    statusError.textContent = err.message;
  }
}

async function loadConfig() {
  const data = await api("/api/config");
  if (statusApiBase) {
    statusApiBase.textContent = shortUrl(data.api_base);
  }
}

async function loadTradeConfig() {
  const data = await api("/api/trade-config");
  tradeConfig = data;
  tradeAccounts = Array.isArray(data.accounts)
    ? data.accounts.map((acc) => normalizeAccount(acc))
    : [];
  if (!tradeAccounts.length) {
    tradeAccounts = [
      normalizeAccount({
        account_id: "default",
        name: "Default",
        enabled: false,
        base_url: TRADE_NETWORKS.testnet,
        api_key: "",
        api_secret: "",
      }),
    ];
  }
  if (!selectedAccountId) {
    selectedAccountId = data.default_account_id || tradeAccounts[0].account_id;
  }
  if (!tradeAccounts.find((acc) => acc.account_id === selectedAccountId)) {
    selectedAccountId = tradeAccounts[0].account_id;
  }
  if (!positionAccountId) {
    positionAccountId = selectedAccountId;
  }
  if (positionAccountId && !tradeAccounts.find((acc) => acc.account_id === positionAccountId)) {
    positionAccountId = selectedAccountId;
  }
  if (actionAccountId && !tradeAccounts.find((acc) => acc.account_id === actionAccountId)) {
    actionAccountId = "";
  }
  renderAccountSelects();
  applySelectedAccount();
  if (tradeEnabledInput) {
    tradeEnabledInput.checked = Boolean(data.enabled);
  }
  if (statusTradeText) {
    statusTradeText.textContent = data.enabled ? "开启" : "关闭";
  }
}

async function loadFollowerEquity() {
  if (!followerEquityInput) return;
  try {
    const accountId = selectedAccountId || "";
    const path = accountId
      ? `/api/follower-equity?account_id=${encodeURIComponent(accountId)}`
      : "/api/follower-equity";
    const data = await api(path);
    if (data.ok && Number.isFinite(data.equity)) {
      followerEquityInput.value = Number(data.equity).toFixed(2);
    }
  } catch (err) {
    // keep previous value on errors
  }
}

async function loadProjects() {
  const projects = await api("/api/projects");
  renderProjects(projects);
  if (!projectFormDirty && projects.length > 0) {
    fillProjectForm(projects[0]);
  }
}

async function loadPositions() {
  if (!positionsTable) return;
  const positions = await api("/api/positions");
  positionsCache = Array.isArray(positions) ? positions : [];
  renderPositions();
}

async function loadLeaderPositions() {
  if (!leaderPositionsTable) return;
  const positions = await api("/api/leader-positions");
  const items = Array.isArray(positions) ? positions : [];
  renderLeaderPositions(items);
}

function renderLeaderPositions(items) {
  if (!leaderPositionsTable) return;
  const header = `
    <div class="table-row header">
      <div>Portfolio</div>
      <div>Symbol</div>
      <div>Side</div>
      <div>Qty</div>
      <div>Entry</div>
      <div>Mark</div>
      <div>Leverage</div>
      <div>PnL</div>
    </div>
  `;
  const rows = items.length > 0
    ? items.map((item) => `
      <div class="table-row">
        <div>${item.portfolio_id || "-"}</div>
        <div>${item.symbol || "-"}</div>
        <div>${item.side || "-"}</div>
        <div>${item.qty?.toFixed(4) || "-"}</div>
        <div>${item.entry_price?.toFixed(4) || "-"}</div>
        <div>${item.mark_price?.toFixed(4) || "-"}</div>
        <div>${item.leverage || "-"}x</div>
        <div>${item.unrealized_pnl?.toFixed(2) || "-"}</div>
      </div>
    `).join("")
    : `<div class="table-row"><div>暂无持仓</div><div>-</div><div>-</div><div>-</div><div>-</div><div>-</div><div>-</div><div>-</div></div>`;
  leaderPositionsTable.innerHTML = header + rows;
}

function renderProjects(projects) {
  const header = `
    <div class="table-row header">
      <div>ID</div>
      <div>账户</div>
      <div>跟随模式</div>
      <div>倍数</div>
      <div>杠杆</div>
      <div>资金</div>
      <div>状态</div>
      <div>操作</div>
    </div>
  `;
  const rows = projects
    .map((p) => {
      const badge = p.enabled
        ? '<span class="badge">运行</span>'
        : '<span class="badge off">停止</span>';
      const modeLabel = SCALE_MODE_LABELS[p.scale_mode] || p.scale_mode || "-";
      return `
      <div class="table-row">
        <div>${p.portfolio_id}</div>
        <div>${accountLabelById(p.trade_account_id)}</div>
        <div>${modeLabel}</div>
        <div>${Number(p.scale_value || 1).toFixed(2)}x</div>
        <div>${Number(p.follower_leverage || 0).toFixed(0)}x</div>
        <div>${p.follower_equity}</div>
        <div>${badge}</div>
        <div class="actions">
          <button class="ghost" data-action="toggle" data-id="${p.portfolio_id}" data-enabled="${!p.enabled}">${
        p.enabled ? "暂停" : "启动"
      }</button>
          <button class="ghost" data-action="remove" data-id="${p.portfolio_id}">删除</button>
        </div>
      </div>
    `;
    })
    .join("");
  projectsTable.innerHTML = header + rows;

  projectsTable.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const action = btn.dataset.action;
      if (action === "toggle") {
        const enabled = btn.dataset.enabled === "true";
        await api(`/api/projects/${id}/enable`, {
          method: "POST",
          body: JSON.stringify({ enabled }),
        });
      }
      if (action === "remove") {
        await api(`/api/projects/${id}`, { method: "DELETE" });
      }
      await loadProjects();
    });
  });
}

function renderPositions() {
  if (!positionsTable) return;
  const items = positionsCache;
  const total = items.length;
  const totalPages = Math.max(Math.ceil(total / POSITIONS_PAGE_SIZE), 1);
  if (positionsPage > totalPages) {
    positionsPage = totalPages;
  }
  const start = (positionsPage - 1) * POSITIONS_PAGE_SIZE;
  const pageItems = items.slice(start, start + POSITIONS_PAGE_SIZE);
  const header = `
    <div class="table-row header">
      <div>Portfolio</div>
      <div>Symbol</div>
      <div>Side</div>
      <div>Status</div>
      <div>Avg Cost</div>
      <div>Opened At</div>
      <div>Closed At</div>
      <div>Updated</div>
    </div>
  `;
  const rows = pageItems
    .map((item) => {
      const updatedAt = item.update_time || item.snapshot_ts || 0;
      return `
      <div class="table-row">
        <div>${item.portfolio_id || "-"}</div>
        <div>${item.symbol || "-"}</div>
        <div>${item.side || "-"}</div>
        <div>${item.status || "-"}</div>
        <div>${formatPrice(item.avg_cost)}</div>
        <div>${formatDateTime(item.open_time)}</div>
        <div>${formatDateTime(item.close_time)}</div>
        <div>${formatDateTime(updatedAt)}</div>
      </div>
    `;
    })
    .join("");
  const empty = `
    <div class="table-row">
      <div>暂无记录</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
    </div>
  `;
  positionsTable.innerHTML = header + (rows || empty);
  renderPositionsPagination(total, totalPages);
}

function renderPositionsPagination(total, totalPages) {
  if (!positionsPagination) return;
  if (total === 0) {
    positionsPagination.innerHTML = "";
    return;
  }
  positionsPagination.innerHTML = `
    <button type="button" data-page="prev" ${positionsPage <= 1 ? "disabled" : ""}>上一页</button>
    <span>第 ${positionsPage} / ${totalPages} 页</span>
    <button type="button" data-page="next" ${positionsPage >= totalPages ? "disabled" : ""}>下一页</button>
  `;
  positionsPagination.querySelectorAll("button[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.page;
      if (action === "prev" && positionsPage > 1) {
        positionsPage -= 1;
        renderPositions();
      }
      if (action === "next" && positionsPage < totalPages) {
        positionsPage += 1;
        renderPositions();
      }
    });
  });
}

async function loadActionEvents() {
  const events = await api("/api/events?limit=200");
  const actionText = {
    open: "开仓",
    add: "加仓",
    reduce: "减仓",
    close: "平仓",
  };
  const filtered = events.filter((e) => actionText[e.action]);
  const accountFiltered = actionAccountId
    ? filtered.filter((e) => {
        const resolved = e.trade_account_id || (tradeConfig && tradeConfig.default_account_id) || "";
        return resolved === actionAccountId;
      })
    : filtered;
  historyCache = accountFiltered;
  renderActionSummary(accountFiltered);
  renderActionHistory();
}

async function loadLogs() {
  const logs = await api("/api/logs?limit=200");
  logsCache = Array.isArray(logs) ? logs : [];
  renderLogs();
}

function renderLogs() {
  const totalPages = Math.ceil(logsCache.length / LOGS_PAGE_SIZE) || 1;
  if (logsPage > totalPages) logsPage = totalPages;
  const start = (logsPage - 1) * LOGS_PAGE_SIZE;
  const pageData = logsCache.slice(start, start + LOGS_PAGE_SIZE);

  const header = `
    <div class="table-row header">
      <div>时间</div>
      <div>级别</div>
      <div>消息</div>
    </div>
  `;
  const rows = pageData
    .map((log) => {
      const level = String(log.level || "").toLowerCase() || "info";
      const message = log.message || "-";
      return `
      <div class="table-row">
        <div>${formatTime(log.ts)}</div>
        <div class="log-level ${level}">${level}</div>
        <div class="log-message">${message}</div>
      </div>
    `;
    })
    .join("");
  const empty = `
    <div class="table-row">
      <div>暂无记录</div>
      <div>-</div>
      <div class="log-message">等待服务器日志...</div>
    </div>
  `;
  logsTable.innerHTML = header + (rows || empty);
  renderLogsPagination(totalPages);
}

function renderLogsPagination(totalPages) {
  if (!logsPagination) return;
  if (logsCache.length === 0) {
    logsPagination.innerHTML = "";
    return;
  }
  logsPagination.innerHTML = `
    <button type="button" data-page="prev" ${logsPage <= 1 ? "disabled" : ""}>上一页</button>
    <span>第 ${logsPage} / ${totalPages} 页 (共 ${logsCache.length} 条)</span>
    <button type="button" data-page="next" ${logsPage >= totalPages ? "disabled" : ""}>下一页</button>
  `;
  logsPagination.querySelectorAll("button[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.page;
      if (action === "prev" && logsPage > 1) {
        logsPage -= 1;
        renderLogs();
      }
      if (action === "next" && logsPage < totalPages) {
        logsPage += 1;
        renderLogs();
      }
    });
  });
}

function renderActionSummary(events) {
  if (!actionCardMap.size) return;
  const counts = new Map(ACTIONS.map((action) => [action, 0]));
  const latest = new Map();
  for (const event of events) {
    if (!counts.has(event.action)) continue;
    counts.set(event.action, (counts.get(event.action) || 0) + 1);
    if (!latest.has(event.action)) {
      latest.set(event.action, event);
    }
  }
  for (const action of ACTIONS) {
    const target = actionCardMap.get(action);
    if (!target) continue;
    if (target.count) {
      target.count.textContent = String(counts.get(action) || 0);
    }
    const event = latest.get(action);
    if (!event) {
      if (target.symbol) target.symbol.textContent = "-";
      if (target.meta) target.meta.textContent = "暂无记录";
      continue;
    }
    if (target.symbol) {
      target.symbol.textContent = event.symbol || "-";
    }
    if (target.meta) {
      const time = formatTime(event.created_at);
      const side = event.side || "-";
      const qty = formatQty(event.follower_qty);
      const binanceTime = getEventBinanceTime(event);
      const latency = formatLatency(event.created_at && binanceTime ? event.created_at - binanceTime : NaN);
      target.meta.textContent = `${side} ${qty} · ${time} · 延迟 ${latency}`;
    }
  }
}

function renderActionHistory() {
  if (!historyTable) return;
  const items = historyCache;
  const total = items.length;
  const totalPages = Math.max(Math.ceil(total / HISTORY_PAGE_SIZE), 1);
  if (historyPage > totalPages) {
    historyPage = totalPages;
  }
  const start = (historyPage - 1) * HISTORY_PAGE_SIZE;
  const pageItems = items.slice(start, start + HISTORY_PAGE_SIZE);
  const header = `
    <div class="table-row header">
      <div>动作</div>
      <div>Symbol</div>
      <div>Side</div>
      <div>Qty</div>
      <div>执行时间</div>
      <div>币安时间</div>
      <div>延迟</div>
    </div>
  `;
  const actionText = {
    open: "开仓",
    add: "加仓",
    reduce: "减仓",
    close: "平仓",
  };
  const rows = pageItems
    .map((event) => {
      const binanceTime = getEventBinanceTime(event);
      const executedAt = event.executed_at || event.created_at;
      const latency = event.latency_ms != null
        ? formatLatency(event.latency_ms)
        : formatLatency(executedAt && binanceTime ? executedAt - binanceTime : NaN);
      return `
      <div class="table-row">
        <div>${actionText[event.action] || event.action || "-"}</div>
        <div>${event.symbol || "-"}</div>
        <div>${event.side || "-"}</div>
        <div>${formatQty(event.follower_qty)}</div>
        <div>${formatDateTime(executedAt)}</div>
        <div>${formatDateTime(binanceTime)}</div>
        <div>${latency}</div>
      </div>
    `;
    })
    .join("");
  const empty = `
    <div class="table-row">
      <div>暂无记录</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
    </div>
  `;
  historyTable.innerHTML = header + (rows || empty);
  renderActionHistoryPagination(total, totalPages);
}

function renderActionHistoryPagination(total, totalPages) {
  if (!historyPagination) return;
  if (total === 0) {
    historyPagination.innerHTML = "";
    return;
  }
  historyPagination.innerHTML = `
    <button type="button" data-page="prev" ${historyPage <= 1 ? "disabled" : ""}>上一页</button>
    <span>第 ${historyPage} / ${totalPages} 页</span>
    <button type="button" data-page="next" ${historyPage >= totalPages ? "disabled" : ""}>下一页</button>
  `;
  historyPagination.querySelectorAll("button[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.page;
      if (action === "prev" && historyPage > 1) {
        historyPage -= 1;
        renderActionHistory();
      }
      if (action === "next" && historyPage < totalPages) {
        historyPage += 1;
        renderActionHistory();
      }
    });
  });
}

async function loadFollowerPositions() {
  if (!accountPositionsTable) return;
  const accountId = positionAccountId || selectedAccountId;
  if (!accountId) {
    accountPositionsTable.innerHTML = "";
    return;
  }
  try {
    const path = `/api/follower-positions?account_id=${encodeURIComponent(accountId)}`;
    const data = await api(path);
    renderFollowerPositions(Array.isArray(data) ? data : []);
  } catch (err) {
    renderFollowerPositions([]);
  }
}

function renderFollowerPositions(items) {
  if (!accountPositionsTable) return;
  const header = `
    <div class="table-row header">
      <div>Symbol</div>
      <div>Side</div>
      <div>Qty</div>
      <div>Entry</div>
      <div>Mark</div>
      <div>Notional</div>
      <div>PnL</div>
    </div>
  `;
  const rows = items
    .map((item) => {
      const qty = Number(item.positionAmt || 0);
      const entry = Number(item.entryPrice || 0);
      const mark = Number(item.markPrice || 0);
      const notional = qty * (mark || entry || 0);
      const pnl = Number(item.unRealizedProfit || item.unrealizedProfit || 0);
      return `
      <div class="table-row">
        <div>${item.symbol || "-"}</div>
        <div>${item.positionSide || "-"}</div>
        <div>${formatSignedQty(qty)}</div>
        <div>${formatPrice(entry)}</div>
        <div>${formatPrice(mark)}</div>
        <div>${formatNotional(notional)}</div>
        <div>${formatNotional(pnl)}</div>
      </div>
    `;
    })
    .join("");
  const empty = `
    <div class="table-row">
      <div>暂无记录</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
      <div>-</div>
    </div>
  `;
  accountPositionsTable.innerHTML = header + (rows || empty);
}

function guessTradeNetwork(url) {
  if (!url) return "mainnet";
  const value = url.toLowerCase();
  if (value.includes("testnet")) return "testnet";
  if (value.includes("fapi.binance.com")) return "mainnet";
  return "mainnet";
}

function applyTradeNetwork(value) {
  const preset = TRADE_NETWORKS[value];
  if (preset && tradeBaseUrlInput) {
    tradeBaseUrlInput.value = preset;
  }
}

projectForm.addEventListener("input", () => {
  projectFormDirty = true;
  clearFormFeedback(projectFeedback);
});

projectForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearFormFeedback(projectFeedback);
  const submitBtn = projectForm.querySelector('button[type="submit"]');
  const submitLabel = submitBtn ? submitBtn.textContent : "";
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "保存中...";
  }
  const formData = new FormData(projectForm);
  const payload = Object.fromEntries(formData.entries());
  payload.enabled = true;
  if (!payload.trade_account_id && selectedAccountId) {
    payload.trade_account_id = selectedAccountId;
  }
  payload.poll_interval_ms = toNumber(payload.poll_interval_ms, 3000);
  payload.order_window_ms = toNumber(payload.order_window_ms, 1800000);
  payload.page_size = toNumber(payload.page_size, 5);
  payload.scale_mode = payload.scale_mode || "ratio";
  payload.scale_value = toNumber(payload.scale_value, 1.0);
  payload.leader_leverage = toNumber(payload.leader_leverage, 10);
  payload.follower_leverage = toNumber(payload.follower_leverage, 10);
  const followerEquityValue = followerEquityInput ? followerEquityInput.value : payload.follower_equity;
  payload.follower_equity = toNumber(followerEquityValue, 1000);
  payload.min_qty = toNumber(payload.min_qty, 0);
  payload.max_qty = toNumber(payload.max_qty, 0);
  payload.detail_refresh_ms = toNumber(payload.detail_refresh_ms, 5000);

  try {
    await api("/api/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    projectFormDirty = false;
    await loadProjects();
    showFormFeedback(projectFeedback, "success", "保存成功");
  } catch (err) {
    showFormFeedback(projectFeedback, "error", err.message || "保存失败");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = submitLabel;
    }
  }
});

resetFormBtn.addEventListener("click", () => {
  projectForm.reset();
  projectFormDirty = false;
  clearFormFeedback(projectFeedback);
  loadFollowerEquity();
});

envForm.addEventListener("input", () => {
  clearFormFeedback(envFeedback);
});

envForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearFormFeedback(envFeedback);
  const submitBtn = envForm.querySelector('button[type="submit"]');
  const submitLabel = submitBtn ? submitBtn.textContent : "";
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "保存中...";
  }
  if (tradeNetworkSelect) {
    applyTradeNetwork(tradeNetworkSelect.value);
  }
  const account = getSelectedAccount();
  if (!tradeConfig || !account) {
    showFormFeedback(envFeedback, "error", "请先加载 API 配置");
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = submitLabel;
    }
    return;
  }
  account.name = tradeAccountNameInput ? tradeAccountNameInput.value.trim() : account.name;
  account.enabled = tradeAccountEnabledInput ? tradeAccountEnabledInput.checked : account.enabled;
  account.base_url = tradeBaseUrlInput ? tradeBaseUrlInput.value.trim() : account.base_url;
  account.api_key = tradeApiKeyInput ? tradeApiKeyInput.value.trim() : account.api_key;
  account.api_secret = tradeApiSecretInput ? tradeApiSecretInput.value.trim() : account.api_secret;
  account.recv_window = tradeRecvWindowInput
    ? toNumber(tradeRecvWindowInput.value, account.recv_window)
    : account.recv_window;
  account.timeout_ms = tradeTimeoutInput
    ? toNumber(tradeTimeoutInput.value, account.timeout_ms)
    : account.timeout_ms;
  account.min_qty = tradeMinQtyInput
    ? toNumber(tradeMinQtyInput.value, account.min_qty)
    : account.min_qty;
  account.max_qty = tradeMaxQtyInput
    ? toNumber(tradeMaxQtyInput.value, account.max_qty)
    : account.max_qty;
  account.order_type = tradeOrderTypeSelect
    ? tradeOrderTypeSelect.value
    : account.order_type;
  account.price_source = tradePriceSourceSelect
    ? tradePriceSourceSelect.value
    : account.price_source;
  account.usdt_order_mode = tradeUsdtOrderModeInput
    ? tradeUsdtOrderModeInput.checked
    : account.usdt_order_mode;
  account.send_position_side = tradeSendPositionSideInput
    ? tradeSendPositionSideInput.checked
    : account.send_position_side;
  account.time_sync = tradeTimeSyncInput ? tradeTimeSyncInput.checked : account.time_sync;
  account.time_sync_interval_ms = tradeTimeSyncIntervalInput
    ? toNumber(tradeTimeSyncIntervalInput.value, account.time_sync_interval_ms)
    : account.time_sync_interval_ms;
  account.auto_adjust_qty = tradeAutoAdjustQtyInput
    ? tradeAutoAdjustQtyInput.checked
    : account.auto_adjust_qty;
  account.min_notional_mode = tradeMinNotionalModeSelect
    ? tradeMinNotionalModeSelect.value
    : account.min_notional_mode;
  account.exchange_info_ttl_ms = tradeExchangeInfoTtlInput
    ? toNumber(tradeExchangeInfoTtlInput.value, account.exchange_info_ttl_ms)
    : account.exchange_info_ttl_ms;
  account.price_ttl_ms = tradePriceTtlInput
    ? toNumber(tradePriceTtlInput.value, account.price_ttl_ms)
    : account.price_ttl_ms;
  account.auto_position_mode = tradeAutoPositionModeInput
    ? tradeAutoPositionModeInput.checked
    : account.auto_position_mode;
  account.position_mode_ttl_ms = tradePositionModeTtlInput
    ? toNumber(tradePositionModeTtlInput.value, account.position_mode_ttl_ms)
    : account.position_mode_ttl_ms;
  account.auto_set_leverage = tradeAutoSetLeverageInput
    ? tradeAutoSetLeverageInput.checked
    : account.auto_set_leverage;
  account.leverage_ttl_ms = tradeLeverageTtlInput
    ? toNumber(tradeLeverageTtlInput.value, account.leverage_ttl_ms)
    : account.leverage_ttl_ms;
  tradeConfig.enabled = tradeEnabledInput.checked;
  tradeConfig.default_account_id = selectedAccountId || account.account_id;
  tradeConfig.accounts = tradeAccounts;
  try {
    await api("/api/trade-config", {
      method: "POST",
      body: JSON.stringify(tradeConfig),
    });
    await loadTradeConfig();
    await loadFollowerEquity();
    showFormFeedback(envFeedback, "success", "保存成功");
  } catch (err) {
    showFormFeedback(envFeedback, "error", err.message || "保存失败");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = submitLabel;
    }
  }
});

if (tradeAccountSelect) {
  tradeAccountSelect.addEventListener("change", () => {
    selectedAccountId = tradeAccountSelect.value;
    applySelectedAccount();
    loadFollowerEquity();
  });
}

if (actionAccountSelect) {
  actionAccountSelect.addEventListener("change", () => {
    actionAccountId = actionAccountSelect.value;
    loadActionEvents();
  });
}

if (positionAccountSelect) {
  positionAccountSelect.addEventListener("change", () => {
    positionAccountId = positionAccountSelect.value;
    loadFollowerPositions();
  });
}

if (addTradeAccountBtn) {
  addTradeAccountBtn.addEventListener("click", () => {
    const id = `acc-${Date.now()}`;
    const account = normalizeAccount({
      account_id: id,
      name: `Account ${tradeAccounts.length + 1}`,
      enabled: false,
      base_url: TRADE_NETWORKS.testnet,
      api_key: "",
      api_secret: "",
    });
    tradeAccounts.push(account);
    selectedAccountId = id;
    renderAccountSelects();
    applySelectedAccount();
    clearFormFeedback(envFeedback);
  });
}

if (removeTradeAccountBtn) {
  removeTradeAccountBtn.addEventListener("click", () => {
    if (tradeAccounts.length <= 1) {
      showFormFeedback(envFeedback, "error", "至少保留一个 API");
      return;
    }
    tradeAccounts = tradeAccounts.filter((acc) => acc.account_id !== selectedAccountId);
    selectedAccountId = tradeAccounts[0].account_id;
    renderAccountSelects();
    applySelectedAccount();
    clearFormFeedback(envFeedback);
  });
}

if (cookieForm) {
  cookieForm.addEventListener("input", () => {
    clearFormFeedback(cookieFeedback);
  });

  cookieForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFormFeedback(cookieFeedback);
    if (!cookieFileInput || !cookieFileInput.files || cookieFileInput.files.length === 0) {
      showFormFeedback(cookieFeedback, "error", "请先选择 cookies.json");
      return;
    }
    const submitBtn = cookieForm.querySelector('button[type="submit"]');
    const submitLabel = submitBtn ? submitBtn.textContent : "";
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "上传中...";
    }
    const formData = new FormData();
    formData.append("file", cookieFileInput.files[0]);
    try {
      const res = await fetch("/api/cookies", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "上传失败");
      }
      cookieFileInput.value = "";
      await loadStatus();
      showFormFeedback(cookieFeedback, "success", "Cookie 已启用");
    } catch (err) {
      showFormFeedback(cookieFeedback, "error", err.message || "上传失败");
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = submitLabel;
      }
    }
  });
}

refreshEnvBtn.addEventListener("click", async () => {
  await loadTradeConfig();
  await loadFollowerEquity();
});

if (tradeNetworkSelect) {
  tradeNetworkSelect.addEventListener("change", () => {
    if (tradeNetworkSelect.value !== "custom") {
      applyTradeNetwork(tradeNetworkSelect.value);
    }
  });
}

if (tradeBaseUrlInput && tradeNetworkSelect) {
  tradeBaseUrlInput.addEventListener("input", () => {
    tradeNetworkSelect.value = guessTradeNetwork(tradeBaseUrlInput.value.trim());
  });
}

connectBtn.addEventListener("click", async () => {
  await api("/api/connect", { method: "POST" });
  await loadStatus();
});

// 服务控制相关函数
let serviceStatus = { running: 0, total: 0, lastFetch: 0 };

async function loadServiceStatus() {
  try {
    const projects = await api("/api/projects");
    const status = await api("/api/status");
    const running = projects.filter(p => p.enabled).length;
    const total = projects.length;

    serviceStatus = {
      running,
      total,
      lastFetch: status.last_fetch_at || 0,
      connected: status.connected,
      pollInterval: projects[0]?.poll_interval_ms || 3000
    };

    updateServiceUI();
  } catch (err) {
    if (serviceDot) serviceDot.className = "service-dot stopped";
    if (serviceStatusText) serviceStatusText.textContent = "服务异常";
  }
}

function updateServiceUI() {
  if (serviceDot) {
    serviceDot.className = serviceStatus.running > 0 ? "service-dot running" : "service-dot stopped";
  }
  if (serviceStatusText) {
    serviceStatusText.textContent = serviceStatus.running > 0
      ? `运行中 (${serviceStatus.running}/${serviceStatus.total} 项目)`
      : "已停止";
  }
  if (serviceProjects) {
    serviceProjects.textContent = `${serviceStatus.running}/${serviceStatus.total}`;
  }
  if (serviceInterval) {
    serviceInterval.textContent = serviceStatus.pollInterval ? `${serviceStatus.pollInterval}ms` : "-";
  }
  if (serviceLastFetch) {
    serviceLastFetch.textContent = serviceStatus.lastFetch ? formatTime(serviceStatus.lastFetch) : "-";
  }
}

async function startAllProjects() {
  try {
    const projects = await api("/api/projects");
    for (const p of projects) {
      if (!p.enabled) {
        await api(`/api/projects/${p.portfolio_id}/enable`, {
          method: "POST",
          body: JSON.stringify({ enabled: true }),
        });
      }
    }
    await loadServiceStatus();
    await loadProjects();
  } catch (err) {
    alert("启动失败: " + (err.message || "未知错误"));
  }
}

async function stopAllProjects() {
  try {
    const projects = await api("/api/projects");
    for (const p of projects) {
      if (p.enabled) {
        await api(`/api/projects/${p.portfolio_id}/enable`, {
          method: "POST",
          body: JSON.stringify({ enabled: false }),
        });
      }
    }
    await loadServiceStatus();
    await loadProjects();
  } catch (err) {
    alert("停止失败: " + (err.message || "未知错误"));
  }
}

// 服务控制按钮事件
if (serviceStartBtn) {
  serviceStartBtn.addEventListener("click", startAllProjects);
}
if (serviceStopBtn) {
  serviceStopBtn.addEventListener("click", stopAllProjects);
}
if (serviceRefreshBtn) {
  serviceRefreshBtn.addEventListener("click", loadServiceStatus);
}

async function boot() {
  await loadStatus();
  await loadTradeConfig();
  await loadFollowerEquity();
  await loadProjects();
  await loadServiceStatus();
  await loadPositions();
  await loadLeaderPositions();
  await loadActionEvents();
  await loadLogs();
  await loadFollowerPositions();
  // 优化刷新间隔，降低延迟
  setInterval(loadStatus, 1500);
  setInterval(loadProjects, 3000);
  setInterval(loadServiceStatus, 2000);
  setInterval(loadPositions, 2000);
  setInterval(loadLeaderPositions, 1500);  // 带单员持仓刷新更快
  setInterval(loadActionEvents, 1500);
  setInterval(loadLogs, 1500);
  setInterval(loadFollowerEquity, 5000);
  setInterval(loadFollowerPositions, 3000);
}

boot();

// Cookie 文件直接上传（状态栏按钮）
if (cookieFileInput) {
  cookieFileInput.addEventListener("change", async () => {
    if (!cookieFileInput.files || cookieFileInput.files.length === 0) return;
    const formData = new FormData();
    formData.append("file", cookieFileInput.files[0]);
    try {
      const res = await fetch("/api/cookies", { method: "POST", body: formData });
      if (!res.ok) throw new Error(await res.text());
      cookieFileInput.value = "";
      await loadStatus();
      alert("Cookie 上传成功！");
    } catch (err) {
      alert("Cookie 上传失败: " + (err.message || "未知错误"));
    }
  });
}

// 复制按钮功能
document.querySelectorAll(".copy-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const targetId = btn.dataset.target;
    const target = document.getElementById(targetId);
    if (!target) return;
    navigator.clipboard.writeText(target.textContent).then(() => {
      const orig = btn.textContent;
      btn.textContent = "已复制";
      setTimeout(() => { btn.textContent = orig; }, 1500);
    });
  });
});
