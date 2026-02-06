// 风控系统前端 JavaScript

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

// API wrapper
const API = {
    async request(method, url, data = null) {
        console.log(`API Request: ${method} ${url}`);
        
        const options = { 
            method, 
            headers: {},
            credentials: 'include'
        };
        
        if (data) {
            options.body = JSON.stringify(data);
            options.headers['Content-Type'] = 'application/json';
        }
        
        const resp = await fetch(url, options);
        
        console.log(`API Response: ${resp.status} ${resp.statusText}`);
        
        if (resp.status === 401) {
            console.error('401 Unauthorized - redirecting to login');
            window.location.href = '/login';
            return;
        }
        
        if (resp.status === 403) {
            console.error('403 Forbidden - insufficient permissions');
            alert('权限不足：仅超级管理员可访问风控系统');
            window.location.href = '/';
            return;
        }
        
        if (resp.status === 404) {
            console.error('404 Not Found:', url);
            throw new Error(`API endpoint not found: ${url}`);
        }
        
        return resp.json();
    },
    get: (url) => API.request('GET', url),
    post: (url, data) => API.request('POST', url, data),
    put: (url, data) => API.request('PUT', url, data),
    delete: (url) => API.request('DELETE', url)
};

// 检查用户权限
async function checkPermission() {
    try {
        const user = await API.get('/api/auth/me');
        console.log('Current user:', user);
        
        if (!user || user.role !== 'super_admin') {
            alert('权限不足：仅超级管理员可访问风控系统');
            window.location.href = '/';
            return false;
        }
        
        // 显示用户信息
        document.getElementById('user-email').textContent = user.email;
        document.getElementById('user-avatar-text').textContent = user.name ? user.name[0].toUpperCase() : 'A';
        document.getElementById('current-user-role').textContent = '超级管理员';
        
        return true;
    } catch (e) {
        console.error('Failed to check permission:', e);
        alert('权限检查失败: ' + e.message);
        window.location.href = '/login';
        return false;
    }
}

// 退出登录
async function logout() {
    await API.post('/api/auth/logout');
    window.location.href = '/login';
}

// Navigation
document.querySelectorAll('.nav-menu a').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        const page = link.dataset.page;
        if (page) {
            showPage(page);
            loadPageData(page);
        }
    });
});

function showPage(page) {
    document.querySelectorAll('.nav-menu a').forEach(l => l.classList.remove('active'));
    document.querySelector(`.nav-menu a[data-page="${page}"]`)?.classList.add('active');
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(`page-${page}`)?.classList.add('active');
}

function loadPageData(page) {
    const loaders = {
        overview: loadOverview,
        'proxy-pool': loadProxyPool,
        'health-monitor': loadHealthMonitor,
        'rate-limit': loadRateLimit,
        config: loadConfig
    };
    loaders[page]?.();
}

// ==================== 系统概览 ====================
async function loadOverview() {
    try {
        const status = await API.get('/api/risk-control/status');
        
        // 代理池状态
        if (status.components.proxy_pool) {
            const proxy = status.components.proxy_pool;
            document.getElementById('overview-proxy-status').textContent = 
                proxy.alive_proxies > 0 ? '运行中' : '未配置';
            document.getElementById('overview-proxy-detail').textContent = 
                proxy.alive_proxies + '/' + proxy.total_proxies + ' 存活';
        } else {
            document.getElementById('overview-proxy-status').textContent = '未启用';
            document.getElementById('overview-proxy-detail').textContent = '未配置代理';
        }
        
        // 健康监控状态
        if (status.components.health_monitor) {
            const health = status.components.health_monitor;
            document.getElementById('overview-health-status').textContent = 
                health.healthy + '/' + health.total_accounts + ' 健康';
            document.getElementById('overview-health-detail').textContent = 
                '降级: ' + health.degraded + ', 封禁: ' + health.banned;
            
            // 更新摘要
            document.getElementById('summary-healthy').textContent = health.healthy;
            document.getElementById('summary-degraded').textContent = health.degraded;
            document.getElementById('summary-unhealthy').textContent = health.unhealthy;
            document.getElementById('summary-banned').textContent = health.banned;
        } else {
            document.getElementById('overview-health-status').textContent = '❌ 未启用';
            document.getElementById('overview-health-detail').textContent = '未监控';
        }
        
        // 速率限制状态
        if (status.components.rate_limiter) {
            document.getElementById('overview-rate-status').textContent = '运行中';
            document.getElementById('overview-rate-detail').textContent = '多级限流';
        } else {
            document.getElementById('overview-rate-status').textContent = '未启用';
            document.getElementById('overview-rate-detail').textContent = '未配置';
        }
        
        // 指纹伪装状态
        document.getElementById('overview-fingerprint-status').textContent = 
            status.initialized ? '运行中' : '未启用';
        
        // 加载代理池摘要
        if (status.components.proxy_pool) {
            await loadProxySummary();
        }
        
    } catch (e) {
        console.error('Failed to load overview:', e);
        alert('加载系统概览失败');
    }
}

async function loadProxySummary() {
    try {
        const data = await API.get('/api/risk-control/proxy-pool/stats');
        const tbody = document.querySelector('#proxy-summary-table tbody');
        
        if (!data.proxies || data.proxies.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center">暂无代理</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.proxies.slice(0, 5).map(p => `
            <tr>
                <td><code>${p.proxy}</code></td>
                <td>${p.country || '-'} ${p.region || ''}</td>
                <td>${getStatusBadge(p.is_alive)}</td>
                <td>${p.total_requests}</td>
                <td>${p.success_rate}</td>
                <td>${p.avg_response_time}</td>
                <td>${p.bound_accounts}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load proxy summary:', e);
    }
}

function refreshOverview() {
    loadOverview();
}

// ==================== 代理池管理 ====================
async function loadProxyPool() {
    try {
        const data = await API.get('/api/risk-control/proxy-pool/stats');
        
        // 更新统计
        document.getElementById('proxy-total').textContent = data.total_proxies;
        document.getElementById('proxy-alive').textContent = data.alive_proxies;
        document.getElementById('proxy-dead').textContent = data.dead_proxies;
        document.getElementById('proxy-strategy').textContent = data.strategy.toUpperCase();
        
        // 更新代理列表
        const tbody = document.querySelector('#proxy-list-table tbody');
        
        if (!data.proxies || data.proxies.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" style="text-align:center">暂无代理，请点击"添加代理"按钮添加</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.proxies.map(p => `
            <tr>
                <td><code>${p.proxy}</code></td>
                <td>${p.proxy.split('://')[0].toUpperCase()}</td>
                <td>${p.country || '-'} ${p.region ? '/ ' + p.region : ''}</td>
                <td>${p.isp || '-'}</td>
                <td>${getStatusBadge(p.is_alive)}</td>
                <td>${p.total_requests}</td>
                <td>${p.success_rate}</td>
                <td>${p.avg_response_time}</td>
                <td>${p.bound_accounts}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-xs btn-secondary" onclick="testProxy('${p.proxy}')">测试</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load proxy pool:', e);
        // 移除弹窗提示
    }
}

function refreshProxyPool() {
    loadProxyPool();
}

function showAddProxyModal() {
    document.getElementById('add-proxy-modal').classList.add('active');
}

function closeAddProxyModal() {
    document.getElementById('add-proxy-modal').classList.remove('active');
    // 清空表单
    document.getElementById('proxy-host').value = '';
    document.getElementById('proxy-port').value = '';
    document.getElementById('proxy-username').value = '';
    document.getElementById('proxy-password').value = '';
    document.getElementById('proxy-country').value = '';
    document.getElementById('proxy-region').value = '';
    document.getElementById('proxy-isp').value = '';
}

async function addProxy() {
    const host = document.getElementById('proxy-host').value.trim();
    const port = parseInt(document.getElementById('proxy-port').value);
    const protocol = document.getElementById('proxy-protocol').value;
    const username = document.getElementById('proxy-username').value.trim();
    const password = document.getElementById('proxy-password').value.trim();
    const country = document.getElementById('proxy-country').value.trim();
    const region = document.getElementById('proxy-region').value.trim();
    const isp = document.getElementById('proxy-isp').value.trim();
    
    if (!host || !port) {
        alert('请填写代理地址和端口');
        return;
    }
    
    try {
        const data = {
            host,
            port,
            protocol,
            username: username || undefined,
            password: password || undefined,
            country: country || undefined,
            region: region || undefined,
            isp: isp || undefined
        };
        
        const result = await API.post('/api/risk-control/proxy-pool/add', data);
        
        if (result.success) {
            alert(`代理添加成功！\n状态: ${result.is_alive ? '存活' : '失效'}`);
            closeAddProxyModal();
            loadProxyPool();
        } else {
            alert('代理添加失败');
        }
    } catch (e) {
        console.error('Failed to add proxy:', e);
        alert('代理添加失败: ' + e.message);
    }
}

async function healthCheckProxies() {
    if (!confirm('确定要对所有代理进行健康检查吗？这可能需要一些时间。')) {
        return;
    }
    
    try {
        const result = await API.post('/api/risk-control/proxy-pool/health-check');
        alert(`健康检查完成！\n存活: ${result.alive_proxies}\n失效: ${result.dead_proxies}`);
        loadProxyPool();
    } catch (e) {
        console.error('Failed to health check:', e);
        alert('健康检查失败');
    }
}

async function testProxy(proxyUrl) {
    alert('测试代理: ' + proxyUrl);
    // TODO: 实现单个代理测试
}

// ==================== 账号健康监控 ====================
async function loadHealthMonitor() {
    try {
        const data = await API.get('/api/risk-control/health-monitor/stats');
        
        // 更新统计
        const summary = data.summary;
        document.getElementById('health-total').textContent = summary.total_accounts;
        document.getElementById('health-healthy').textContent = summary.healthy;
        document.getElementById('health-degraded').textContent = summary.degraded;
        document.getElementById('health-banned').textContent = summary.banned;
        
        // 更新账号列表
        const tbody = document.querySelector('#health-list-table tbody');
        
        if (!data.accounts || data.accounts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="12" style="text-align:center">暂无账号数据</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.accounts.map(a => `
            <tr>
                <td><strong>#${a.account_id}</strong></td>
                <td>${getHealthStatusBadge(a.status)}</td>
                <td>${getRiskBadge(a.risk_level)}</td>
                <td>${a.success_rate}</td>
                <td>${a.recent_failure_rate}</td>
                <td>${a.total_requests}</td>
                <td>${a.failed_requests}</td>
                <td>${a.consecutive_failures}</td>
                <td>${a.rate_limit_errors}</td>
                <td>${a.auth_errors}</td>
                <td>${a.avg_response_time}</td>
                <td>
                    <div class="action-buttons">
                        ${a.status !== 'healthy' ? 
                            `<button class="btn btn-xs btn-success" onclick="recoverAccount(${a.account_id})">恢复</button>` : 
                            `<button class="btn btn-xs btn-warning" onclick="degradeAccount(${a.account_id})">降级</button>`
                        }
                        <button class="btn btn-xs btn-danger" onclick="banAccount(${a.account_id})">封禁</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load health monitor:', e);
        // 移除弹窗提示
    }
}

function refreshHealthMonitor() {
    loadHealthMonitor();
}

async function degradeAccount(accountId) {
    const duration = prompt('降级时长（秒）：', '3600');
    if (!duration) return;
    
    try {
        await API.post(`/api/risk-control/accounts/${accountId}/degrade`, {
            duration: parseInt(duration)
        });
        alert('账号已降级');
        loadHealthMonitor();
    } catch (e) {
        console.error('Failed to degrade account:', e);
        alert('降级失败');
    }
}

async function banAccount(accountId) {
    if (!confirm('确定要封禁此账号吗？')) return;
    
    const duration = prompt('封禁时长（秒）：', '86400');
    if (!duration) return;
    
    try {
        await API.post(`/api/risk-control/accounts/${accountId}/ban`, {
            duration: parseInt(duration)
        });
        alert('账号已封禁');
        loadHealthMonitor();
    } catch (e) {
        console.error('Failed to ban account:', e);
        alert('封禁失败');
    }
}

async function recoverAccount(accountId) {
    if (!confirm('确定要恢复此账号吗？')) return;
    
    try {
        await API.post(`/api/risk-control/accounts/${accountId}/recover`);
        alert('账号已恢复');
        loadHealthMonitor();
    } catch (e) {
        console.error('Failed to recover account:', e);
        alert('恢复失败');
    }
}

// ==================== 速率限制 ====================
async function loadRateLimit() {
    try {
        const data = await API.get('/api/risk-control/rate-limit/stats');
        
        // 全局限制
        if (data.global) {
            const g = data.global;
            document.getElementById('global-requests').textContent = g.requests_last_minute;
            document.getElementById('global-tokens').textContent = g.tokens_last_minute.toLocaleString();
            document.getElementById('global-available-requests').textContent = g.available_request_tokens;
            document.getElementById('global-available-tokens').textContent = g.available_token_quota.toLocaleString();
            document.getElementById('global-rpm-limit').textContent = g.rpm_limit;
            document.getElementById('global-tpm-limit').textContent = g.tpm_limit.toLocaleString();
        } else {
            document.getElementById('global-rate-limit').innerHTML = '<p>全局速率限制未启用</p>';
        }
        
        // 账号级限制
        const tbody = document.querySelector('#account-rate-limit-table tbody');
        
        if (!data.accounts || Object.keys(data.accounts).length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center">暂无账号级限制数据</td></tr>';
            return;
        }
        
        tbody.innerHTML = Object.entries(data.accounts).map(([id, stats]) => `
            <tr>
                <td><strong>#${id}</strong></td>
                <td>${stats.requests_last_minute}</td>
                <td>${stats.tokens_last_minute.toLocaleString()}</td>
                <td>${stats.available_request_tokens}</td>
                <td>${stats.available_token_quota.toLocaleString()}</td>
                <td>${stats.rpm_limit}</td>
                <td>${stats.tpm_limit.toLocaleString()}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load rate limit:', e);
        // 移除弹窗提示
    }
}

function refreshRateLimit() {
    loadRateLimit();
}

// ==================== 系统配置 ====================
async function loadConfig() {
    // 配置功能：直接编辑配置文件
    console.log('Config page loaded - edit risk_control_config.json directly');
}

async function saveConfig() {
    console.log('Config save - edit risk_control_config.json directly and restart service');
}

// ==================== 辅助函数 ====================
function getStatusBadge(isAlive) {
    return `<span class="status-badge ${isAlive ? 'alive' : 'dead'}">${isAlive ? '存活' : '失效'}</span>`;
}

function getHealthStatusBadge(status) {
    const map = {
        healthy: '健康',
        degraded: '降级',
        unhealthy: '不健康',
        banned: '已封禁'
    };
    return `<span class="status-badge ${status}">${map[status] || status}</span>`;
}

function getRiskBadge(level) {
    const map = {
        low: '低',
        medium: '中',
        high: '高',
        critical: '严重'
    };
    return `<span class="risk-badge ${level}">${map[level] || level}</span>`;
}

// ==================== 初始化 ====================
(async function init() {
    console.log('=== Risk Control System Initialization ===');
    
    // 显示调试信息
    const debugInfo = document.getElementById('debug-info');
    if (debugInfo) {
        debugInfo.textContent = 'JavaScript已加载';
    }
    
    console.log('Step 1: Checking permission...');
    
    // 检查权限
    const hasPermission = await checkPermission();
    if (!hasPermission) {
        console.log('Permission check failed');
        if (debugInfo) debugInfo.textContent = '权限检查失败';
        return;
    }
    
    console.log('Step 2: Permission check passed');
    if (debugInfo) debugInfo.textContent = '权限检查通过';
    
    console.log('Step 3: Loading overview...');
    
    // 加载默认页面
    try {
        await loadOverview();
        console.log('Step 4: Overview loaded successfully');
        if (debugInfo) {
            debugInfo.textContent = '系统概览加载成功';
            setTimeout(() => debugInfo.style.display = 'none', 3000);
        }
    } catch (e) {
        console.error('Failed to load overview:', e);
        if (debugInfo) debugInfo.textContent = '加载失败: ' + e.message;
        // 移除弹窗提示
    }
    
    // 设置自动刷新（每30秒）
    setInterval(() => {
        const activePage = document.querySelector('.page.active');
        if (activePage) {
            const pageId = activePage.id.replace('page-', '');
            console.log('Auto refreshing page:', pageId);
            loadPageData(pageId);
        }
    }, 30000);
    
    console.log('=== Risk Control System Initialized ===');
})();
