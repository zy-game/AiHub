// Theme Toggle
function toggleTheme() {
    const body = document.body;
    const isDark = body.classList.toggle('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    document.querySelector('.theme-toggle').textContent = isDark ? '☀️' : '🌙';
}

// Load saved theme
(function() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark');
        document.querySelector('.theme-toggle').textContent = '☀️';
    }
})();

// API wrapper - now uses session authentication (cookies)
const API = {
    async request(method, url, data = null, contentType = 'application/json') {
        const options = { 
            method, 
            headers: {},
            credentials: 'include'  // Include cookies in requests
        };
        
        if (data) {
            options.body = contentType === 'text/plain' ? data : JSON.stringify(data);
            options.headers['Content-Type'] = contentType;
        }
        
        const resp = await fetch(url, options);
        
        // If 401, redirect to login
        if (resp.status === 401) {
            window.location.href = '/login';
            return;
        }
        
        return resp.json();
    },
    get: (url) => API.request('GET', url),
    post: (url, data, ct) => API.request('POST', url, data, ct),
    put: (url, data) => API.request('PUT', url, data),
    delete: (url) => API.request('DELETE', url)
};

let currentChannelId = null;
let currentChannelName = '';
let currentChannelType = 'openai';

// Formatters
function formatTokens(n) {
    if (!n) return '-';
    if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n/1e3).toFixed(1) + 'K';
    return n.toLocaleString();
}

function formatDate(d) {
    if (!d) return '-';
    return new Date(d).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
}

function getProgressBar(used, limit, label = '用量') {
    if (!limit) return '';
    const pct = Math.min(100, Math.round((used / limit) * 100));
    const cls = pct >= 90 ? 'danger' : pct >= 70 ? 'warning' : 'success';
    return `<div class="progress-container">
        <div class="progress-header"><span class="progress-label">${label}</span><span class="progress-value">${used.toLocaleString()} / ${limit.toLocaleString()} (${pct}%)</span></div>
        <div class="progress-bar"><div class="progress-fill ${cls}" style="width:${pct}%"></div></div>
    </div>`;
}

function getBadge(type, text) {
    const map = { success:'badge-success', danger:'badge-danger', warning:'badge-warning', info:'badge-info', gray:'badge-gray' };
    return `<span class="badge ${map[type] || 'badge-gray'}">${text}</span>`;
}

function getTypeBadge(t) {
    const m = { kiro:'info', openai:'success', anthropic:'warning', google:'info' };
    const names = { kiro:'Kiro', openai:'OpenAI', anthropic:'Anthropic', google:'Google' };
    return getBadge(m[t] || 'gray', names[t] || t);
}

// Navigation
document.querySelectorAll('.nav-menu a').forEach(link => {
    link.addEventListener('click', e => { e.preventDefault(); const p = link.dataset.page; showPage(p); loadPageData(p); });
});

function showPage(page) {
    document.querySelectorAll('.nav-menu a').forEach(l => l.classList.remove('active'));
    document.querySelector(`.nav-menu a[data-page="${page}"]`)?.classList.add('active');
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${page}`).classList.add('active');
}

function loadPageData(page) {
    const loaders = { 
        dashboard: loadDashboard, 
        channels: loadChannels, 
        accounts: loadAccountsAll, 
        users: loadUsers, 
        tokens: loadTokens, 
        logs: loadLogs,
        profile: loadProfile
    };
    loaders[page]?.();
}

// Dashboard
let requestsChart = null;
let tokensChart = null;

async function loadDashboard() {
    const data = await API.get('/api/stats?days=7');
    const o = data.overview || {};
    document.getElementById('stat-requests').textContent = o.total_requests || 0;
    document.getElementById('stat-tokens').textContent = formatTokens((o.total_input_tokens||0) + (o.total_output_tokens||0));
    document.getElementById('stat-duration').textContent = o.avg_duration ? `${Math.round(o.avg_duration)}ms` : '-';
    document.getElementById('stat-errors').textContent = o.total_requests ? `${((o.error_count||0)/o.total_requests*100).toFixed(1)}%` : '0%';
    
    // Channel stats - only load if section is visible (super_admin only)
    const channelTbody = document.querySelector('#channel-stats tbody');
    if (channelTbody && data.channels && data.channels.length > 0) {
        channelTbody.innerHTML = data.channels.map(c => `
            <tr>
                <td><strong>${c.name}</strong></td>
                <td>${getTypeBadge(c.type)}</td>
                <td>${c.total_accounts || 0}</td>
                <td>${c.active_accounts || 0}</td>
                <td>${formatTokens(c.total_tokens)}</td>
                <td>${c.enabled ? getBadge('success','启用') : getBadge('danger','禁用')}</td>
            </tr>
        `).join('');
    }
    
    // Top users - only load if section is visible (super_admin only)
    const usersTbody = document.querySelector('#top-users tbody');
    if (usersTbody && data.top_users && data.top_users.length > 0) {
        usersTbody.innerHTML = data.top_users.map(u => `
            <tr>
                <td>${u.name || '用户 #' + u.id}</td>
                <td>${formatTokens(u.input_tokens)}</td>
                <td>${formatTokens(u.output_tokens)}</td>
                <td><strong>${formatTokens(u.total_tokens)}</strong></td>
            </tr>
        `).join('');
    }
    
    // Model stats (show for all users)
    const modelTbody = document.querySelector('#model-stats tbody');
    if (modelTbody) {
        modelTbody.innerHTML = (data.models||[]).map(m => 
            `<tr><td>${m.model}</td><td>${m.count}</td><td>${formatTokens(m.total_tokens)}</td></tr>`
        ).join('');
    }
    
    // Render charts
    renderRequestsChart(data.hourly || []);
    renderTokensChart(data.hourly || []);
}

function renderRequestsChart(hourlyData) {
    const ctx = document.getElementById('requests-chart');
    if (!ctx) return;
    if (requestsChart) requestsChart.destroy();
    
    const labels = hourlyData.map(h => {
        const date = new Date(h.hour);
        return date.toLocaleDateString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit'}) + '时';
    });
    const requests = hourlyData.map(h => h.requests || 0);
    
    requestsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '请求数',
                data: requests,
                borderColor: 'rgb(99, 102, 241)',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true } }
        }
    });
}

function renderTokensChart(hourlyData) {
    const ctx = document.getElementById('tokens-chart');
    if (!ctx) return;
    if (tokensChart) tokensChart.destroy();
    
    const labels = hourlyData.map(h => {
        const date = new Date(h.hour);
        return date.toLocaleDateString('zh-CN', {month:'2-digit', day:'2-digit', hour:'2-digit'}) + '时';
    });
    const inputTokens = hourlyData.map(h => h.input_tokens || 0);
    const outputTokens = hourlyData.map(h => h.output_tokens || 0);
    
    tokensChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                { label: '输入Token', data: inputTokens, backgroundColor: 'rgba(16, 185, 129, 0.7)', stack: 'tokens' },
                { label: '输出Token', data: outputTokens, backgroundColor: 'rgba(99, 102, 241, 0.7)', stack: 'tokens' }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top' } },
            scales: { y: { beginAtZero: true, stacked: true }, x: { stacked: true } }
        }
    });
}

// Channels (Card)
async function loadChannels() {
    const channels = await API.get('/api/providers');
    document.getElementById('channels-grid').innerHTML = channels.map(c => {
        const successRate = c.total_requests > 0 ? ((1 - (c.failed_requests || 0) / c.total_requests) * 100).toFixed(1) : '100.0';
        
        // Health status indicator
        let healthBadge = '';
        if (c.enabled && c.account_count > 0) {
            if (c.total_requests > 0) {
                const rate = parseFloat(successRate);
                if (rate >= 95) {
                    healthBadge = '<span class="health-indicator health-good" title="健康 (成功率: ' + successRate + '%)">●</span>';
                } else if (rate >= 80) {
                    healthBadge = '<span class="health-indicator health-warning" title="一般 (成功率: ' + successRate + '%)">●</span>';
                } else {
                    healthBadge = '<span class="health-indicator health-bad" title="异常 (成功率: ' + successRate + '%)">●</span>';
                }
            } else {
                // No requests yet, show as healthy if enabled and has accounts
                healthBadge = '<span class="health-indicator health-good" title="就绪 (未有请求)">●</span>';
            }
        } else if (!c.enabled) {
            healthBadge = '<span class="health-indicator health-unknown" title="已禁用">●</span>';
        } else {
            healthBadge = '<span class="health-indicator health-unknown" title="无账号">●</span>';
        }
        
        return `
        <div class="item-card" id="channel-card-${c.id}">
            <div class="item-card-header">
                <div>
                    <div class="item-card-title">${healthBadge} ${c.name}</div>
                    <div class="item-card-subtitle">ID: ${c.id} | 优先级: ${c.priority} | 权重: ${c.weight}</div>
                </div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    ${getTypeBadge(c.type)}
                    ${c.enabled ? getBadge('success','启用') : getBadge('danger','禁用')}
                </div>
            </div>
            <div class="item-card-body">
                <div class="item-card-row">
                    <span class="item-card-label">账号</span>
                    <span class="item-card-value">${c.enabled_account_count} / ${c.account_count}</span>
                </div>
                <div class="item-card-row">
                    <span class="item-card-label">Token数</span>
                    <span class="item-card-value">${formatTokens(c.total_tokens)}</span>
                </div>
                ${c.total_requests > 0 ? `
                <div class="item-card-row">
                    <span class="item-card-label">请求数</span>
                    <span class="item-card-value">${c.total_requests} (成功率: ${successRate}%)</span>
                </div>
                <div class="item-card-row">
                    <span class="item-card-label">平均响应</span>
                    <span class="item-card-value">${c.avg_response_time}ms</span>
                </div>` : ''}
                ${c.type === 'kiro' && c.limit ? getProgressBar(c.usage||0, c.limit) : ''}
            </div>
            <div class="item-card-footer">
                ${c.supports_usage_refresh?`<button class="btn btn-xs" onclick="refreshChannelUsage(${c.id})">刷新</button>`:''}
                <button class="btn btn-xs" id="health-check-btn-${c.id}" onclick="healthCheckChannel(${c.id})">健康检查</button>
                ${window.userRole === 'super_admin' ? `<button class="btn btn-xs" onclick="editChannel(${c.id})">编辑</button>` : ''}
                ${window.userRole === 'super_admin' ? `<button class="btn btn-xs btn-danger" onclick="deleteChannel(${c.id})">删除</button>` : ''}
            </div>
        </div>
    `;
    }).join('');
}

async function healthCheckChannel(id) {
    const btn = document.getElementById(`health-check-btn-${id}`);
    if (!btn) return;
    
    // Disable button and show loading state
    btn.disabled = true;
    btn.textContent = '检查中...';
    
    try {
        const result = await API.post(`/api/channels/${id}/health-check`);
        
        const healthy = result.healthy_accounts || 0;
        const total = result.total_accounts || 0;
        
        // Update button text with result
        if (healthy === total && total > 0) {
            btn.textContent = `✅ ${healthy}/${total}`;
            btn.classList.add('btn-success');
        } else if (healthy > 0) {
            btn.textContent = `⚠️ ${healthy}/${total}`;
            btn.classList.add('btn-warning');
        } else {
            btn.textContent = `❌ ${healthy}/${total}`;
            btn.classList.add('btn-danger');
        }
        
        // Re-enable button after 3 seconds
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = '健康检查';
            btn.classList.remove('btn-success', 'btn-warning', 'btn-danger');
        }, 3000);
        
        // Reload channels to update statistics
        setTimeout(() => {
            loadChannels();
        }, 3500);
        
    } catch (err) {
        btn.textContent = '检查失败';
        btn.classList.add('btn-danger');
        
        // Re-enable button after 2 seconds
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = '健康检查';
            btn.classList.remove('btn-danger');
        }, 2000);
    }
}

async function refreshChannelUsage(id) {
    if (!confirm('确认刷新此渠道的所有账号用量？')) return;
    const r = await API.post(`/api/channels/${id}/refresh-usage`);
    alert(`刷新完成：成功 ${r.success} 个，失败 ${r.failed} 个`);
    loadChannels();
}

async function refreshAllUsage() {
    if (!confirm('确认刷新所有 Kiro 渠道的用量？这可能需要一些时间。')) return;
    const r = await API.post('/api/refresh-all-usage');
    alert(`刷新完成：成功 ${r.total_success} 个，失败 ${r.total_failed} 个`);
    loadChannels();
}

function showChannelModal(c = null) {
    document.getElementById('channel-modal-title').textContent = c ? '编辑渠道' : '添加渠道';
    document.getElementById('channel-id').value = c?.id || '';
    document.getElementById('channel-name').value = c?.name || '';
    document.getElementById('channel-type').value = c?.type || 'openai';
    document.getElementById('channel-priority').value = c?.priority || 0;
    document.getElementById('channel-weight').value = c?.weight || 1;
    document.getElementById('channel-modal').classList.add('active');
}

async function editChannel(id) {
    const channels = await API.get('/api/providers');
    const c = channels.find(x => x.id === id);
    if (c) {
        // Navigate to edit page
        document.getElementById('channel-edit-title').textContent = `编辑渠道 - ${c.name}`;
        document.getElementById('edit-channel-id').value = c.id;
        document.getElementById('edit-channel-name').value = c.name;
        document.getElementById('edit-channel-type').value = c.type;
        document.getElementById('edit-channel-priority').value = c.priority || 0;
        document.getElementById('edit-channel-weight').value = c.weight || 1;
        document.getElementById('edit-channel-enabled').checked = c.enabled;
        
        // Load supported models
        loadChannelSupportedModels(c.id);
        
        showPage('channel-edit');
    }
}

async function loadChannelSupportedModels(channelId) {
    const container = document.getElementById('edit-channel-supported-models');
    try {
        const data = await API.get(`/api/channels/${channelId}/models`);
        if (data.supported_models && data.supported_models.length > 0) {
            container.innerHTML = `<div class="model-tags">${data.supported_models.map(m => `<span class="model-tag">${m}</span>`).join('')}</div>`;
        } else {
            container.innerHTML = '<small class="help-text">无可用模型</small>';
        }
    } catch (err) {
        container.innerHTML = '<small class="help-text text-error">加载失败</small>';
    }
}

async function saveChannelEdit() {
    const id = document.getElementById('edit-channel-id').value;
    
    const data = {
        name: document.getElementById('edit-channel-name').value,
        priority: parseInt(document.getElementById('edit-channel-priority').value) || 0,
        weight: parseInt(document.getElementById('edit-channel-weight').value) || 1,
        enabled: document.getElementById('edit-channel-enabled').checked ? 1 : 0
    };
    
    try {
        await API.put(`/api/channels/${id}`, data);
        alert('保存成功');
        showChannelsPage();
        loadChannels();
    } catch (err) {
        alert('保存失败：' + err.message);
    }
}

async function deleteChannel(id) {
    if (confirm('确认删除此渠道及其所有账号？')) { await API.delete(`/api/channels/${id}`); loadChannels(); }
}

document.getElementById('channel-form').addEventListener('submit', async e => {
    e.preventDefault();
    const id = document.getElementById('channel-id').value;
    
    const data = {
        name: document.getElementById('channel-name').value,
        type: document.getElementById('channel-type').value,
        priority: parseInt(document.getElementById('channel-priority').value) || 0,
        weight: parseInt(document.getElementById('channel-weight').value) || 1
    };
    id ? await API.put(`/api/channels/${id}`, data) : await API.post('/api/providers', data);
    closeModal('channel-modal');
    loadChannels();
});

// Channel Accounts (Card)
async function showChannelAccountsPage(id, name) {
    currentChannelId = id;
    currentChannelName = name;
    const channels = await API.get('/api/providers');
    const channel = channels.find(c => c.id === id);
    currentChannelType = channel?.type || 'openai';
    const supportsRefresh = channel?.supports_usage_refresh || false;
    
    document.getElementById('accounts-channel-name').textContent = name;
    document.getElementById('btn-refresh-channel').style.display = supportsRefresh ? '' : 'none';
    showPage('channel-accounts');
    loadAccounts();
}

function showChannelsPage() { showPage('channels'); loadChannels(); }

async function loadAccounts() {
    const accounts = await API.get(`/api/channels/${currentChannelId}/accounts`);
    document.getElementById('accounts-grid').innerHTML = accounts.map(a => `
        <div class="item-card">
            <div class="item-card-header">
                <div>
                    <div class="item-card-title">${a.name || '账号 #' + a.id}</div>
                    <div class="item-card-subtitle">ID: ${a.id}</div>
                </div>
                ${a.enabled ? getBadge('success','启用') : getBadge('danger','禁用')}
            </div>
            <div class="item-card-body">
                <div class="item-card-row">
                    <span class="item-card-label">API Key</span>
                    <span class="item-card-value"><span class="api-key">${a.api_key}</span></span>
                </div>
                <div class="item-card-row">
                    <span class="item-card-label">最后使用</span>
                    <span class="item-card-value">${formatDate(a.last_used_at)}</span>
                </div>
                ${currentChannelType === 'kiro' && a.limit ? getProgressBar(a.usage||0, a.limit) : ''}
            </div>
            <div class="item-card-footer">
                ${currentChannelType==='kiro'?`<button class="btn btn-xs" onclick="refreshAccountUsage(${a.id})">刷新</button>`:''}
                ${window.userRole === 'super_admin' ? `<button class="btn btn-xs" onclick="editAccount(${a.id})">编辑</button>` : ''}
                ${window.userRole === 'super_admin' ? `<button class="btn btn-xs" onclick="toggleAccount(${a.id},${a.enabled})">${a.enabled?'禁用':'启用'}</button>` : ''}
                ${window.userRole === 'super_admin' ? `<button class="btn btn-xs btn-danger" onclick="deleteAccount(${a.id})">删除</button>` : ''}
            </div>
        </div>
    `).join('');
}

async function editAccount(id) {
    const accounts = await API.get(`/api/channels/${currentChannelId}/accounts`);
    const account = accounts.find(a => a.id === id);
    if (!account) return;
    
    document.getElementById('account-edit-title').textContent = `编辑账号 - ${account.name || '账号 #' + account.id}`;
    document.getElementById('edit-account-id').value = account.id;
    document.getElementById('edit-account-channel-id').value = currentChannelId;
    document.getElementById('edit-account-name').value = account.name || '';
    document.getElementById('edit-account-api-key').value = account.api_key;
    document.getElementById('edit-account-enabled').checked = account.enabled;
    
    showPage('account-edit');
}

async function saveAccountEdit() {
    const id = document.getElementById('edit-account-id').value;
    
    const data = {
        name: document.getElementById('edit-account-name').value,
        api_key: document.getElementById('edit-account-api-key').value,
        enabled: document.getElementById('edit-account-enabled').checked ? 1 : 0
    };
    
    try {
        await API.put(`/api/accounts/${id}`, data);
        alert('保存成功');
        backToAccountsList();
        loadAccounts();
    } catch (err) {
        alert('保存失败：' + err.message);
    }
}

function backToAccountsList() {
    if (currentChannelId) {
        showPage('channel-accounts');
    } else {
        showPage('accounts-all');
    }
}

async function refreshAccountUsage(id) {
    const r = await API.post(`/api/accounts/${id}/refresh-usage`);
    r.success ? alert(`用量：${r.usage}/${r.limit}`) : alert('刷新失败：' + r.error);
    loadAccounts();
}

async function refreshCurrentChannelUsage() {
    if (!confirm('确认刷新此渠道的所有账号用量？')) return;
    const r = await API.post(`/api/channels/${currentChannelId}/refresh-usage`);
    alert(`刷新完成：成功 ${r.success} 个，失败 ${r.failed} 个`);
    loadAccounts();
}

async function toggleAccount(id, enabled) { await API.put(`/api/accounts/${id}`, { enabled: enabled ? 0 : 1 }); loadAccounts(); }
async function deleteAccount(id) { if (confirm('确认删除此账号？')) { await API.delete(`/api/accounts/${id}`); loadAccounts(); } }
async function clearAllAccounts() { if (confirm('确认删除此渠道的所有账号？')) { await API.delete(`/api/channels/${currentChannelId}/accounts`); loadAccounts(); } }

function showAccountModal() {
    document.getElementById('account-name').value = '';
    document.getElementById('account-api-key').value = '';
    document.getElementById('account-channel-group').style.display = 'none';
    document.getElementById('account-modal').classList.add('active');
}

async function showAccountModalWithChannel() {
    // Load channels for selection
    const channels = await API.get('/api/providers');
    const select = document.getElementById('account-channel-select');
    select.innerHTML = '<option value="">请选择渠道</option>' + 
        channels.map(c => `<option value="${c.id}">${c.name} (${c.type})</option>`).join('');
    
    document.getElementById('account-name').value = '';
    document.getElementById('account-api-key').value = '';
    document.getElementById('account-channel-group').style.display = 'block';
    document.getElementById('account-channel-select').required = true;
    document.getElementById('account-modal').classList.add('active');
}

document.getElementById('account-form').addEventListener('submit', async e => {
    e.preventDefault();
    
    // Check if channel selection is visible (adding from all accounts page)
    const channelGroup = document.getElementById('account-channel-group');
    let targetChannelId = currentChannelId;
    
    if (channelGroup.style.display !== 'none') {
        // Adding from all accounts page, use selected channel
        targetChannelId = parseInt(document.getElementById('account-channel-select').value);
        if (!targetChannelId) {
            alert('请选择渠道');
            return;
        }
    }
    
    await API.post(`/api/channels/${targetChannelId}/accounts`, {
        name: document.getElementById('account-name').value,
        api_key: document.getElementById('account-api-key').value
    });
    
    closeModal('account-modal');
    
    // Reload appropriate page
    if (channelGroup.style.display !== 'none') {
        loadAccountsAll();
    } else {
        loadAccounts();
    }
});

// All Accounts (Card)
async function loadAccountsAll() {
    const accounts = await API.get('/api/accounts');
    document.getElementById('accounts-all-grid').innerHTML = accounts.map(a => `
        <div class="item-card">
            <div class="item-card-header">
                <div>
                    <div class="item-card-title">${a.name || '账号 #' + a.id}</div>
                    <div class="item-card-subtitle">${a.channel_name || '-'}</div>
                </div>
                <div>${getTypeBadge(a.channel_type)} ${a.enabled ? getBadge('success','启用') : getBadge('danger','禁用')}</div>
            </div>
            <div class="item-card-body">
                <div class="item-card-row">
                    <span class="item-card-label">API Key</span>
                    <span class="item-card-value"><span class="api-key">${a.api_key}</span></span>
                </div>
                <div class="item-card-row">
                    <span class="item-card-label">最后使用</span>
                    <span class="item-card-value">${formatDate(a.last_used_at)}</span>
                </div>
                ${a.channel_type === 'kiro' && a.limit ? getProgressBar(a.usage||0, a.limit) : ''}
            </div>
            <div class="item-card-footer">
                ${a.channel_type==='kiro'?`<button class="btn btn-xs" onclick="refreshAccountUsageAll(${a.id})">刷新</button>`:''}
                ${window.userRole === 'super_admin' ? `<button class="btn btn-xs" onclick="toggleAccountAll(${a.id},${a.enabled})">${a.enabled?'禁用':'启用'}</button>` : ''}
                ${window.userRole === 'super_admin' ? `<button class="btn btn-xs btn-danger" onclick="deleteAccountAll(${a.id})">删除</button>` : ''}
            </div>
        </div>
    `).join('');
}

async function refreshAccountUsageAll(id) {
    const r = await API.post(`/api/accounts/${id}/refresh-usage`);
    r.success ? alert(`用量：${r.usage}/${r.limit}`) : alert('刷新失败：' + r.error);
    loadAccountsAll();
}

async function toggleAccountAll(id, enabled) { await API.put(`/api/accounts/${id}`, { enabled: enabled ? 0 : 1 }); loadAccountsAll(); }
async function deleteAccountAll(id) { if (confirm('确认删除此账号？')) { await API.delete(`/api/accounts/${id}`); loadAccountsAll(); } }

// Users (Card with token stats)
async function loadUsers() {
    const users = await API.get('/api/users');
    document.getElementById('users-grid').innerHTML = users.map(u => {
        const roleText = {
            'super_admin': '超级管理员',
            'admin': '管理员',
            'user': '普通用户'
        }[u.role] || u.role;
        const roleClass = (u.role || 'user').replace('_', '-');
        
        return `
        <div class="card">
            <div class="card-header">
                <h3>${u.name || '用户 #' + u.id}</h3>
                ${u.enabled ? getBadge('success','启用') : getBadge('danger','禁用')}
            </div>
            <div class="card-body">
                <div class="card-info">
                    <span class="label">用户ID:</span>
                    <span class="value">${u.id}</span>
                </div>
                <div class="card-info">
                    <span class="label">邮箱:</span>
                    <span class="value">${u.email || '-'}</span>
                </div>
                <div class="card-info">
                    <span class="label">角色:</span>
                    <span class="value"><span class="role-badge ${roleClass}">${roleText}</span></span>
                </div>
                <div class="card-info">
                    <span class="label">配额:</span>
                    <span class="value">${u.quota === -1 ? '无限制' : u.used_quota.toLocaleString() + ' / ' + u.quota.toLocaleString()}</span>
                </div>
                ${u.quota !== -1 ? getProgressBar(u.used_quota, u.quota, '配额') : ''}
                <div class="token-stats">
                    <div class="stat-item">
                        <div class="stat-label">输入Token</div>
                        <div class="stat-value">${formatTokens(u.input_tokens)}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">输出Token</div>
                        <div class="stat-value">${formatTokens(u.output_tokens)}</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-label">总Token</div>
                        <div class="stat-value">${formatTokens(u.total_tokens)}</div>
                    </div>
                </div>
            </div>
            <div class="card-actions">
                <button class="btn btn-sm" onclick="editUser(${u.id})">编辑</button>
                <button class="btn btn-sm btn-danger" onclick="deleteUser(${u.id})">删除</button>
            </div>
        </div>
    `;
    }).join('');
}

function showUserModal() {
    document.getElementById('user-modal-title').textContent = '添加用户';
    document.getElementById('user-id').value = '';
    document.getElementById('user-name').value = '';
    document.getElementById('user-role').value = 'user';
    document.getElementById('user-quota').value = '-1';
    document.getElementById('user-modal').classList.add('active');
}

async function editUser(id) {
    const users = await API.get('/api/users');
    const user = users.find(u => u.id === id);
    if (!user) return;
    
    console.log('编辑用户:', user);
    
    document.getElementById('user-modal-title').textContent = '编辑用户';
    document.getElementById('user-id').value = user.id;
    document.getElementById('user-name').value = user.name;
    document.getElementById('user-role').value = user.role || 'user';
    document.getElementById('user-quota').value = user.quota;
    
    console.log('表单已填充:', {
        id: document.getElementById('user-id').value,
        name: document.getElementById('user-name').value,
        role: document.getElementById('user-role').value,
        quota: document.getElementById('user-quota').value
    });
    
    // 添加角色选择监听器
    const roleSelect = document.getElementById('user-role');
    roleSelect.onchange = function() {
        console.log('角色已更改为:', this.value);
    };
    
    document.getElementById('user-modal').classList.add('active');
}

async function deleteUser(id) { if (confirm('确认删除此用户？')) { await API.delete(`/api/users/${id}`); loadUsers(); } }

document.getElementById('user-form').addEventListener('submit', async e => {
    e.preventDefault();
    const id = document.getElementById('user-id').value;
    const nameValue = document.getElementById('user-name').value;
    const roleValue = document.getElementById('user-role').value;
    const quotaValue = document.getElementById('user-quota').value;
    
    console.log('表单提交时的原始值:', {
        id: id,
        name: nameValue,
        role: roleValue,
        quota: quotaValue
    });
    
    const data = {
        name: nameValue,
        role: roleValue,
        quota: parseInt(quotaValue)
    };
    
    console.log('提交用户表单:', { id, data });
    
    try {
        if (id) {
            console.log(`更新用户 ${id}:`, data);
            const result = await API.put(`/api/users/${id}`, data);
            console.log('更新结果:', result);
        } else {
            console.log('创建新用户:', data);
            const result = await API.post('/api/users', data);
            console.log('创建结果:', result);
        }
        
        closeModal('user-modal');
        await loadUsers();
        console.log('用户列表已刷新');
    } catch (error) {
        console.error('保存用户失败:', error);
        alert('保存失败: ' + error.message);
    }
});

// Logs (Table)
let logsOffset = 0;
async function loadLogs(append = false) {
    if (!append) logsOffset = 0;
    const logs = await API.get(`/api/logs?limit=50&offset=${logsOffset}`);
    const html = logs.map(l => `
        <tr>
            <td>${formatDate(l.created_at)}</td>
            <td>${l.user_name || '-'}</td>
            <td>${l.channel_name || '-'}</td>
            <td>${l.model}</td>
            <td>${formatTokens(l.input_tokens + l.output_tokens)}</td>
            <td>${l.duration_ms}ms</td>
            <td>${l.status >= 400 ? getBadge('danger', l.status) : getBadge('success', l.status)}</td>
        </tr>
    `).join('');
    const tbody = document.querySelector('#logs-table tbody');
    tbody.innerHTML = append ? tbody.innerHTML + html : html;
    logsOffset += logs.length;
}

function loadMoreLogs() { loadLogs(true); }

// Import
function showImportModal() {
    // Hide channel selector (already in channel context)
    const selectGroup = document.getElementById('import-channel-group');
    if (selectGroup) selectGroup.style.display = 'none';
    
    document.getElementById('import-keys').value = '';
    const f = document.getElementById('import-file'); if(f) f.value = '';
    const j = document.getElementById('import-kiro-json'); if(j) j.value = '';
    document.getElementById('import-standard').style.display = currentChannelType === 'kiro' ? 'none' : 'block';
    document.getElementById('import-kiro').style.display = currentChannelType === 'kiro' ? 'block' : 'none';
    if (currentChannelType === 'kiro') switchImportTab('file');
    document.getElementById('import-modal').classList.add('active');
}

async function showImportModalWithChannel() {
    // Show channel selector in import modal
    const channels = await API.get('/api/providers');
    const selectGroup = document.getElementById('import-channel-group');
    const select = document.getElementById('import-channel-select');
    
    if (select && selectGroup) {
        select.innerHTML = channels.map(c => 
            `<option value="${c.id}" data-type="${c.type}">${c.name} (${c.type})</option>`
        ).join('');
        selectGroup.style.display = 'block';
        
        // Update import type based on selected channel
        select.onchange = function() {
            const selectedOption = this.options[this.selectedIndex];
            const channelType = selectedOption.getAttribute('data-type');
            currentChannelType = channelType;
            currentChannelId = parseInt(this.value);
            document.getElementById('import-standard').style.display = channelType === 'kiro' ? 'none' : 'block';
            document.getElementById('import-kiro').style.display = channelType === 'kiro' ? 'block' : 'none';
            if (channelType === 'kiro') switchImportTab('file');
        };
        
        // Trigger initial setup
        if (channels.length > 0) {
            currentChannelType = channels[0].type;
            currentChannelId = channels[0].id;
            select.onchange();
        }
    }
    
    document.getElementById('import-keys').value = '';
    const f = document.getElementById('import-file'); if(f) f.value = '';
    const j = document.getElementById('import-kiro-json'); if(j) j.value = '';
    document.getElementById('import-modal').classList.add('active');
}

function switchImportTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    event?.target?.classList.add('active');
    document.querySelectorAll('.import-tab-content').forEach(el => el.style.display = 'none');
    document.getElementById(`import-tab-${tab}`).style.display = 'block';
}

async function startKiroLogin() {
    const r = await API.post(`/api/kiro/device-auth`, { channel_id: currentChannelId });
    if (r.error) { alert(r.error.message || '启动登录失败'); return; }
    document.getElementById('kiro-login-status').style.display = 'block';
    document.getElementById('kiro-login-code').textContent = r.userCode;
    window.open(r.verificationUriComplete || r.verificationUri, '_blank');
    pollKiroLogin(r.deviceCode, r._clientId, r._clientSecret, r.interval || 5);
}

async function pollKiroLogin(deviceCode, clientId, clientSecret, interval) {
    let attempts = 0;
    const poll = async () => {
        if (++attempts > 60) { document.getElementById('kiro-login-status').style.display = 'none'; alert('登录超时'); return; }
        const r = await API.post(`/api/kiro/device-token`, { device_code: deviceCode, client_id: clientId, client_secret: clientSecret, channel_id: currentChannelId });
        if (r.success) { document.getElementById('kiro-login-status').style.display = 'none'; alert(`已导入 ${r.imported} 个账号`); closeModal('import-modal'); loadAccounts(); return; }
        if (r.error === 'authorization_pending') setTimeout(poll, interval * 1000);
        else if (r.error) { document.getElementById('kiro-login-status').style.display = 'none'; alert('登录失败：' + r.error); }
    };
    setTimeout(poll, interval * 1000);
}

document.getElementById('import-form').addEventListener('submit', async e => {
    e.preventDefault();
    let result;
    if (currentChannelType === 'kiro') {
        const file = document.getElementById('import-file')?.files[0];
        const json = document.getElementById('import-kiro-json')?.value.trim();
        if (file) { try { result = await API.post(`/api/channels/${currentChannelId}/accounts/import`, JSON.parse(await file.text())); } catch { alert('无效的 JSON 文件'); return; } }
        else if (json) { try { result = await API.post(`/api/channels/${currentChannelId}/accounts/import`, JSON.parse(json)); } catch { alert('无效的 JSON 格式'); return; } }
        else { alert('请上传文件或粘贴 JSON'); return; }
    } else {
        const keys = document.getElementById('import-keys').value.trim();
        if (!keys) { alert('请输入 API Keys'); return; }
        result = await API.post(`/api/channels/${currentChannelId}/accounts/import`, keys, 'text/plain');
    }
    alert(`已导入 ${result.imported} 个账号`);
    closeModal('import-modal');
    loadAccounts();
});

// Modal
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

// ===== Token Management =====
async function loadTokens() {
    // All users (including super_admin) only see their own tokens
    const endpoint = '/api/auth/tokens';
    const tokens = await API.get(endpoint);
    
    // Show "Add Token" button for all users (super_admin and regular users)
    const tokenActions = document.getElementById('token-actions');
    if (tokenActions) {
        // Hide for admin, show for super_admin and user
        tokenActions.style.display = window.userRole === 'admin' ? 'none' : '';
    }
    
    const grid = document.getElementById('tokens-grid');
    grid.innerHTML = tokens.map(t => {
        const statusText = {1: '启用', 2: '禁用', 4: '已过期'}[t.status] || '未知';
        const statusClass = {1: 'success', 2: 'warning', 4: 'error'}[t.status] || '';
        const expiredText = t.expired_time === -1 ? '永不过期' : formatDate(t.expired_time * 1000);
        
        // Only super_admin can edit/delete tokens
        const canEdit = window.userRole === 'super_admin';
        
        return `
            <div class="card">
                <div class="card-header">
                    <h3>${t.name || '未命名令牌'}</h3>
                    <span class="badge badge-${statusClass}">${statusText}</span>
                </div>
                <div class="card-body">
                    <div class="card-info">
                        <span class="label">Key:</span>
                        <span class="value" style="display: flex; align-items: center; gap: 8px;">
                            <code id="token-key-${t.id}">${t.key.substring(0, 20)}...${t.key.substring(t.key.length - 4)}</code>
                            <button class="btn btn-sm" onclick="copyTokenKey('${t.key}', ${t.id}, event)" title="复制完整Key">📋</button>
                        </span>
                    </div>
                    <div class="card-info">
                        <span class="label">过期时间:</span>
                        <span class="value">${expiredText}</span>
                    </div>
                    <div class="card-info">
                        <span class="label">分组:</span>
                        <span class="value">${t.group || 'default'}</span>
                    </div>
                    ${t.rpm_limit > 0 || t.tpm_limit > 0 ? `
                    <div class="card-info">
                        <span class="label">速率限制:</span>
                        <span class="value">${t.rpm_limit > 0 ? `RPM: ${t.rpm_limit}` : ''}${t.rpm_limit > 0 && t.tpm_limit > 0 ? ' | ' : ''}${t.tpm_limit > 0 ? `TPM: ${t.tpm_limit.toLocaleString()}` : ''}</span>
                    </div>` : ''}
                    ${t.model_limits_enabled ? `
                    <div class="card-info">
                        <span class="label">模型限制:</span>
                        <span class="value">${t.model_limits || '无'}</span>
                    </div>` : ''}
                    ${t.cross_group_retry ? `
                    <div class="card-info">
                        <span class="label">跨分组重试:</span>
                        <span class="value">✅ 已启用</span>
                    </div>` : ''}
                    <div class="token-stats">
                        <div class="stat-item">
                            <div class="stat-label">请求数</div>
                            <div class="stat-value">${t.request_count || 0}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">输入Token</div>
                            <div class="stat-value">${formatTokens(t.input_tokens)}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">输出Token</div>
                            <div class="stat-value">${formatTokens(t.output_tokens)}</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-label">总Token</div>
                            <div class="stat-value">${formatTokens(t.total_tokens)}</div>
                        </div>
                    </div>
                </div>
                ${canEdit ? `
                <div class="card-actions">
                    <button class="btn btn-sm" onclick="editToken(${t.id})">编辑</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteToken(${t.id}, '${t.name}')">删除</button>
                </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

function copyTokenKey(key, tokenId, event) {
    navigator.clipboard.writeText(key).then(() => {
        const btn = event.target;
        const originalText = btn.textContent;
        btn.textContent = '✓';
        setTimeout(() => btn.textContent = originalText, 2000);
    }).catch(err => {
        alert('复制失败：' + err);
    });
}

async function showTokenModal() {
    document.getElementById('token-modal-title').textContent = '添加令牌';
    document.getElementById('token-id').value = '';
    document.getElementById('token-name').value = '';
    
    // Set user_id to current user's id
    if (currentUser) {
        document.getElementById('token-user-id').value = currentUser.id;
    } else {
        document.getElementById('token-user-id').value = '0';
    }
    
    document.getElementById('token-expired-time').value = '';
    document.getElementById('token-model-limits-enabled').checked = false;
    document.getElementById('token-model-limits').value = '';
    document.getElementById('token-ip-whitelist').value = '';
    document.getElementById('token-group').value = 'default';
    document.getElementById('token-cross-group-retry').checked = false;
    document.getElementById('token-rpm-limit').value = '0';
    document.getElementById('token-tpm-limit').value = '0';
    
    toggleTokenModelsField();
    document.getElementById('token-modal').classList.add('active');
}

async function editToken(id) {
    const tokens = await API.get('/api/tokens');
    const token = tokens.find(t => t.id === id);
    if (!token) return;
    
    document.getElementById('token-modal-title').textContent = '编辑令牌';
    document.getElementById('token-id').value = token.id;
    document.getElementById('token-name').value = token.name;
    document.getElementById('token-user-id').value = token.user_id || 0;
    
    if (token.expired_time !== -1) {
        const date = new Date(token.expired_time * 1000);
        document.getElementById('token-expired-time').value = date.toISOString().slice(0, 16);
    } else {
        document.getElementById('token-expired-time').value = '';
    }
    
    document.getElementById('token-model-limits-enabled').checked = token.model_limits_enabled;
    document.getElementById('token-model-limits').value = token.model_limits;
    document.getElementById('token-ip-whitelist').value = token.ip_whitelist;
    document.getElementById('token-group').value = token.group;
    document.getElementById('token-cross-group-retry').checked = token.cross_group_retry || false;
    document.getElementById('token-rpm-limit').value = token.rpm_limit || 0;
    document.getElementById('token-tpm-limit').value = token.tpm_limit || 0;
    
    toggleTokenModelsField();
    document.getElementById('token-modal').classList.add('active');
}

async function deleteToken(id, name) {
    if (!confirm(`确定要删除令牌 "${name}" 吗？`)) return;
    await API.delete(`/api/tokens/${id}`);
    alert('删除成功');
    loadTokens();
}

function toggleTokenModelsField() {
    const enabled = document.getElementById('token-model-limits-enabled').checked;
    const group = document.getElementById('token-model-limits-group');
    if (group) {
        group.style.display = enabled ? 'block' : 'none';
    }
}

// Token form event listeners
document.getElementById('token-model-limits-enabled')?.addEventListener('change', toggleTokenModelsField);

function toggleTokenModelLimits() {
    const enabled = document.getElementById('token-model-limits-enabled').checked;
    document.getElementById('token-model-limits-group').style.display = enabled ? 'block' : 'none';
}

// Token form event listeners
document.getElementById('token-model-limits-enabled').addEventListener('change', toggleTokenModelLimits);

document.getElementById('token-form').addEventListener('submit', async e => {
    e.preventDefault();
    const id = document.getElementById('token-id').value;
    
    const expiredTimeInput = document.getElementById('token-expired-time').value;
    let expiredTime = -1;
    if (expiredTimeInput) {
        expiredTime = Math.floor(new Date(expiredTimeInput).getTime() / 1000);
    }
    
    const data = {
        name: document.getElementById('token-name').value,
        user_id: parseInt(document.getElementById('token-user-id').value) || 0,
        expired_time: expiredTime,
        model_limits_enabled: document.getElementById('token-model-limits-enabled').checked,
        model_limits: document.getElementById('token-model-limits').value.trim(),
        ip_whitelist: document.getElementById('token-ip-whitelist').value.trim(),
        group: document.getElementById('token-group').value.trim() || 'default',
        cross_group_retry: document.getElementById('token-cross-group-retry').checked,
        rpm_limit: parseInt(document.getElementById('token-rpm-limit').value) || 0,
        tpm_limit: parseInt(document.getElementById('token-tpm-limit').value) || 0
    };
    
    if (id) {
        await API.put(`/api/tokens/${id}`, data);
        alert('更新成功');
    } else {
        const result = await API.post('/api/tokens', data);
        alert(`创建成功！\n\nToken Key:\n${result.key}\n\n请妥善保管，此Key只显示一次！`);
    }
    
    closeModal('token-modal');
    loadTokens();
});

// ==================== User Profile & Auth ====================

let currentUser = null;

// Load current user info
async function loadCurrentUser() {
    try {
        currentUser = await API.get('/api/auth/me');
        
        // Update sidebar user info
        const email = currentUser.email || '';
        const name = currentUser.name || '';
        const role = currentUser.role || 'user';
        
        document.getElementById('user-email').textContent = email;
        document.getElementById('user-avatar-text').textContent = (name || email).charAt(0).toUpperCase();
        
        // Set role badge
        const roleText = {
            'super_admin': '超级管理员',
            'admin': '管理员',
            'user': '普通用户'
        }[role] || role;
        document.getElementById('current-user-role').textContent = roleText;
        
        // Apply permission-based UI control
        applyPermissions(currentUser);
        
    } catch (err) {
        console.error('Failed to load user:', err);
        // If failed, redirect to login
        window.location.href = '/login';
    }
}

// Apply permission-based UI control
function applyPermissions(user) {
    const role = user.role;
    const permissions = user.permissions || {};
    
    // Hide menu items based on role
    const menuItems = document.querySelectorAll('.nav-menu li');
    menuItems.forEach(item => {
        const link = item.querySelector('a');
        const page = link.getAttribute('data-page');
        
        // Hide users page for admin and regular users
        if ((role === 'admin' || role === 'user') && page === 'users') {
            item.style.display = 'none';
        }
        
        // Regular users can access: dashboard, tokens, profile
        // Hide: channels, accounts, logs
        if (role === 'user' && ['channels', 'accounts', 'logs'].includes(page)) {
            item.style.display = 'none';
        }
        
        // Admin can access all except users
        // (already handled above)
    });
    
    // Hide dashboard sections for non-super_admin users
    if (role !== 'super_admin') {
        // Hide channel stats section
        const channelStatsSection = document.getElementById('channel-stats-section');
        if (channelStatsSection) {
            channelStatsSection.style.display = 'none';
        }
        
        // Hide top users section
        const topUsersSection = document.getElementById('top-users-section');
        if (topUsersSection) {
            topUsersSection.style.display = 'none';
        }
    }
    
    // Store permissions globally for later use
    window.userPermissions = permissions;
    window.userRole = role;
}

// Logout
async function logout() {
    if (!confirm('确定要退出登录吗？')) return;
    
    try {
        await API.post('/api/auth/logout');
        window.location.href = '/login';
    } catch (err) {
        console.error('Logout failed:', err);
        // Force redirect anyway
        window.location.href = '/login';
    }
}

// Load profile page
async function loadProfile() {
    if (!currentUser) {
        await loadCurrentUser();
    }
    
    // Basic info
    document.getElementById('profile-email').textContent = currentUser.email || '-';
    document.getElementById('profile-name').textContent = currentUser.name || '-';
    document.getElementById('profile-last-login').textContent = currentUser.last_login_at || '-';
    
    // Role badge
    const role = currentUser.role || 'user';
    const roleText = {
        'super_admin': '超级管理员',
        'admin': '管理员',
        'user': '普通用户'
    }[role] || role;
    const roleClass = role.replace('_', '-');
    document.getElementById('profile-role-badge').innerHTML = `<span class="role-badge ${roleClass}">${roleText}</span>`;
    
    // Usage stats
    document.getElementById('profile-total-tokens').textContent = formatTokens(currentUser.total_tokens || 0);
    document.getElementById('profile-input-tokens').textContent = formatTokens(currentUser.input_tokens || 0);
    document.getElementById('profile-output-tokens').textContent = formatTokens(currentUser.output_tokens || 0);
    
    const quota = currentUser.quota || 0;
    const usedQuota = currentUser.used_quota || 0;
    if (quota === -1) {
        document.getElementById('profile-quota').textContent = '无限制';
    } else {
        document.getElementById('profile-quota').textContent = `${formatTokens(usedQuota)} / ${formatTokens(quota)}`;
    }
}

// Change password
async function changePassword() {
    const oldPassword = document.getElementById('old-password').value;
    const newPassword = document.getElementById('new-password').value;
    const confirmPassword = document.getElementById('confirm-password').value;
    
    if (newPassword !== confirmPassword) {
        alert('两次输入的新密码不一致！');
        return;
    }
    
    if (newPassword.length < 6) {
        alert('新密码长度至少为6位！');
        return;
    }
    
    try {
        await API.post('/api/auth/change-password', {
            old_password: oldPassword,
            new_password: newPassword
        });
        
        alert('密码修改成功！请重新登录。');
        window.location.href = '/login';
    } catch (err) {
        alert('密码修改失败：' + (err.message || '未知错误'));
    }
}

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Init
loadCurrentUser().then(() => {
    loadDashboard();
});
