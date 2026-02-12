// Toast Notification System
class Toast {
    static container;

    static init() {
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        document.body.appendChild(this.container);
    }

    static show(message, type = 'info', duration = 3000) {
        if (!this.container) this.init();

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        // Icon based on type
        let icon = '';
        switch(type) {
            case 'success': icon = '✅'; break;
            case 'error': icon = '❌'; break;
            case 'warning': icon = '⚠️'; break;
            default: icon = 'ℹ️';
        }

        toast.innerHTML = `
            <span class="toast-icon">${icon}</span>
            <span class="toast-message">${message}</span>
        `;

        this.container.appendChild(toast);

        // Remove after duration
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    static success(msg) { this.show(msg, 'success'); }
    static error(msg) { this.show(msg, 'error', 5000); }
    static info(msg) { this.show(msg, 'info'); }
}

// State Management
const state = {
    historyPage: 1,
    logsPage: 1,
    allEvents: [],
    allLogs: [],
    isConnected: false,
    refreshInterval: null
};

// DOM Elements
const elements = {
    connectionStatus: document.getElementById('connectionStatus'),
    serviceStatus: document.getElementById('serviceStatus'),
    projectCount: document.getElementById('projectCount'),
    positionCount: document.getElementById('positionCount'),
    actionCount: document.getElementById('actionCount'),
    projectsBody: document.getElementById('projectsBody'),
    leaderPositionsBody: document.getElementById('leaderPositionsBody2'),
    followerPositionsBody: document.getElementById('followerPositionsBody2'),
    accountSelect: document.getElementById('accountSelect2'),
    historyBody: document.getElementById('historyBody'),
    logsBody: document.getElementById('logsBody'),
    refreshBtn: document.getElementById('refreshProjectsBtn'),
    // Forms
    projectForm: document.getElementById('projectForm'),
    accountForm: document.getElementById('accountForm'),
    allocationForm: document.getElementById('allocationForm'),
    cookieForm: document.getElementById('cookieForm'),
    allocationSlider: document.getElementById('allocationSlider'),
    allocationValue: document.getElementById('allocationValue'),
    // Pagination
    historyPrev: document.getElementById('historyPrevBtn'),
    historyNext: document.getElementById('historyNextBtn'),
    historyInfo: document.getElementById('historyPageInfo'),
    logsPrev: document.getElementById('logsPrevBtn'),
    logsNext: document.getElementById('logsNextBtn'),
    logsInfo: document.getElementById('logsPageInfo'),
};

// API Helper
async function api(endpoint, method = 'GET', data = null) {
    try {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (data && !(data instanceof FormData)) {
            options.body = JSON.stringify(data);
        } else if (data instanceof FormData) {
            delete options.headers['Content-Type']; // Let browser set boundary
            options.body = data;
        }

        const response = await fetch(`/api/${endpoint}`, options);
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        if (method !== 'GET') { // Don't toast on background polling failures unless critical
            Toast.error(error.message);
        }
        return null;
    }
}

// Initialization
function init() {
    Toast.init();
    setupEventListeners();
    setupTabs();
    
    // Initial Load
    loadAccounts();
    loadAllocation();
    refreshData();
    
    // Polling
    state.refreshInterval = setInterval(refreshData, 5000);
}

function setupEventListeners() {
    // Refresh Button
    elements.refreshBtn?.addEventListener('click', () => {
        refreshData();
        Toast.info('刷新数据...');
    });

    // Forms
    elements.projectForm?.addEventListener('submit', handleProjectSubmit);
    elements.accountForm?.addEventListener('submit', handleAccountSubmit);
    elements.allocationForm?.addEventListener('submit', handleAllocationSubmit);
    elements.cookieForm?.addEventListener('submit', handleCookieSubmit);

    // Inputs
    elements.allocationSlider?.addEventListener('input', (e) => {
        elements.allocationValue.textContent = `${e.target.value}%`;
    });

    elements.accountSelect?.addEventListener('change', updateFollowerPositions);

    // Pagination
    elements.historyPrev?.addEventListener('click', () => {
        if (state.historyPage > 1) {
            state.historyPage--;
            renderHistory();
        }
    });
    elements.historyNext?.addEventListener('click', () => {
        const totalPages = Math.ceil(state.allEvents.length / 20);
        if (state.historyPage < totalPages) {
            state.historyPage++;
            renderHistory();
        }
    });

    elements.logsPrev?.addEventListener('click', () => {
        if (state.logsPage > 1) {
            state.logsPage--;
            renderLogs();
        }
    });
    elements.logsNext?.addEventListener('click', () => {
        const totalPages = Math.ceil(state.allLogs.length / 20);
        if (state.logsPage < totalPages) {
            state.logsPage++;
            renderLogs();
        }
    });
}

function setupTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            btn.classList.add('active');
            const targetId = btn.dataset.tab;
            document.getElementById(targetId).classList.add('active');
        });
    });
}

// Core Data Functions
async function refreshData() {
    await Promise.all([
        updateStatus(),
        updateProjects(),
        updateLeaderPositions(),
        updateFollowerPositions(),
        updateActionCards(),
        updateLogs()
    ]);
    // History is rendered via updateActionCards -> renderHistory
}

async function updateStatus() {
    const data = await api('status');
    if (data) {
        state.isConnected = data.connected;
        elements.connectionStatus.classList.toggle('connected', data.connected);
        elements.connectionStatus.querySelector('.status-text').textContent = 
            data.connected ? '已连接' : '未连接';
        
        elements.serviceStatus.textContent = data.running ? '运行中' : '已停止';
        elements.serviceStatus.className = `metric-value ${data.running ? 'text-success' : 'text-secondary'}`;
    }
}

async function updateProjects() {
    const data = await api('projects');
    if (data && Array.isArray(data)) {
        const enabledCount = data.filter(p => p.enabled).length;
        elements.projectCount.textContent = enabledCount;

        if (data.length === 0) {
            elements.projectsBody.innerHTML = '<tr class="empty"><td colspan="4">暂无项目</td></tr>';
        } else {
            elements.projectsBody.innerHTML = data.map(p => `
                <tr>
                    <td><span class="status-tag bg-info">${p.portfolio_id}</span></td>
                    <td>${p.trade_account_id || '—'}</td>
                    <td><span class="status-tag ${p.enabled ? 'bg-success' : 'bg-secondary'}">${p.enabled ? '运行中' : '已停止'}</span></td>
                    <td>
                        <button class="btn-sm btn-toggle" onclick="toggleProject('${p.portfolio_id}', ${!p.enabled})">
                            ${p.enabled ? '停止' : '启动'}
                        </button>
                    </td>
                </tr>
            `).join('');
        }
    }
}

async function updateLeaderPositions() {
    const data = await api('leader-positions');
    if (data && Array.isArray(data)) {
        renderPositionsTable(elements.leaderPositionsBody, data);
    }
}

async function updateFollowerPositions() {
    const accountId = elements.accountSelect.value;
    const data = await api(`follower-positions${accountId ? '?account_id=' + accountId : ''}`);
    if (data && Array.isArray(data)) {
        elements.positionCount.textContent = data.length;
        renderPositionsTable(elements.followerPositionsBody, data);
    }
}

function renderPositionsTable(tbody, data) {
    if (data.length === 0) {
        tbody.innerHTML = '<tr class="empty"><td colspan="7">暂无持仓</td></tr>';
        return;
    }

    tbody.innerHTML = data.map(p => {
        const pnl = parseFloat(p.unrealizedProfit || 0);
        const pnlClass = pnl >= 0 ? 'text-success' : 'text-danger';
        const sideClass = p.positionSide === 'LONG' ? 'text-success' : 'text-danger';
        const pnlBg = pnl >= 0 ? 'bg-success' : 'bg-danger';

        return `
            <tr>
                <td>${p.symbol || '—'}</td>
                <td class="${sideClass}">${p.positionSide || '—'}</td>
                <td>${parseFloat(p.positionAmt || 0).toFixed(4)}</td>
                <td>${p.leverage || '—'}</td>
                <td>${parseFloat(p.entryPrice || 0).toFixed(2)}</td>
                <td>${parseFloat(p.markPrice || 0).toFixed(2)}</td>
                <td><span class="status-tag ${pnlBg}">${pnl.toFixed(2)}</span></td>
            </tr>
        `;
    }).join('');
}

async function updateActionCards() {
    const data = await api('events?limit=200');
    if (data && Array.isArray(data)) {
        state.allEvents = data;
        elements.actionCount.textContent = data.length;

        const counts = {
            open: data.filter(e => e.action === 'open').length,
            add: data.filter(e => e.action === 'add').length,
            reduce: data.filter(e => e.action === 'reduce').length,
            close: data.filter(e => e.action === 'close').length
        };

        document.getElementById('openCount').textContent = counts.open;
        document.getElementById('addCount').textContent = counts.add;
        document.getElementById('reduceCount').textContent = counts.reduce;
        document.getElementById('closeCount').textContent = counts.close;

        renderHistory();
    }
}

function renderHistory() {
    const pageSize = 20;
    const start = (state.historyPage - 1) * pageSize;
    const end = start + pageSize;
    const pageData = state.allEvents.slice(start, end);
    const totalPages = Math.ceil(state.allEvents.length / pageSize) || 1;

    if (pageData.length === 0) {
        elements.historyBody.innerHTML = '<tr class="empty"><td colspan="6">暂无记录</td></tr>';
    } else {
        elements.historyBody.innerHTML = pageData.map(e => {
            const time = e.created_at ? new Date(e.created_at).toLocaleString('zh-CN') : '—';
            let actionClass = 'bg-info';
            if (e.action === 'close') actionClass = 'bg-danger';
            if (e.action === 'open') actionClass = 'bg-success';

            return `
                <tr>
                    <td>${time}</td>
                    <td><span class="status-tag ${actionClass}">${e.action || '—'}</span></td>
                    <td>${e.symbol || '—'}</td>
                    <td class="${e.side === 'BUY' ? 'text-success' : 'text-danger'}">${e.side || '—'}</td>
                    <td>${parseFloat(e.executed_qty || 0).toFixed(4)}</td>
                    <td>${parseFloat(e.avg_price || 0).toFixed(2)}</td>
                </tr>
            `;
        }).join('');
    }

    elements.historyInfo.textContent = `第 ${state.historyPage} / ${totalPages} 页`;
    elements.historyPrev.disabled = state.historyPage === 1;
    elements.historyNext.disabled = state.historyPage >= totalPages;
}

async function updateLogs() {
    const data = await api('logs?limit=200');
    if (data && Array.isArray(data)) {
        state.allLogs = data;
        renderLogs();
    }
}

function renderLogs() {
    const pageSize = 20;
    const start = (state.logsPage - 1) * pageSize;
    const end = start + pageSize;
    const pageData = state.allLogs.slice(start, end);
    const totalPages = Math.ceil(state.allLogs.length / pageSize) || 1;

    if (pageData.length === 0) {
        elements.logsBody.innerHTML = '<tr class="empty"><td colspan="3">暂无日志</td></tr>';
    } else {
        elements.logsBody.innerHTML = pageData.map(log => {
            const time = log.timestamp ? new Date(log.timestamp).toLocaleString('zh-CN') : '—';
            let levelClass = 'bg-info';
            if (log.level === 'error') levelClass = 'bg-danger';
            if (log.level === 'warning') levelClass = 'bg-warning';

            return `
                <tr>
                    <td>${time}</td>
                    <td><span class="status-tag ${levelClass}">${(log.level || 'INFO').toUpperCase()}</span></td>
                    <td>${log.message || '—'}</td>
                </tr>
            `;
        }).join('');
    }

    elements.logsInfo.textContent = `第 ${state.logsPage} / ${totalPages} 页`;
    elements.logsPrev.disabled = state.logsPage === 1;
    elements.logsNext.disabled = state.logsPage >= totalPages;
}

// Form Handlers
async function handleProjectSubmit(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData);
    
    // Convert types if necessary
    data.scale_value = parseFloat(data.scale_value);
    data.follower_leverage = parseInt(data.follower_leverage);
    data.enabled = true; // Default to enabled when creating

    const result = await api('projects', 'POST', data);
    if (result) {
        Toast.success('项目创建成功');
        e.target.reset();
        await updateProjects();
    }
}

async function handleAccountSubmit(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const newAccount = {
        account_id: formData.get('account_name'), // Using name as ID for simplicity
        account_name: formData.get('account_name'),
        api_key: formData.get('api_key'),
        api_secret: formData.get('api_secret'),
        network: formData.get('network')
    };

    // We need to fetch current config, append, and save
    const config = await api('trade-config');
    if (!config) return;

    config.accounts = config.accounts || [];
    // Check for duplicate
    if (config.accounts.find(a => a.account_id === newAccount.account_id)) {
        Toast.error('账户ID已存在');
        return;
    }
    
    config.accounts.push(newAccount);

    const result = await api('trade-config', 'POST', config);
    if (result) {
        Toast.success('账户添加成功');
        e.target.reset();
        await loadAccounts();
    }
}

async function handleAllocationSubmit(e) {
    e.preventDefault();
    const percent = parseFloat(elements.allocationSlider.value);
    
    // Get projects to update allocation
    // This logic seems a bit simplistic (assigning same allocation to all?), 
    // but sticking to "old frontend logic" where it seemed to update the first project?
    // Let's improve: Update ALL active projects evenly or just the first one?
    // The old code: `allocations[projects[0].portfolio_id] = percent;`
    // I'll stick to that but safer.
    
    const projects = await api('projects');
    if (!projects || projects.length === 0) {
        Toast.error('没有可用的项目');
        return;
    }

    const allocations = {};
    // Reset all to 0 first? Or keep existing?
    // Old code kept existing and updated first.
    projects.forEach(p => allocations[p.portfolio_id] = p.allocated_equity_pct || 0);
    
    // Update first project
    if (projects.length > 0) {
        allocations[projects[0].portfolio_id] = percent;
    }

    const result = await api('allocation', 'POST', allocations);
    if (result) {
        Toast.success('资金分配已更新');
        await loadAllocation();
    }
}

async function handleCookieSubmit(e) {
    e.preventDefault();
    const formData = new FormData(e.target);
    const result = await api('cookies', 'POST', formData);
    if (result) {
        Toast.success('Cookie 上传成功');
        e.target.reset();
    }
}

// Helpers
async function loadAccounts() {
    const config = await api('trade-config');
    if (config && config.accounts) {
        const options = '<option value="">所有账户</option>' + 
            config.accounts.map(acc => `<option value="${acc.account_id}">${acc.account_name}</option>`).join('');
        
        if (elements.accountSelect) elements.accountSelect.innerHTML = options;
        
        const projectAccountSelect = elements.projectForm?.querySelector('select[name="trade_account_id"]');
        if (projectAccountSelect) {
            projectAccountSelect.innerHTML = '<option value="">选择账户</option>' + 
                config.accounts.map(acc => `<option value="${acc.account_id}">${acc.account_name}</option>`).join('');
        }

        const accountsBody = document.getElementById('accountsBody');
        if (accountsBody) {
            if (config.accounts.length === 0) {
                accountsBody.innerHTML = '<tr class="empty"><td colspan="3">暂无账户</td></tr>';
            } else {
                accountsBody.innerHTML = config.accounts.map(acc => `
                    <tr>
                        <td>${acc.account_name || '—'}</td>
                        <td>${acc.api_key ? acc.api_key.substring(0, 8) + '***' : '—'}</td>
                        <td><span class="status-tag ${acc.network === 'mainnet' ? 'bg-success' : 'bg-warning'}">${acc.network}</span></td>
                    </tr>
                `).join('');
            }
        }
    }
}

async function loadAllocation() {
    const summary = await api('account-summary');
    if (summary) {
        document.getElementById('totalEquity').textContent = `$${(summary.total_equity || 0).toFixed(2)}`;
        document.getElementById('allocatedPercent').textContent = `${(summary.total_allocated_pct || 0).toFixed(1)}%`;
    }
    
    const allocation = await api('allocation');
    if (allocation && allocation.total !== undefined) {
        elements.allocationSlider.value = allocation.total;
        elements.allocationValue.textContent = `${allocation.total}%`;
    }
}

// Global functions for HTML event attributes
window.toggleProject = async (portfolioId, enabled) => {
    try {
        await api(`projects/${portfolioId}/enable`, 'POST', { enabled });
        Toast.success(`项目已${enabled ? '启动' : '停止'}`);
        await updateProjects();
    } catch (error) {
        // Error handled by api helper
    }
};

// Start
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}