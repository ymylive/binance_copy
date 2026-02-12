(() => {
  const state = {
    historyPage: 1,
    logsPage: 1,
    allEvents: [],
    allLogs: [],
    projects: [],
    accounts: [],
    allocations: {},
    allocationsDraft: {},
    allocationsDirty: false,
    leverages: {},
    leveragesDraft: {},
    allocationAccountId: '',
    language: 'en',
    onchainConfigLoaded: false,
    onchainConfig: null
  };

  const elements = {
    connectionStatus: document.getElementById('connectionStatus'),
    connectBtn: document.getElementById('connectBtn'),
    themeToggle: document.getElementById('themeToggle'),
    languageToggle: document.getElementById('languageToggle'),
    refreshNowBtn: document.getElementById('refreshNowBtn'),
    jumpConfigBtn: document.getElementById('jumpConfigBtn'),
    serviceStatus: document.getElementById('serviceStatus'),
    serviceStatusText: document.getElementById('serviceStatusText'),
    projectCount: document.getElementById('projectCount'),
    positionCount: document.getElementById('positionCount'),
    actionCount: document.getElementById('actionCount'),
    openCount: document.getElementById('openCount'),
    addCount: document.getElementById('addCount'),
    reduceCount: document.getElementById('reduceCount'),
    closeCount: document.getElementById('closeCount'),
    projectsBody: document.getElementById('projectsBody'),
    leaderPositionsBody: document.getElementById('leaderPositionsBody'),
    followerPositionsBody: document.getElementById('followerPositionsBody'),
    accountSelect: document.getElementById('accountSelect'),
    historyBody: document.getElementById('historyBody'),
    logsBody: document.getElementById('logsBody'),
    historyPrev: document.getElementById('historyPrevBtn'),
    historyNext: document.getElementById('historyNextBtn'),
    historyInfo: document.getElementById('historyPageInfo'),
    logsPrev: document.getElementById('logsPrevBtn'),
    logsNext: document.getElementById('logsNextBtn'),
    logsInfo: document.getElementById('logsPageInfo'),
    refreshProjectsBtn: document.getElementById('refreshProjectsBtn'),
    projectForm: document.getElementById('projectForm'),
    accountForm: document.getElementById('accountForm'),
    cookieForm: document.getElementById('cookieForm'),
    cookieTextForm: document.getElementById('cookieTextForm'),
    cookieTextArea: document.getElementById('cookieTextArea'),
    projectAccountSelect: document.getElementById('projectAccountSelect'),
    totalEquity: document.getElementById('totalEquity'),
    marginBalance: document.getElementById('marginBalance'),
    allocatedPercent: document.getElementById('allocatedPercent'),
    availablePercent: document.getElementById('availablePercent'),
    allocationEquity: document.getElementById('allocationEquity'),
    allocationMargin: document.getElementById('allocationMargin'),
    allocationTotal: document.getElementById('allocationTotal'),
    allocationAvailable: document.getElementById('allocationAvailable'),
    allocationList: document.getElementById('allocationList'),
    saveAllocationBtn: document.getElementById('saveAllocationBtn'),
    allocationAccountSelect: document.getElementById('allocationAccountSelect'),
    accountsBody: document.getElementById('accountsBody'),
    projectExchange: document.getElementById('projectExchange'),
    projectPortfolioField: document.getElementById('projectPortfolioField'),
    projectLeaderField: document.getElementById('projectLeaderField'),
    projectPortfolioId: document.getElementById('projectPortfolioId'),
    projectLeaderId: document.getElementById('projectLeaderId'),
    accountExchangeSelect: document.getElementById('accountExchangeSelect'),
    accountNetworkField: document.getElementById('accountNetworkField'),
    accountPassphraseField: document.getElementById('accountPassphraseField'),
    accountSimulatedField: document.getElementById('accountSimulatedField'),
    okxCopyAccountSelect: document.getElementById('okxCopyAccountSelect'),
    okxInstId: document.getElementById('okxInstId'),
    okxSubPosId: document.getElementById('okxSubPosId'),
    okxTpPx: document.getElementById('okxTpPx'),
    okxSlPx: document.getElementById('okxSlPx'),
    okxTpType: document.getElementById('okxTpType'),
    okxSlType: document.getElementById('okxSlType'),
    okxHistoryLimit: document.getElementById('okxHistoryLimit'),
    okxFetchInstruments: document.getElementById('okxFetchInstruments'),
    okxSetInstruments: document.getElementById('okxSetInstruments'),
    okxFetchPositions: document.getElementById('okxFetchPositions'),
    okxFetchHistory: document.getElementById('okxFetchHistory'),
    okxPlaceStop: document.getElementById('okxPlaceStop'),
    okxClosePosition: document.getElementById('okxClosePosition'),
    okxProfitSharing: document.getElementById('okxProfitSharing'),
    okxCopyOutput: document.getElementById('okxCopyOutput'),
    onchainEnabled: document.getElementById('onchainEnabled'),
    onchainChain: document.getElementById('onchainChain'),
    onchainRpcUrl: document.getElementById('onchainRpcUrl'),
    onchainPollInterval: document.getElementById('onchainPollInterval'),
    onchainIgnoreMints: document.getElementById('onchainIgnoreMints'),
    onchainWalletList: document.getElementById('onchainWalletList'),
    onchainAddWallet: document.getElementById('onchainAddWallet'),
    onchainSaveConfig: document.getElementById('onchainSaveConfig'),
    onchainEventsBody: document.getElementById('onchainEventsBody')
  };

  const TRANSLATIONS = {
    en: {
      brand_sub: 'Multi-Exchange Copy Trading Console',
      status_connecting: 'Connecting...',
      status_connected: 'Connected',
      status_disconnected: 'Disconnected',
      status_label: 'Status',
      status_running: 'Running',
      status_stopped: 'Stopped',
      status_unknown: 'Unknown',
      action_connect: 'Connect',
      action_theme_dark: 'Dark Mode',
      action_theme_light: 'Light Mode',
      action_refresh_now: 'Refresh now',
      action_go_config: 'Go to configuration',
      action_refresh: 'Refresh',
      action_prev: 'Prev',
      action_next: 'Next',
      action_pause: 'Pause',
      action_resume: 'Resume',
      action_remove: 'Remove',
      action_create_project: 'Create project',
      action_add_account: 'Add account',
      action_save_allocation: 'Save allocation',
      action_upload_cookies: 'Upload cookies',
      action_upload_cookie_text: 'Upload cookies (text)',
      action_okx_fetch_instruments: 'Fetch instruments',
      action_okx_set_instruments: 'Set instruments',
      action_okx_fetch_positions: 'Fetch positions',
      action_okx_fetch_history: 'Fetch history',
      action_okx_place_stop: 'Place stop',
      action_okx_close_position: 'Close position',
      action_okx_profit_sharing: 'Profit sharing',
      action_add_wallet: 'Add wallet',
      action_save_onchain: 'Save onchain',
      hero_eyebrow: 'Realtime copy trading control',
      hero_title: 'Precision control for fast-follow execution.',
      hero_body: 'Track leader activity, follower exposure, and system health from one bright command panel.',
      label_total_equity: 'Total Equity',
      label_margin_balance: 'Margin Balance',
      label_margin_meta: 'Account margin balance',
      label_allocated: 'Allocated',
      label_available: 'Available',
      label_allocated_meta: 'Allocated allocation',
      label_available_meta: 'Free margin allocation',
      tab_dashboard: 'Dashboard',
      tab_positions: 'Positions',
      tab_history: 'History',
      tab_config: 'Configuration',
      metric_service: 'Service',
      metric_running_projects: 'Running Projects',
      metric_open_positions: 'Open Positions',
      metric_actions_today: 'Actions Today',
      label_open: 'Open',
      label_add: 'Add',
      label_reduce: 'Reduce',
      label_close: 'Close',
      panel_active_projects: 'Active Projects',
      th_portfolio: 'Portfolio',
      th_exchange: 'Exchange',
      th_leader: 'Leader',
      th_account: 'Account',
      th_mode: 'Mode',
      th_allocation: 'Allocation',
      th_status: 'Status',
      th_actions: 'Actions',
      th_symbol: 'Symbol',
      th_side: 'Side',
      th_position: 'Position',
      th_size: 'Size',
      th_leverage: 'Leverage',
      th_entry: 'Entry',
      th_mark: 'Mark',
      th_pnl: 'PnL',
      th_time: 'Time',
      th_action: 'Action',
      th_price: 'Price',
      th_level: 'Level',
      th_message: 'Message',
      th_account_id: 'ID',
      th_account_name: 'Name',
      th_wallet: 'Wallet',
      th_mint: 'Mint',
      th_direction: 'Direction',
      th_token_change: 'Token Change',
      th_sol_change: 'SOL Change',
      th_signature: 'Signature',
      panel_leader_positions: 'Leader Positions',
      panel_follower_positions: 'Follower Positions',
      panel_action_history: 'Action History',
      panel_system_logs: 'System Logs',
      panel_create_project: 'Create Project',
      panel_api_accounts: 'API Accounts',
      panel_allocation_manager: 'Allocation Manager',
      panel_cookie_upload: 'Cookie Upload',
      panel_okx_copytrading: 'OKX Copy Trading',
      panel_onchain_copy: 'Onchain Wallet Copy',
      panel_onchain_events: 'Onchain Events',
      label_exchange: 'Exchange',
      label_binance_portfolio: 'Binance Portfolio ID',
      label_okx_leader: 'OKX Leader Unique Code',
      label_trade_account: 'Trade Account',
      label_default_account: 'Default',
      label_monitor_mode: 'Monitor Mode',
      label_scale_mode: 'Scale Mode',
      label_scale_value: 'Scale Value',
      label_follower_leverage: 'Follower Leverage',
      label_enabled: 'Enabled',
      label_account_id: 'Account ID',
      label_account_name: 'Account Name',
      label_network: 'Network',
      label_api_key: 'API Key',
      label_api_secret: 'API Secret',
      label_okx_passphrase: 'OKX Passphrase',
      label_okx_simulated: 'OKX Simulated',
      label_okx_account: 'OKX Account',
      label_okx_inst_id: 'Instrument ID',
      label_okx_sub_pos: 'Sub Position ID',
      label_okx_tp_px: 'TP Trigger Price',
      label_okx_sl_px: 'SL Trigger Price',
      label_okx_tp_type: 'TP Trigger Type',
      label_okx_sl_type: 'SL Trigger Type',
      label_okx_history_limit: 'History Limit',
      label_okx_output: 'Output',
      label_onchain_enabled: 'Onchain Enabled',
      label_onchain_chain: 'Chain',
      label_onchain_rpc: 'RPC URL',
      label_onchain_poll: 'Poll Interval (ms)',
      label_onchain_ignore_mints: 'Ignore Mints',
      label_onchain_wallets: 'Wallets',
      label_cookie_file: 'Cookie file (.json)',
      label_cookie_text: 'Paste request headers',
      label_all_accounts: 'All accounts',
      label_loading_projects: 'Loading projects...',
      label_no_projects: 'No projects configured',
      label_no_leader_positions: 'No leader positions',
      label_no_follower_positions: 'No follower positions',
      label_no_actions: 'No actions yet',
      label_no_logs: 'No logs yet',
      label_no_accounts: 'No accounts configured',
      label_no_projects_allocate: 'No projects to allocate.',
      label_no_onchain_events: 'No onchain events',
      label_project_created: 'Project created',
      label_account_added: 'Account added',
      label_cookies_uploaded: 'Cookies uploaded',
      label_allocation_saved: 'Allocation saved',
      label_onchain_saved: 'Onchain config saved',
      label_project_resumed: 'Project resumed',
      label_project_paused: 'Project paused',
      label_project_removed: 'Project removed',
      label_active: 'Active',
      label_paused: 'Paused',
      label_page_info: 'Page {page} of {total}',
      option_binance: 'Binance',
      option_okx: 'OKX',
      option_solana: 'Solana',
      option_mainnet: 'Mainnet',
      option_testnet: 'Testnet',
      option_position: 'Position',
      option_order_history: 'Order History',
      option_scale_margin_ratio: 'Margin Ratio',
      option_scale_ratio: 'Ratio',
      option_scale_fixed: 'Fixed',
      option_scale_adaptive: 'Adaptive',
      option_scale_leader_margin: 'Leader Margin',
      placeholder_portfolio_id: 'e.g. 123456789',
      placeholder_okx_leader: 'e.g. 6B7YB9YH',
      placeholder_account_id: 'main-1',
      placeholder_account_name: 'Main Account',
      placeholder_cookie_text: 'Paste the request headers here (including the cookie line).',
      placeholder_wallet_address: 'e.g. 9xQeWvG816bUx9...',
      placeholder_ignore_mints: 'One mint per line',
      confirm_remove_project: 'Remove this project?',
      error_okx_leader_required: 'OKX leader unique code is required',
      error_portfolio_required: 'Portfolio ID is required'
    },
    zh: {
      brand_sub: '多交易所跟单控制台',
      status_connecting: '连接中...',
      status_connected: '已连接',
      status_disconnected: '未连接',
      status_label: '状态',
      status_running: '运行中',
      status_stopped: '已停止',
      status_unknown: '未知',
      action_connect: '连接',
      action_theme_dark: '夜间模式',
      action_theme_light: '日间模式',
      action_refresh_now: '立即刷新',
      action_go_config: '前往配置',
      action_refresh: '刷新',
      action_prev: '上一页',
      action_next: '下一页',
      action_pause: '暂停',
      action_resume: '恢复',
      action_remove: '移除',
      action_create_project: '创建项目',
      action_add_account: '新增账户',
      action_save_allocation: '保存分配',
      action_upload_cookies: '上传 Cookie',
      action_upload_cookie_text: '上传 Cookie（文本）',
      action_okx_fetch_instruments: '获取标的',
      action_okx_set_instruments: '设置标的',
      action_okx_fetch_positions: '获取持仓',
      action_okx_fetch_history: '获取历史',
      action_okx_place_stop: '设置止盈止损',
      action_okx_close_position: '平仓',
      action_okx_profit_sharing: '分润',
      hero_eyebrow: '实时跟单控制',
      hero_title: '精准掌控高速跟单执行。',
      hero_body: '在一个清爽的控制面板内追踪带单动向、跟随风险与系统健康。',
      label_total_equity: '总权益',
      label_margin_balance: '保证金余额',
      label_margin_meta: '账户保证金余额',
      label_allocated: '已分配',
      label_available: '可用',
      label_allocated_meta: '分配占比',
      label_available_meta: '可用占比',
      tab_dashboard: '仪表盘',
      tab_positions: '持仓',
      tab_history: '历史',
      tab_config: '配置',
      metric_service: '服务',
      metric_running_projects: '运行项目',
      metric_open_positions: '持仓数量',
      metric_actions_today: '今日动作',
      label_open: '开仓',
      label_add: '加仓',
      label_reduce: '减仓',
      label_close: '平仓',
      panel_active_projects: '在运行项目',
      th_portfolio: '组合ID',
      th_exchange: '交易所',
      th_leader: '带单员',
      th_account: '账户',
      th_mode: '模式',
      th_allocation: '分配',
      th_status: '状态',
      th_actions: '操作',
      th_symbol: '品种',
      th_side: '方向',
      th_position: '持仓方向',
      th_size: '数量',
      th_leverage: '杠杆',
      th_entry: '开仓价',
      th_mark: '标记价',
      th_pnl: '盈亏',
      th_time: '时间',
      th_action: '动作',
      th_price: '价格',
      th_level: '等级',
      th_message: '内容',
      th_account_id: '账户ID',
      th_account_name: '名称',
      panel_leader_positions: '带单员持仓',
      panel_follower_positions: '跟随者持仓',
      panel_action_history: '动作记录',
      panel_system_logs: '系统日志',
      panel_create_project: '创建项目',
      panel_api_accounts: 'API账户',
      panel_allocation_manager: '分配管理',
      panel_cookie_upload: 'Cookie 上传',
      panel_okx_copytrading: 'OKX 跟单',
      label_exchange: '交易所',
      label_binance_portfolio: 'Binance 组合ID',
      label_okx_leader: 'OKX 带单员唯一ID',
      label_trade_account: '交易账户',
      label_default_account: '默认',
      label_monitor_mode: '监控模式',
      label_scale_mode: '倍率模式',
      label_scale_value: '倍率值',
      label_follower_leverage: '跟随杠杆',
      label_enabled: '启用',
      label_account_id: '账户ID',
      label_account_name: '账户名称',
      label_network: '网络',
      label_api_key: 'API Key（密钥）',
      label_api_secret: 'API Secret（密钥）',
      label_okx_passphrase: 'OKX 口令',
      label_okx_simulated: 'OKX 模拟盘',
      label_okx_account: 'OKX 账户',
      label_okx_inst_id: '合约ID',
      label_okx_sub_pos: '子持仓ID',
      label_okx_tp_px: '止盈触发价',
      label_okx_sl_px: '止损触发价',
      label_okx_tp_type: '止盈触发类型',
      label_okx_sl_type: '止损触发类型',
      label_okx_history_limit: '历史条数',
      label_okx_output: '输出',
      label_cookie_file: 'Cookie 文件 (.json)',
      label_cookie_text: '粘贴请求头',
      label_all_accounts: '全部账户',
      label_loading_projects: '加载中...',
      label_no_projects: '暂无项目',
      label_no_leader_positions: '暂无带单持仓',
      label_no_follower_positions: '暂无跟随持仓',
      label_no_actions: '暂无动作',
      label_no_logs: '暂无日志',
      label_no_accounts: '暂无账户',
      label_no_projects_allocate: '暂无可分配项目。',
      label_project_created: '项目已创建',
      label_account_added: '账户已添加',
      label_cookies_uploaded: 'Cookie 已上传',
      label_allocation_saved: '分配已保存',
      label_project_resumed: '项目已启用',
      label_project_paused: '项目已暂停',
      label_project_removed: '项目已删除',
      label_active: '运行中',
      label_paused: '已暂停',
      label_page_info: '第 {page}/{total} 页',
      option_binance: '币安',
      option_okx: 'OKX',
      option_mainnet: '主网',
      option_testnet: '测试网',
      option_position: '持仓',
      option_order_history: '订单历史',
      option_scale_margin_ratio: '保证金比例',
      option_scale_ratio: '比例',
      option_scale_fixed: '固定',
      option_scale_adaptive: '自适应',
      option_scale_leader_margin: '带单保证金',
      placeholder_portfolio_id: '例如 123456789',
      placeholder_okx_leader: '例如 6B7YB9YH',
      placeholder_account_id: 'main-1',
      placeholder_account_name: '主账户',
      placeholder_cookie_text: '粘贴请求头（包含 cookie 行）',
      confirm_remove_project: '确定删除该项目？',
      error_okx_leader_required: '需要填写 OKX 带单员唯一ID',
      error_portfolio_required: '需要填写组合ID',
      panel_onchain_copy: '链上钱包复制',
      panel_onchain_events: '链上事件',
      label_onchain_enabled: '启用链上',
      label_onchain_chain: '链',
      label_onchain_rpc: 'RPC 地址',
      label_onchain_poll: '轮询间隔（毫秒）',
      label_onchain_ignore_mints: '忽略 Mint',
      label_onchain_wallets: '钱包列表',
      label_no_onchain_events: '暂无链上事件',
      label_onchain_saved: '链上配置已保存',
      th_wallet: '钱包',
      th_mint: 'Mint',
      th_direction: '方向',
      th_token_change: '代币变化',
      th_sol_change: 'SOL 变化',
      th_signature: '签名',
      action_add_wallet: '添加钱包',
      action_save_onchain: '保存链上配置',
      option_solana: 'Solana',
      placeholder_wallet_address: '例如 9xQeWvG816bUx9...',
      placeholder_ignore_mints: '每行一个 Mint',

    }
  };

  const LANGUAGE_STORAGE_KEY = 'copy-sync-lang';
  const THEME_STORAGE_KEY = 'copy-sync-theme';
  const AUTO_THEME_INTERVAL_MS = 60 * 1000;
  let autoThemeEnabled = false;
  let autoThemeTimer = null;

  const template = (text, params = {}) => {
    return String(text || '').replace(/\{(\w+)\}/g, (match, key) => {
      const value = params[key];
      return value === undefined ? match : String(value);
    });
  };

  const t = (key, params) => {
    const lang = state.language || 'en';
    const dict = TRANSLATIONS[lang] || TRANSLATIONS.en;
    const fallback = TRANSLATIONS.en || {};
    const value = dict[key] ?? fallback[key] ?? key;
    return params ? template(value, params) : value;
  };

  function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.dataset.i18n;
      el.textContent = t(key);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      const key = el.dataset.i18nPlaceholder;
      el.setAttribute('placeholder', t(key));
    });

    if (elements.serviceStatus) {
      elements.serviceStatus.textContent = `${t('status_label')}: ${t('status_unknown')}`;
    }
    if (elements.serviceStatusText) {
      elements.serviceStatusText.textContent = t('status_unknown');
    }
  }

  function setLanguage(lang) {
    const resolved = TRANSLATIONS[lang] ? lang : 'en';
    state.language = resolved;
    document.documentElement.lang = resolved === 'zh' ? 'zh-CN' : 'en';
    localStorage.setItem(LANGUAGE_STORAGE_KEY, resolved);
    if (elements.languageToggle) {
      elements.languageToggle.textContent = resolved === 'zh' ? 'English' : '中文';
    }
    applyTranslations();
    setTheme(document.documentElement.getAttribute('data-theme') || 'light', { persist: false });
  }

  function initLanguage() {
    const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (saved && TRANSLATIONS[saved]) {
      setLanguage(saved);
      return;
    }
    const guess = (navigator.language || '').toLowerCase();
    setLanguage(guess.startsWith('zh') ? 'zh' : 'en');
  }

  const Toast = {
    container: null,
    init() {
      this.container = document.createElement('div');
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    },
    show(message, type = 'info') {
      if (!this.container) this.init();
      const toast = document.createElement('div');
      toast.className = `toast ${type}`;
      toast.textContent = message;
      this.container.appendChild(toast);
      setTimeout(() => {
        toast.remove();
      }, 3200);
    },
    success(message) {
      this.show(message, 'success');
    },
    error(message) {
      this.show(message, 'error');
    }
  };

  const formatNumber = (value, decimals = 2) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    return Number(value).toFixed(decimals);
  };

  const formatUSD = (value, decimals = 2) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    return `$${formatNumber(value, decimals)}`;
  };

  const formatPercent = (value, decimals = 1) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    return `${formatNumber(value, decimals)}%`;
  };

  const formatTime = (value) => {
    if (!value) return '--';
    return new Date(value).toLocaleString();
  };

  const formatSigned = (value, decimals = 6) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    const numeric = Number(value);
    const fixed = numeric.toFixed(decimals);
    if (numeric > 0) return `+${fixed}`;
    return fixed;
  };

  const formatShort = (value, head = 6, tail = 4) => {
    const text = String(value || '');
    if (!text) return '--';
    if (text.length <= head + tail + 2) return text;
    return `${text.slice(0, head)}...${text.slice(-tail)}`;
  };

  const formatMonitorMode = (value) => {
    if (value === 'order_history') return t('option_order_history');
    return t('option_position');
  };

  const formatAction = (value) => {
    const key = {
      open: 'label_open',
      add: 'label_add',
      reduce: 'label_reduce',
      close: 'label_close'
    }[value];
    return key ? t(key) : value || '--';
  };

  const getAllocationAccountId = () => {
    if (state.allocationAccountId) return state.allocationAccountId;
    if (state.accounts.length) return state.accounts[0].account_id;
    return 'default';
  };

  const normalizeAccountId = (value) => String(value || '').trim();

  const resolveAccount = (accountId) => {
    const target = normalizeAccountId(accountId);
    if (!target) return null;
    return (state.accounts || []).find((account) => account.account_id === target) || null;
  };

  const projectMatchesAccount = (project, accountId) => {
    const target = normalizeAccountId(accountId);
    const projectAccount = normalizeAccountId(project.trade_account_id);
    if (!target || target === 'default') {
      return !projectAccount || projectAccount === 'default';
    }
    const account = resolveAccount(target);
    if (account && account.exchange && project.exchange && account.exchange !== project.exchange) {
      return false;
    }
    return projectAccount === target;
  };

  const parseLineList = (value) => {
    return String(value || '')
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter((item) => item);
  };

  async function apiRequest(path, options = {}) {
    const config = {
      method: 'GET',
      headers: {},
      ...options
    };

    if (config.body instanceof FormData) {
      delete config.headers['Content-Type'];
    } else if (config.body) {
      config.headers['Content-Type'] = 'application/json';
      config.body = JSON.stringify(config.body);
    }

    const response = await fetch(path, config);
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json')
      ? await response.json().catch(() => null)
      : await response.text().catch(() => null);

    if (!response.ok) {
      const message = payload?.detail || payload?.message || response.statusText;
      throw new Error(message || `HTTP ${response.status}`);
    }

    return payload;
  }

  function setTheme(theme, options = {}) {
    const { persist = true } = options;
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    const isDark = theme === 'dark';
    if (elements.themeToggle) {
      elements.themeToggle.setAttribute('aria-pressed', String(isDark));
      elements.themeToggle.textContent = isDark ? t('action_theme_light') : t('action_theme_dark');
    }
    if (persist) {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    }
  }

  function initTheme() {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (saved) {
      stopAutoTheme();
      setTheme(saved, { persist: false });
      return;
    }
    startAutoTheme();
  }

  function resolveAutoTheme() {
    const hour = new Date().getHours();
    return hour >= 7 && hour < 19 ? 'light' : 'dark';
  }

  function startAutoTheme() {
    autoThemeEnabled = true;
    if (autoThemeTimer) {
      clearInterval(autoThemeTimer);
    }
    setTheme(resolveAutoTheme(), { persist: false });
    autoThemeTimer = setInterval(() => {
      if (!autoThemeEnabled) return;
      setTheme(resolveAutoTheme(), { persist: false });
    }, AUTO_THEME_INTERVAL_MS);
  }

  function stopAutoTheme() {
    autoThemeEnabled = false;
    if (autoThemeTimer) {
      clearInterval(autoThemeTimer);
      autoThemeTimer = null;
    }
  }

  function setupTabs() {
    const buttons = document.querySelectorAll('.tab');
    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        buttons.forEach((node) => node.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach((panel) => panel.classList.remove('active'));
        btn.classList.add('active');
        const target = btn.dataset.tab;
        const panel = document.getElementById(target);
        if (panel) panel.classList.add('active');
      });
    });
  }

  async function refreshStatus() {
    const data = await apiRequest('/api/status');
    if (!data) return;
    const connected = Boolean(data.connected);
    elements.connectionStatus.classList.toggle('connected', connected);
    elements.connectionStatus.classList.toggle('disconnected', !connected);
    const statusText = elements.connectionStatus.querySelector('.status-text');
    if (statusText) statusText.textContent = connected ? t('status_connected') : t('status_disconnected');
    if (elements.connectBtn) elements.connectBtn.disabled = connected;

    const runningText = data.running ? t('status_running') : t('status_stopped');
    if (elements.serviceStatus) {
      elements.serviceStatus.textContent = `${t('status_label')}: ${runningText}`;
    }
    if (elements.serviceStatusText) {
      elements.serviceStatusText.textContent = runningText;
    }
  }

  async function updateProjects() {
    const projects = await apiRequest('/api/projects');
    if (!Array.isArray(projects)) return;
    state.projects = projects;
    elements.projectCount.textContent = projects.filter((p) => p.enabled).length;
    renderProjects(projects);
    await updateAllocationList();
  }

  function renderProjects(projects) {
    if (!projects.length) {
      elements.projectsBody.innerHTML = `<tr class="empty"><td colspan="8">${t('label_no_projects')}</td></tr>`;
      return;
    }

    elements.projectsBody.innerHTML = projects.map((project) => {
      const projectId = project.project_id || project.portfolio_id || project.leader_id || '';
      const encodedId = encodeURIComponent(projectId);
      const displayId = project.portfolio_id || project.leader_id || projectId;
      const enabled = Boolean(project.enabled);
      const allocation = formatPercent(project.allocated_equity_pct || 0);
      const exchange = project.exchange || 'binance';
      const modeLabel = formatMonitorMode(project.monitor_mode);
      const accountLabel = project.trade_account_id || t('label_default_account');
      const statusLabel = enabled ? t('label_active') : t('label_paused');
      return `
        <tr>
          <td>${displayId || '--'}</td>
          <td>${exchange.toUpperCase()}</td>
          <td>${project.leader_id || '--'}</td>
          <td>${accountLabel}</td>
          <td>${modeLabel}</td>
          <td>${allocation}</td>
          <td>
            <span class="status-pill ${enabled ? '' : 'off'}">
              ${statusLabel}
            </span>
          </td>
          <td>
            <div class="project-actions">
              <button
                type="button"
                class="btn btn-ghost"
                data-action="toggle-project"
                data-project-id="${encodedId}"
                data-next-enabled="${enabled ? 'false' : 'true'}"
              >
                ${enabled ? t('action_pause') : t('action_resume')}
              </button>
              <button
                type="button"
                class="btn btn-ghost"
                data-action="delete-project"
                data-project-id="${encodedId}"
              >
                ${t('action_remove')}
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    // Action handlers are delegated to avoid re-binding on every refresh.
  }

  async function updateLeaderPositions() {
    const data = await apiRequest('/api/leader-positions');
    if (!Array.isArray(data)) return;
    if (!data.length) {
      elements.leaderPositionsBody.innerHTML = `<tr class="empty"><td colspan="9">${t('label_no_leader_positions')}</td></tr>`;
      return;
    }
    elements.leaderPositionsBody.innerHTML = data.map((pos) => {
      return `
        <tr>
          <td>${pos.portfolio_id || '--'}</td>
          <td>${pos.symbol || '--'}</td>
          <td>${pos.side || '--'}</td>
          <td>${pos.position_side || '--'}</td>
          <td>${formatNumber(pos.qty || 0, 4)}</td>
          <td>${pos.leverage || 0}x</td>
          <td>${formatUSD(pos.entry_price || 0)}</td>
          <td>${formatUSD(pos.mark_price || 0)}</td>
          <td>${formatUSD(pos.unrealized_pnl || 0)}</td>
        </tr>
      `;
    }).join('');
  }

  async function updateFollowerPositions() {
    const accountId = elements.accountSelect.value;
    const url = accountId ? `/api/follower-positions?account_id=${encodeURIComponent(accountId)}` : '/api/follower-positions';
    const data = await apiRequest(url);
    if (!Array.isArray(data)) return;
    elements.positionCount.textContent = data.length;
    if (!data.length) {
      elements.followerPositionsBody.innerHTML = `<tr class="empty"><td colspan="7">${t('label_no_follower_positions')}</td></tr>`;
      return;
    }
    elements.followerPositionsBody.innerHTML = data.map((pos) => {
      return `
        <tr>
          <td>${pos.symbol || '--'}</td>
          <td>${pos.positionSide || '--'}</td>
          <td>${formatNumber(Math.abs(pos.positionAmt || 0), 4)}</td>
          <td>${pos.leverage || 0}x</td>
          <td>${formatUSD(pos.entryPrice || 0)}</td>
          <td>${formatUSD(pos.markPrice || 0)}</td>
          <td>${formatUSD(pos.unRealizedProfit || 0)}</td>
        </tr>
      `;
    }).join('');
  }

  async function updateEvents() {
    const data = await apiRequest('/api/events?limit=200');
    if (!Array.isArray(data)) return;
    state.allEvents = data;
    elements.actionCount.textContent = data.length;

    const counts = { open: 0, add: 0, reduce: 0, close: 0 };
    data.forEach((event) => {
      if (counts[event.action] !== undefined) counts[event.action] += 1;
    });

    elements.openCount.textContent = counts.open;
    elements.addCount.textContent = counts.add;
    elements.reduceCount.textContent = counts.reduce;
    elements.closeCount.textContent = counts.close;
    renderHistory();
  }

  async function updateLogs() {
    const data = await apiRequest('/api/logs?limit=200');
    if (!Array.isArray(data)) return;
    state.allLogs = data;
    renderLogs();
  }

  function createOnchainWalletRow(wallet) {
    const row = document.createElement('div');
    row.className = 'wallet-row';
    const address = wallet && wallet.address ? String(wallet.address) : '';
    const enabled = wallet ? wallet.enabled !== false : true;
    row.innerHTML = `
      <input
        type="text"
        class="wallet-address"
        value="${address}"
        placeholder="${t('placeholder_wallet_address')}"
        data-i18n-placeholder="placeholder_wallet_address"
      />
      <label class="checkbox">
        <input type="checkbox" class="wallet-enabled" ${enabled ? 'checked' : ''} />
        <span data-i18n="label_enabled">${t('label_enabled')}</span>
      </label>
      <button type="button" class="btn btn-ghost btn-small wallet-remove" data-i18n="action_remove">
        ${t('action_remove')}
      </button>
    `;
    const removeBtn = row.querySelector('.wallet-remove');
    if (removeBtn) {
      removeBtn.addEventListener('click', () => {
        row.remove();
      });
    }
    return row;
  }

  function renderOnchainWallets(wallets) {
    if (!elements.onchainWalletList) return;
    const list = elements.onchainWalletList;
    list.innerHTML = '';
    const items = wallets && wallets.length ? wallets : [{ address: '', enabled: true }];
    items.forEach((wallet) => {
      list.appendChild(createOnchainWalletRow(wallet));
    });
    applyTranslations();
  }

  function collectOnchainWallets() {
    if (!elements.onchainWalletList) return [];
    const seen = new Set();
    const wallets = [];
    elements.onchainWalletList.querySelectorAll('.wallet-row').forEach((row) => {
      const address = row.querySelector('.wallet-address')?.value?.trim();
      if (!address || seen.has(address)) return;
      seen.add(address);
      const enabled = row.querySelector('.wallet-enabled')?.checked ?? true;
      wallets.push({ address, enabled });
    });
    return wallets;
  }

  async function loadOnchainConfig() {
    if (!elements.onchainEnabled) return;
    const data = await apiRequest('/api/onchain/config');
    if (!data || typeof data !== 'object') return;
    state.onchainConfigLoaded = true;
    state.onchainConfig = data;
    elements.onchainEnabled.checked = Boolean(data.enabled);
    if (elements.onchainChain) {
      elements.onchainChain.value = data.chain || 'solana';
    }
    if (elements.onchainRpcUrl) {
      elements.onchainRpcUrl.value = data.rpc_url || '';
    }
    if (elements.onchainPollInterval) {
      elements.onchainPollInterval.value = Number(data.poll_interval_ms || 2000);
    }
    if (elements.onchainIgnoreMints) {
      elements.onchainIgnoreMints.value = (data.ignore_mints || []).join('\n');
    }
    renderOnchainWallets(data.wallets || []);
  }

  async function saveOnchainConfig() {
    if (!elements.onchainEnabled) return;
    let pollInterval = Number(elements.onchainPollInterval?.value || 0);
    if (!Number.isFinite(pollInterval) || pollInterval < 500) {
      pollInterval = 2000;
    }
    const rpcUrl = (elements.onchainRpcUrl?.value || '').trim();
    const payload = {
      enabled: Boolean(elements.onchainEnabled.checked),
      chain: elements.onchainChain?.value || 'solana',
      rpc_url: rpcUrl || 'https://api.mainnet-beta.solana.com',
      poll_interval_ms: pollInterval,
      ignore_mints: parseLineList(elements.onchainIgnoreMints?.value || ''),
      wallets: collectOnchainWallets()
    };
    await apiRequest('/api/onchain/config', { method: 'POST', body: payload });
    state.onchainConfigLoaded = true;
    state.onchainConfig = payload;
    Toast.success(t('label_onchain_saved'));
  }

  async function updateOnchainEvents() {
    if (!elements.onchainEventsBody) return;
    const data = await apiRequest('/api/onchain/events?limit=200');
    if (!Array.isArray(data)) return;
    renderOnchainEvents(data);
  }

  function renderOnchainEvents(events) {
    if (!elements.onchainEventsBody) return;
    if (!events.length) {
      elements.onchainEventsBody.innerHTML = `<tr class="empty"><td colspan="7" data-i18n="label_no_onchain_events">No onchain events</td></tr>`;
      applyTranslations();
      return;
    }
    elements.onchainEventsBody.innerHTML = events.map((event) => {
      const wallet = event.wallet || '--';
      const mint = event.mint || '--';
      const signature = event.signature || '--';
      const direction = (event.direction || '--').toUpperCase();
      const tokenRaw = Number(event.token_change || 0);
      const tokenSigned = event.direction === 'sell' ? -tokenRaw : tokenRaw;
      return `
        <tr>
          <td>${formatTime(event.timestamp)}</td>
          <td title="${wallet}">${formatShort(wallet, 6, 6)}</td>
          <td title="${mint}">${formatShort(mint, 6, 4)}</td>
          <td>${direction}</td>
          <td>${formatSigned(tokenSigned, 6)}</td>
          <td>${formatSigned(event.sol_change, 6)}</td>
          <td title="${signature}">${formatShort(signature, 8, 6)}</td>
        </tr>
      `;
    }).join('');
  }

  function renderHistory() {
    const pageSize = 20;
    const totalPages = Math.max(1, Math.ceil(state.allEvents.length / pageSize));
    if (state.historyPage > totalPages) state.historyPage = totalPages;
    const start = (state.historyPage - 1) * pageSize;
    const page = state.allEvents.slice(start, start + pageSize);

    if (!page.length) {
      elements.historyBody.innerHTML = `<tr class="empty"><td colspan="6">${t('label_no_actions')}</td></tr>`;
    } else {
      elements.historyBody.innerHTML = page.map((event) => {
        return `
          <tr>
            <td>${formatTime(event.created_at)}</td>
            <td>${formatAction(event.action)}</td>
            <td>${event.symbol || '--'}</td>
            <td>${event.side || '--'}</td>
            <td>${formatNumber(event.executed_qty || 0, 4)}</td>
            <td>${formatUSD(event.avg_price || 0)}</td>
          </tr>
        `;
      }).join('');
    }

    elements.historyInfo.textContent = t('label_page_info', {
      page: state.historyPage,
      total: totalPages
    });
    elements.historyPrev.disabled = state.historyPage <= 1;
    elements.historyNext.disabled = state.historyPage >= totalPages;
  }

  function renderLogs() {
    const pageSize = 20;
    const totalPages = Math.max(1, Math.ceil(state.allLogs.length / pageSize));
    if (state.logsPage > totalPages) state.logsPage = totalPages;
    const start = (state.logsPage - 1) * pageSize;
    const page = state.allLogs.slice(start, start + pageSize);

    if (!page.length) {
      elements.logsBody.innerHTML = `<tr class="empty"><td colspan="3">${t('label_no_logs')}</td></tr>`;
    } else {
      elements.logsBody.innerHTML = page.map((log) => {
        return `
          <tr>
            <td>${formatTime(log.ts)}</td>
            <td>${log.level || 'INFO'}</td>
            <td>${log.message || '--'}</td>
          </tr>
        `;
      }).join('');
    }

    elements.logsInfo.textContent = t('label_page_info', {
      page: state.logsPage,
      total: totalPages
    });
    elements.logsPrev.disabled = state.logsPage <= 1;
    elements.logsNext.disabled = state.logsPage >= totalPages;
  }

  async function updateAccounts() {
    const data = await apiRequest('/api/accounts');
    if (!Array.isArray(data)) return;
    state.accounts = data;
    renderAccountsTable(data);
    renderAccountOptions(data);
    renderOkxAccounts(data);
  }

  function renderAccountsTable(accounts) {
    if (!accounts.length) {
      elements.accountsBody.innerHTML = `<tr class="empty"><td colspan="4">${t('label_no_accounts')}</td></tr>`;
      return;
    }
    elements.accountsBody.innerHTML = accounts.map((account) => {
      const exchangeLabel = account.exchange || '--';
      const simTag = account.exchange === 'okx' && account.simulated ? ' (Sim)' : '';
      return `
        <tr>
          <td>${account.account_id || '--'}</td>
          <td>${account.name || '--'}</td>
          <td>${exchangeLabel}${simTag}</td>
          <td>${account.enabled ? 'Enabled' : 'Disabled'}</td>
        </tr>
      `;
    }).join('');
  }

  function renderAccountOptions(accounts) {
    const currentAccount = elements.accountSelect.value;
    const options = [`<option value="">${t('label_all_accounts')}</option>`];
    accounts.forEach((account) => {
      const label = account.name || account.account_id;
      const suffix = account.exchange ? ` (${account.exchange})` : '';
      options.push(`<option value="${account.account_id}">${label}${suffix}</option>`);
    });
    elements.accountSelect.innerHTML = options.join('');
    if (currentAccount) {
      elements.accountSelect.value = currentAccount;
    }

    const currentProjectAccount = elements.projectAccountSelect.value;
    const projectOptions = [`<option value="">${t('label_default_account')}</option>`];
    accounts.forEach((account) => {
      const label = account.name || account.account_id;
      const suffix = account.exchange ? ` (${account.exchange})` : '';
      projectOptions.push(`<option value="${account.account_id}">${label}${suffix}</option>`);
    });
    elements.projectAccountSelect.innerHTML = projectOptions.join('');
    if (currentProjectAccount) {
      elements.projectAccountSelect.value = currentProjectAccount;
    }

    if (elements.allocationAccountSelect) {
      const allocationOptions = [`<option value="default">${t('label_default_account')}</option>`];
      if (accounts.length) {
        accounts.forEach((account) => {
          const label = account.name || account.account_id;
          const suffix = account.exchange ? ` (${account.exchange})` : '';
          allocationOptions.push(
            `<option value="${account.account_id}">${label}${suffix}</option>`
          );
        });
      }
      elements.allocationAccountSelect.innerHTML = allocationOptions.join('');

      const hasDefaultProjects = (state.projects || []).some((project) => {
        const projectAccount = normalizeAccountId(project.trade_account_id);
        return !projectAccount || projectAccount === 'default';
      });
      const preferred = state.allocationAccountId;
      const exists = preferred === 'default'
        || accounts.some((account) => account.account_id === preferred);
      if (exists) {
        state.allocationAccountId = preferred;
      } else if (hasDefaultProjects) {
        state.allocationAccountId = 'default';
      } else if (accounts.length) {
        state.allocationAccountId = accounts[0].account_id;
      } else {
        state.allocationAccountId = 'default';
      }
      elements.allocationAccountSelect.value = state.allocationAccountId;
    }
  }

  function renderOkxAccounts(accounts) {
    if (!elements.okxCopyAccountSelect) return;
    const okxAccounts = (accounts || []).filter((account) => account.exchange === 'okx');
    if (!okxAccounts.length) {
      elements.okxCopyAccountSelect.innerHTML = `<option value="">${t('label_no_accounts')}</option>`;
      return;
    }
    const options = okxAccounts.map((account) => {
      const label = account.name || account.account_id;
      return `<option value="${account.account_id}">${label}</option>`;
    });
    elements.okxCopyAccountSelect.innerHTML = options.join('');
  }

  function getOkxAccountId() {
    return elements.okxCopyAccountSelect?.value || '';
  }

  function renderOkxOutput(payload) {
    if (!elements.okxCopyOutput) return;
    const text = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
    elements.okxCopyOutput.value = text;
  }

  function buildOkxUrl(path, params = {}) {
    const search = new URLSearchParams();
    const accountId = getOkxAccountId();
    if (accountId) {
      search.append('account_id', accountId);
    }
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      search.append(key, String(value));
    });
    const query = search.toString();
    return query ? `${path}?${query}` : path;
  }

  async function updateAllocationSummary() {
    const accountId = getAllocationAccountId();
    const url = accountId ? `/api/account-summary?account_id=${encodeURIComponent(accountId)}` : '/api/account-summary';
    const summary = await apiRequest(url);
    if (!summary) return;

    elements.totalEquity.textContent = formatUSD(summary.total_equity || 0);
    if (elements.marginBalance) {
      elements.marginBalance.textContent = formatUSD(summary.margin_balance || 0);
    }
    elements.allocatedPercent.textContent = formatPercent(summary.total_allocated_pct || 0);
    elements.availablePercent.textContent = formatPercent(summary.available_pct || 0);

    elements.allocationEquity.textContent = formatUSD(summary.total_equity || 0);
    if (elements.allocationMargin) {
      elements.allocationMargin.textContent = formatUSD(summary.margin_balance || 0);
    }
    elements.allocationTotal.textContent = formatPercent(summary.total_allocated_pct || 0);
    elements.allocationAvailable.textContent = formatPercent(summary.available_pct || 0);
  }

  async function updateAllocationList() {
    if (!elements.allocationList) return;
    const accountId = getAllocationAccountId();
    const url = accountId ? `/api/allocation?account_id=${encodeURIComponent(accountId)}` : '/api/allocation';
    const data = await apiRequest(url);
    if (!data) return;
    state.allocations = data.allocations || {};
    state.leverages = data.leverages || {};
    if (!state.allocationsDirty) {
      state.allocationsDraft = { ...state.allocations };
      state.leveragesDraft = { ...state.leverages };
    }
    renderAllocationList();
  }

  function renderAllocationList() {
    const accountId = getAllocationAccountId();
    const projects = (state.projects || []).filter((project) => projectMatchesAccount(project, accountId));
    if (!projects.length) {
      elements.allocationList.innerHTML = `<div class="empty">${t('label_no_projects_allocate')}</div>`;
      return;
    }

    elements.allocationList.innerHTML = projects.map((project) => {
      const projectId = project.project_id || project.portfolio_id || project.leader_id || '';
      const displayId = project.portfolio_id || project.leader_id || projectId;
      const current = state.allocationsDraft[projectId];
      const value = current !== undefined ? current : (project.allocated_equity_pct || 0);
      const leverageCurrent = state.leveragesDraft[projectId];
      const leverageValue = leverageCurrent !== undefined ? leverageCurrent : (project.follower_leverage || 0);
      const accountLabel = project.trade_account_id || t('label_default_account');
      const modeLabel = formatMonitorMode(project.monitor_mode);
      return `
        <div class="allocation-row">
          <div>
            <strong>${displayId}</strong>
            <div class="muted">${accountLabel} / ${modeLabel}</div>
          </div>
          <div class="allocation-controls">
            <label class="allocation-field">
              <span>${t('label_allocated')}</span>
              <input
                type="number"
                min="0"
                max="100"
                step="0.1"
                data-portfolio="${projectId}"
                value="${value}"
              />
            </label>
            <label class="allocation-field">
              <span>${t('label_follower_leverage')}</span>
              <input
                type="number"
                min="1"
                max="125"
                step="1"
                data-leverage-portfolio="${projectId}"
                value="${leverageValue}"
              />
            </label>
          </div>
        </div>
      `;
    }).join('');

    elements.allocationList.querySelectorAll('input').forEach((input) => {
      input.addEventListener('input', (event) => {
        const target = event.target;
        const id = target.dataset.portfolio;
        const leverageId = target.dataset.leveragePortfolio;
        const numeric = Number(target.value);
        if (id) {
          let normalized = Number.isFinite(numeric) ? numeric : 0;
          if (normalized < 0) normalized = 0;
          if (normalized > 100) normalized = 100;
          if (normalized !== numeric) {
            target.value = String(normalized);
          }
          state.allocationsDraft[id] = normalized;
          state.allocationsDirty = true;
          refreshAllocationTotals();
          return;
        }
        if (leverageId) {
          state.leveragesDraft[leverageId] = Number.isFinite(numeric) ? numeric : 0;
          state.allocationsDirty = true;
        }
      });
    });

    refreshAllocationTotals();
  }

  function refreshAllocationTotals() {
    const accountId = getAllocationAccountId();
    const projectIds = (state.projects || [])
      .filter((project) => projectMatchesAccount(project, accountId))
      .map((project) => project.project_id || project.portfolio_id || project.leader_id || '')
      .filter((id) => id);
    const total = projectIds.reduce((sum, id) => {
      const value = state.allocationsDraft[id];
      return sum + (Number(value) || 0);
    }, 0);
    elements.allocationTotal.textContent = formatPercent(total, 1);
    elements.allocatedPercent.textContent = formatPercent(total, 1);
    elements.availablePercent.textContent = formatPercent(100 - total, 1);
    elements.allocationAvailable.textContent = formatPercent(100 - total, 1);
  }

  async function handleProjectSubmit(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const exchange = formData.get('exchange') || 'binance';
    const portfolioId = formData.get('portfolio_id')?.trim() || '';
    const leaderId = formData.get('leader_id')?.trim() || '';

    let resolvedPortfolio = portfolioId;
    let resolvedLeader = leaderId;

    if (exchange === 'okx') {
      if (!leaderId && !portfolioId) {
        throw new Error(t('error_okx_leader_required'));
      }
      resolvedLeader = leaderId || portfolioId;
      resolvedPortfolio = portfolioId || resolvedLeader;
    } else if (!portfolioId) {
      throw new Error(t('error_portfolio_required'));
    }

    const payload = {
      exchange,
      portfolio_id: resolvedPortfolio,
      leader_id: resolvedLeader,
      trade_account_id: formData.get('trade_account_id') || '',
      monitor_mode: formData.get('monitor_mode') || 'position',
      scale_mode: formData.get('scale_mode') || 'margin_ratio',
      scale_value: Number(formData.get('scale_value') || 1),
      follower_leverage: Number(formData.get('follower_leverage') || 20),
      enabled: Boolean(formData.get('enabled'))
    };

    await apiRequest('/api/projects', { method: 'POST', body: payload });
    Toast.success(t('label_project_created'));
    event.target.reset();
    setProjectExchange('binance');
    if (elements.allocationAccountSelect) {
      const desiredAccount = normalizeAccountId(payload.trade_account_id) || 'default';
      const options = Array.from(elements.allocationAccountSelect.options || []);
      const exists = options.some((option) => option.value === desiredAccount);
      if (exists) {
        state.allocationAccountId = desiredAccount;
        elements.allocationAccountSelect.value = desiredAccount;
      }
    }
    await updateProjects();
    await updateAllocationSummary();
  }

  async function handleAccountSubmit(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const exchange = formData.get('exchange') || 'binance';
    const network = formData.get('network') || 'mainnet';
    const baseUrl = network === 'testnet'
      ? 'https://testnet.binancefuture.com'
      : 'https://fapi.binance.com';
    const okxBaseUrl = 'https://www.okx.com';

    const payload = {
      account_id: formData.get('account_id')?.trim(),
      name: formData.get('name')?.trim(),
      exchange,
      api_key: formData.get('api_key')?.trim(),
      api_secret: formData.get('api_secret')?.trim(),
      enabled: true
    };

    if (exchange === 'binance') {
      payload.base_url = baseUrl;
    } else if (exchange === 'okx') {
      payload.base_url = okxBaseUrl;
      payload.passphrase = formData.get('passphrase')?.trim() || '';
      payload.simulated = formData.get('simulated') === 'on';
    }

    await apiRequest('/api/accounts', { method: 'POST', body: payload });
    Toast.success(t('label_account_added'));
    event.target.reset();
    setAccountExchange(elements.accountExchangeSelect?.value || 'binance');
    await updateAccounts();
  }

  async function handleCookieSubmit(event) {
    event.preventDefault();
    const fileInput = event.target.querySelector('input[type="file"]');
    if (!fileInput || !fileInput.files.length) return;
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    await apiRequest('/api/cookies', { method: 'POST', body: formData });
    Toast.success(t('label_cookies_uploaded'));
    event.target.reset();
  }

  async function handleCookieTextSubmit(event) {
    event.preventDefault();
    const raw = elements.cookieTextArea?.value || '';
    if (!raw.trim()) return;
    await apiRequest('/api/cookies/raw', { method: 'POST', body: { raw } });
    Toast.success(t('label_cookies_uploaded'));
    event.target.reset();
  }

  async function handleSaveAllocation() {
    const accountId = getAllocationAccountId();
    const allocations = { ...state.allocationsDraft };
    const leverages = { ...state.leveragesDraft };
    const url = accountId ? `/api/allocation?account_id=${encodeURIComponent(accountId)}` : '/api/allocation';
    await apiRequest(url, { method: 'POST', body: { allocations, leverages } });
    state.allocationsDirty = false;
    Toast.success(t('label_allocation_saved'));
    await updateProjects();
    await updateAllocationSummary();
  }

  async function refreshData() {
    const safe = async (fn) => {
      try {
        await fn();
      } catch (error) {
        console.error(error);
      }
    };

    await safe(refreshStatus);
    await safe(updateProjects);

    await Promise.all([
      safe(updateLeaderPositions),
      safe(updateFollowerPositions),
      safe(updateEvents),
      safe(updateOnchainEvents),
      safe(updateLogs),
      safe(updateAccounts),
      safe(updateAllocationSummary),
      safe(updateAllocationList)
    ]);
  }

  function setProjectExchange(exchange) {
    const isOkx = exchange === 'okx';
    if (elements.projectPortfolioField) {
      elements.projectPortfolioField.hidden = isOkx;
    }
    if (elements.projectLeaderField) {
      elements.projectLeaderField.hidden = !isOkx;
    }
    if (elements.projectPortfolioId) {
      elements.projectPortfolioId.required = !isOkx;
    }
    if (elements.projectLeaderId) {
      elements.projectLeaderId.required = isOkx;
    }
  }

  function setAccountExchange(exchange) {
    const isOkx = exchange === 'okx';
    if (elements.accountNetworkField) {
      elements.accountNetworkField.hidden = isOkx;
    }
    if (elements.accountPassphraseField) {
      elements.accountPassphraseField.hidden = !isOkx;
    }
    if (elements.accountSimulatedField) {
      elements.accountSimulatedField.hidden = !isOkx;
    }
    const passphraseInput = elements.accountPassphraseField?.querySelector('input');
    if (passphraseInput) {
      passphraseInput.required = isOkx;
    }
  }

  function setupEventHandlers() {
    elements.projectsBody?.addEventListener('click', (event) => {
      const target = event.target?.closest?.('button[data-action]');
      if (!target || target.disabled) return;
      const rawId = target.dataset.projectId || '';
      let projectId = rawId;
      try {
        projectId = decodeURIComponent(rawId);
      } catch (error) {
        projectId = rawId;
      }
      if (!projectId) return;
      if (target.dataset.action === 'toggle-project') {
        const nextEnabled = target.dataset.nextEnabled === 'true';
        window.toggleProject(projectId, nextEnabled);
        return;
      }
      if (target.dataset.action === 'delete-project') {
        window.deleteProject(projectId);
      }
    });

    elements.themeToggle?.addEventListener('click', () => {
      stopAutoTheme();
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      setTheme(isDark ? 'light' : 'dark');
    });

    elements.languageToggle?.addEventListener('click', () => {
      const next = state.language === 'zh' ? 'en' : 'zh';
      setLanguage(next);
      refreshData().catch(() => {});
    });

    elements.connectBtn?.addEventListener('click', async () => {
      try {
        await apiRequest('/api/connect', { method: 'POST' });
        Toast.success(t('status_connected'));
        await refreshStatus();
      } catch (error) {
        Toast.error(error.message);
      }
    });

    elements.refreshNowBtn?.addEventListener('click', () => {
      refreshData();
    });

    elements.jumpConfigBtn?.addEventListener('click', () => {
      const tab = document.querySelector('.tab[data-tab="config"]');
      if (tab) tab.click();
    });

    elements.refreshProjectsBtn?.addEventListener('click', () => {
      updateProjects();
    });

    elements.projectForm?.addEventListener('submit', (event) => {
      handleProjectSubmit(event).catch((error) => Toast.error(error.message));
    });

    elements.accountExchangeSelect?.addEventListener('change', (event) => {
      const target = event.target;
      setAccountExchange(target?.value || 'binance');
    });

    elements.okxFetchInstruments?.addEventListener('click', async () => {
      try {
        const url = buildOkxUrl('/api/okx/copytrading/instruments');
        renderOkxOutput(await apiRequest(url));
      } catch (error) {
        Toast.error(error.message);
      }
    });

    elements.okxSetInstruments?.addEventListener('click', async () => {
      try {
        const instId = elements.okxInstId?.value?.trim() || '';
        const url = buildOkxUrl('/api/okx/copytrading/instruments');
        renderOkxOutput(await apiRequest(url, { method: 'POST', body: { inst_id: instId } }));
      } catch (error) {
        Toast.error(error.message);
      }
    });

    elements.okxFetchPositions?.addEventListener('click', async () => {
      try {
        const instId = elements.okxInstId?.value?.trim() || '';
        const url = buildOkxUrl('/api/okx/copytrading/leading-positions', { inst_id: instId });
        renderOkxOutput(await apiRequest(url));
      } catch (error) {
        Toast.error(error.message);
      }
    });

    elements.okxFetchHistory?.addEventListener('click', async () => {
      try {
        const instId = elements.okxInstId?.value?.trim() || '';
        const limit = elements.okxHistoryLimit?.value || '';
        const url = buildOkxUrl('/api/okx/copytrading/leading-positions/history', {
          inst_id: instId,
          limit
        });
        renderOkxOutput(await apiRequest(url));
      } catch (error) {
        Toast.error(error.message);
      }
    });

    elements.okxPlaceStop?.addEventListener('click', async () => {
      try {
        const payload = {
          sub_pos_id: elements.okxSubPosId?.value?.trim() || '',
          tp_trigger_px: elements.okxTpPx?.value?.trim() || '',
          sl_trigger_px: elements.okxSlPx?.value?.trim() || '',
          tp_trigger_px_type: elements.okxTpType?.value?.trim() || '',
          sl_trigger_px_type: elements.okxSlType?.value?.trim() || ''
        };
        const url = buildOkxUrl('/api/okx/copytrading/leading-positions/stop');
        renderOkxOutput(await apiRequest(url, { method: 'POST', body: payload }));
      } catch (error) {
        Toast.error(error.message);
      }
    });

    elements.okxClosePosition?.addEventListener('click', async () => {
      try {
        const payload = {
          sub_pos_id: elements.okxSubPosId?.value?.trim() || ''
        };
        const url = buildOkxUrl('/api/okx/copytrading/leading-positions/close');
        renderOkxOutput(await apiRequest(url, { method: 'POST', body: payload }));
      } catch (error) {
        Toast.error(error.message);
      }
    });

    elements.okxProfitSharing?.addEventListener('click', async () => {
      try {
        const url = buildOkxUrl('/api/okx/copytrading/profit-sharing');
        renderOkxOutput(await apiRequest(url));
      } catch (error) {
        Toast.error(error.message);
      }
    });

    elements.onchainAddWallet?.addEventListener('click', () => {
      if (!elements.onchainWalletList) return;
      elements.onchainWalletList.appendChild(createOnchainWalletRow({ address: '', enabled: true }));
      applyTranslations();
    });

    elements.onchainSaveConfig?.addEventListener('click', () => {
      saveOnchainConfig().catch((error) => Toast.error(error.message));
    });

    elements.projectExchange?.addEventListener('change', (event) => {
      setProjectExchange(event.target.value);
    });

    elements.accountForm?.addEventListener('submit', (event) => {
      handleAccountSubmit(event).catch((error) => Toast.error(error.message));
    });

    elements.cookieForm?.addEventListener('submit', (event) => {
      handleCookieSubmit(event).catch((error) => Toast.error(error.message));
    });

    elements.cookieTextForm?.addEventListener('submit', (event) => {
      handleCookieTextSubmit(event).catch((error) => Toast.error(error.message));
    });

    elements.saveAllocationBtn?.addEventListener('click', () => {
      handleSaveAllocation().catch((error) => Toast.error(error.message));
    });

    elements.allocationAccountSelect?.addEventListener('change', () => {
      state.allocationAccountId = elements.allocationAccountSelect.value;
      state.allocationsDirty = false;
      state.allocationsDraft = {};
      state.leveragesDraft = {};
      updateAllocationSummary().catch((error) => Toast.error(error.message));
      updateAllocationList().catch((error) => Toast.error(error.message));
    });

    elements.accountSelect?.addEventListener('change', () => {
      updateFollowerPositions().catch((error) => Toast.error(error.message));
    });

    elements.historyPrev?.addEventListener('click', () => {
      if (state.historyPage > 1) {
        state.historyPage -= 1;
        renderHistory();
      }
    });

    elements.historyNext?.addEventListener('click', () => {
      const totalPages = Math.max(1, Math.ceil(state.allEvents.length / 20));
      if (state.historyPage < totalPages) {
        state.historyPage += 1;
        renderHistory();
      }
    });

    elements.logsPrev?.addEventListener('click', () => {
      if (state.logsPage > 1) {
        state.logsPage -= 1;
        renderLogs();
      }
    });

    elements.logsNext?.addEventListener('click', () => {
      const totalPages = Math.max(1, Math.ceil(state.allLogs.length / 20));
      if (state.logsPage < totalPages) {
        state.logsPage += 1;
        renderLogs();
      }
    });
  }

  window.toggleProject = async (portfolioId, enabled) => {
    try {
      const safeId = encodeURIComponent(portfolioId || '');
      await apiRequest(`/api/projects/${safeId}/enable`, {
        method: 'POST',
        body: { enabled }
      });
      Toast.success(enabled ? t('label_project_resumed') : t('label_project_paused'));
      await updateProjects();
    } catch (error) {
      Toast.error(error.message);
    }
  };

  window.deleteProject = async (portfolioId) => {
    const confirmDelete = window.confirm(t('confirm_remove_project'));
    if (!confirmDelete) return;
    try {
      const safeId = encodeURIComponent(portfolioId || '');
      await apiRequest(`/api/projects/${safeId}`, { method: 'DELETE' });
      Toast.success(t('label_project_removed'));
      await updateProjects();
    } catch (error) {
      Toast.error(error.message);
    }
  };

  function init() {
    initLanguage();
    initTheme();
    setupTabs();
    setupEventHandlers();
    if (elements.projectExchange) {
      setProjectExchange(elements.projectExchange.value || 'binance');
    }
    if (elements.accountExchangeSelect) {
      setAccountExchange(elements.accountExchangeSelect.value || 'binance');
    }
    loadOnchainConfig().catch(() => {});
    refreshData().catch((error) => Toast.error(error.message));

    setInterval(() => {
      if (!document.hidden) {
        refreshData().catch(() => {});
      }
    }, 5000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
