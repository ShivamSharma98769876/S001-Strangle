// Dashboard JavaScript for real-time updates
// Simplified version with core functionality

let updateInterval;
let isAuthenticated = false;
let cumulativePnlChart = null;

// Define showAuthModal early so it's available for inline onclick handlers
window.showAuthModal = function showAuthModal() {
    console.log('[Auth] Attempting to show auth modal');
    const modal = document.getElementById('authModal');
    if (!modal) {
        console.error('[Auth] Auth modal element not found!');
        alert('Authentication modal not found. Please refresh the page.');
        return;
    }
    
    modal.style.display = 'flex';
    populateAuthFormFields();
    updateKiteConnectLink();
};

function hideAuthModal() {
    const modal = document.getElementById('authModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Pre-populate authentication form fields
async function populateAuthFormFields() {
    let serverDetails = {};
    try {
        const response = await fetch('/api/auth/details', {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            if (data.success && data.details) {
                serverDetails = data.details;
            }
        }
    } catch (error) {
        console.error('Error fetching auth details from server:', error);
    }
    
    const apiKey = serverDetails.api_key || '';
    const apiSecret = serverDetails.api_secret || '';
    const accessToken = serverDetails.access_token || '';
    const requestToken = serverDetails.request_token || '';
    
    const apiKeyField = document.getElementById('apiKey');
    if (apiKeyField && apiKey) apiKeyField.value = apiKey;
    
    const apiSecretField = document.getElementById('apiSecret');
    if (apiSecretField && apiSecret) apiSecretField.value = apiSecret;
    
    const requestTokenField = document.getElementById('requestToken');
    if (requestTokenField && requestToken) requestTokenField.value = requestToken;
    
    const accessTokenApiKeyField = document.getElementById('accessTokenApiKey');
    if (accessTokenApiKeyField && apiKey) accessTokenApiKeyField.value = apiKey;
    
    const accessTokenApiSecretField = document.getElementById('accessTokenApiSecret');
    if (accessTokenApiSecretField && apiSecret) accessTokenApiSecretField.value = apiSecret;
    
    const accessTokenField = document.getElementById('accessToken');
    if (accessTokenField && accessToken) accessTokenField.value = accessToken;
}

// Update Kite Connect link with API key
function updateKiteConnectLink() {
    const apiKeyField = document.getElementById('apiKey');
    const kiteConnectLink = document.getElementById('kiteConnectLink');
    
    if (apiKeyField && kiteConnectLink) {
        if (apiKeyField.value.trim()) {
            kiteConnectLink.href = `https://kite.trade/connect/login?api_key=${apiKeyField.value.trim()}`;
        }
        
        apiKeyField.addEventListener('input', function() {
            const apiKey = this.value.trim();
            if (apiKey) {
                kiteConnectLink.href = `https://kite.trade/connect/login?api_key=${apiKey}`;
            } else {
                kiteConnectLink.href = 'https://kite.trade/connect/login';
            }
        });
    }
}

// Switch authentication tabs
function switchAuthTab(tab) {
    const accessTokenTab = document.getElementById('tabAccessToken');
    const requestTokenTab = document.getElementById('tabRequestToken');
    const accessTokenForm = document.getElementById('accessTokenForm');
    const requestTokenForm = document.getElementById('requestTokenForm');
    
    if (tab === 'accessToken') {
        accessTokenTab.classList.add('auth-tab-active');
        requestTokenTab.classList.remove('auth-tab-active');
        accessTokenForm.style.display = 'block';
        requestTokenForm.style.display = 'none';
    } else {
        requestTokenTab.classList.add('auth-tab-active');
        accessTokenTab.classList.remove('auth-tab-active');
        requestTokenForm.style.display = 'block';
        accessTokenForm.style.display = 'none';
    }
}

// Authenticate with access token
async function authenticateWithAccessToken(event) {
    event.preventDefault();
    const apiKey = document.getElementById('accessTokenApiKey').value;
    const apiSecret = document.getElementById('accessTokenApiSecret').value;
    const accessToken = document.getElementById('accessToken').value;
    const errorDiv = document.getElementById('authError');
    
    errorDiv.style.display = 'none';
    errorDiv.textContent = '';
    
    try {
        const response = await fetch('/api/auth/set-access-token', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
                api_key: apiKey,
                api_secret: apiSecret,
                access_token: accessToken
            })
        });
        
        const data = await response.json();
        if (data.success) {
            hideAuthModal();
            await checkAuthStatus();
            // Update auth details after successful authentication
            await updateAuthDetails();
            if (typeof addNotification === 'function') {
                addNotification('Successfully authenticated', 'success');
            }
        } else {
            errorDiv.textContent = data.message || 'Authentication failed';
            errorDiv.style.display = 'block';
        }
    } catch (error) {
        errorDiv.textContent = 'Error: ' + error.message;
        errorDiv.style.display = 'block';
    }
}

// Authenticate with request token
async function authenticateWithRequestToken(event) {
    event.preventDefault();
    const apiKey = document.getElementById('apiKey').value;
    const apiSecret = document.getElementById('apiSecret').value;
    const requestToken = document.getElementById('requestToken').value;
    const errorDiv = document.getElementById('authErrorRequest');
    const accessTokenDisplay = document.getElementById('accessTokenDisplay');
    const generatedAccessToken = document.getElementById('generatedAccessToken');
    const submitBtn = document.getElementById('authSubmitBtn');
    
    errorDiv.style.display = 'none';
    errorDiv.textContent = '';
    accessTokenDisplay.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Generating...';
    
    try {
        const response = await fetch('/api/auth/generate-access-token', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({
                api_key: apiKey,
                api_secret: apiSecret,
                request_token: requestToken
            })
        });
        
        const data = await response.json();
        if (data.success && data.access_token) {
            generatedAccessToken.value = data.access_token;
            accessTokenDisplay.style.display = 'block';
            hideAuthModal();
            await checkAuthStatus();
            // Update auth details after successful authentication
            await updateAuthDetails();
            if (typeof addNotification === 'function') {
                addNotification('Access token generated and saved', 'success');
            }
        } else {
            errorDiv.textContent = data.message || 'Failed to generate access token';
            errorDiv.style.display = 'block';
        }
    } catch (error) {
        errorDiv.textContent = 'Error: ' + error.message;
        errorDiv.style.display = 'block';
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Generate & Connect';
    }
}

// Check authentication status
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/status', {
            credentials: 'include'
        });
        if (!response.ok) {
            isAuthenticated = false;
            updateAuthUI(false);
            return;
        }
        
        const data = await response.json();
        // CRITICAL: Only set as authenticated if explicitly authenticated (not just session exists)
        // This prevents showing as connected when session exists from another machine
        isAuthenticated = data.authenticated === true && data.has_access_token === true;
        updateAuthUI(isAuthenticated, data);
        
        if (isAuthenticated) {
            // Update auth details when authenticated
            await updateAuthDetails();
            startUpdates();
        } else {
            stopUpdates();
        }
    } catch (error) {
        console.error('Error checking auth status:', error);
        isAuthenticated = false;
        updateAuthUI(false);
    }
}

// Update authentication UI
function updateAuthUI(authenticated, authData = null) {
    const authStatus = document.getElementById('authStatus');
    const userInfo = document.getElementById('userInfo');
    const userName = document.getElementById('userName');
    const userId = document.getElementById('userId');
    const disconnectBtn = document.getElementById('disconnectButton');
    
    if (authenticated) {
        if (authStatus) authStatus.style.display = 'none';
        if (userInfo) userInfo.style.display = 'flex';
        if (disconnectBtn) disconnectBtn.style.display = 'inline-block';
        
        // Update user info with actual data
        if (authData) {
            if (userName) {
                userName.textContent = authData.account_name || authData.full_name || authData.email || authData.user_id || 'User';
            }
            if (userId) {
                userId.textContent = authData.user_id || authData.broker_id || '-';
            }
        }
    } else {
        if (authStatus) authStatus.style.display = 'block';
        if (userInfo) userInfo.style.display = 'none';
        if (disconnectBtn) disconnectBtn.style.display = 'none';
        if (userName) userName.textContent = 'Loading...';
        if (userId) userId.textContent = '-';
    }
}

// Check connectivity
async function checkConnectivity() {
    try {
        const response = await fetch('/api/connectivity', {
            credentials: 'include'
        });
        if (!response.ok) return;
        
        const data = await response.json();
        const statusIndicator = document.getElementById('statusIndicator');
        const statusText = document.getElementById('statusText');
        const heartIcon = document.getElementById('heartIcon');
        
        if (data.connected && data.api_connected) {
            if (heartIcon) {
                heartIcon.classList.remove('disconnected');
                heartIcon.classList.add('connected');
            }
            if (statusText) {
                statusText.textContent = data.status_message || 'Connected';
            }
        } else {
            if (heartIcon) {
                heartIcon.classList.remove('connected');
                heartIcon.classList.add('disconnected');
            }
            if (statusText) {
                statusText.textContent = data.status_message || 'Not Connected';
            }
        }
    } catch (error) {
        console.error('Error checking connectivity:', error);
    }
}

// Update all dashboard data
async function updateAll() {
    if (!isAuthenticated) {
        stopUpdates();
        return;
    }
    
    try {
        await Promise.all([
            updateStatus(),
            updateTrades(),
            updateCumulativePnl()
        ]);
    } catch (error) {
        console.error('Error updating dashboard:', error);
        // If authentication error, stop updates
        if (error.message && (error.message.includes('401') || error.message.includes('Unauthorized'))) {
            isAuthenticated = false;
            updateAuthUI(false);
            stopUpdates();
        }
    }
}

// Update status
async function updateStatus() {
    // Don't update if not authenticated
    if (!isAuthenticated) {
        return;
    }
    
    try {
        const response = await fetch('/api/dashboard/status', {
            credentials: 'include'
        });
        if (!response.ok) {
            if (response.status === 401) {
                // Not authenticated, stop updates
                isAuthenticated = false;
                updateAuthUI(false);
                stopUpdates();
            }
            return;
        }
        
        const data = await response.json();
        if (data.daily_loss_used !== undefined) {
            const dailyLossUsed = document.getElementById('dailyLossUsed');
            if (dailyLossUsed) {
                dailyLossUsed.textContent = formatCurrency(data.daily_loss_used);
            }
            
            const lossProgress = document.getElementById('lossProgress');
            if (lossProgress && data.daily_loss_limit) {
                const percentage = Math.min((data.daily_loss_used / data.daily_loss_limit) * 100, 100);
                lossProgress.style.width = percentage + '%';
            }
        }
    } catch (error) {
        console.error('Error updating status:', error);
        // If it's a JSON parse error, it might be a 401 response
        if (error.message && error.message.includes('JSON')) {
            isAuthenticated = false;
            updateAuthUI(false);
            stopUpdates();
        }
    }
}

// Update trades
async function updateTrades() {
    try {
        const showAll = document.getElementById('showAllTrades')?.checked || false;
        const dateFilter = document.getElementById('tradeDateFilter')?.value || '';
        
        let url = '/api/dashboard/trade-history?';
        if (showAll) url += 'all=true&';
        if (dateFilter) url += `date=${dateFilter}`;
        
        const response = await fetch(url, {
            credentials: 'include'
        });
        if (!response.ok) return;
        
        const data = await response.json();
        if (data.success && data.trades) {
            renderTrades(data.trades);
            updateTradeSummary(data.trades);
        }
    } catch (error) {
        console.error('Error updating trades:', error);
    }
}

// Render trades table
function renderTrades(trades) {
    const tbody = document.getElementById('tradesBody');
    if (!tbody) return;
    
    if (trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">No trades found</td></tr>';
        return;
    }
    
    tbody.innerHTML = trades.map(trade => {
        const pnlColor = trade.pnl >= 0 ? 'positive' : 'negative';
        const pnlSign = trade.pnl >= 0 ? '+' : '';
        return `
            <tr>
                <td>${trade.symbol || '-'}</td>
                <td>${formatDateTime(trade.entry_time)}</td>
                <td>${formatDateTime(trade.exit_time)}</td>
                <td>${formatCurrency(trade.entry_price)}</td>
                <td>${formatCurrency(trade.exit_price)}</td>
                <td>${trade.quantity || '-'}</td>
                <td class="${pnlColor}">${pnlSign}${formatCurrency(trade.pnl)}</td>
                <td>${trade.trade_type || '-'}</td>
            </tr>
        `;
    }).join('');
}

// Update trade summary
function updateTradeSummary(trades) {
    const totalTrades = trades.length;
    const totalProfit = trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0);
    const totalLoss = trades.filter(t => t.pnl < 0).reduce((sum, t) => sum + Math.abs(t.pnl), 0);
    const netPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
    const winRate = totalTrades > 0 ? (trades.filter(t => t.pnl > 0).length / totalTrades * 100).toFixed(1) : 0;
    
    const totalTradesEl = document.getElementById('totalTrades');
    if (totalTradesEl) totalTradesEl.textContent = totalTrades;
    
    const totalProfitEl = document.getElementById('totalProfit');
    if (totalProfitEl) totalProfitEl.textContent = formatCurrency(totalProfit);
    
    const totalLossEl = document.getElementById('totalLoss');
    if (totalLossEl) totalLossEl.textContent = formatCurrency(totalLoss);
    
    const netPnlEl = document.getElementById('netPnl');
    if (netPnlEl) {
        netPnlEl.textContent = formatCurrency(netPnl);
        netPnlEl.className = netPnl >= 0 ? 'positive' : 'negative';
    }
    
    const winRateEl = document.getElementById('winRate');
    if (winRateEl) winRateEl.textContent = winRate + '%';
}

// Update cumulative P&L
async function updateCumulativePnl() {
    // Don't update if not authenticated
    if (!isAuthenticated) {
        return;
    }
    
    try {
        const response = await fetch('/api/dashboard/cumulative-pnl', {
            credentials: 'include'
        });
        if (!response.ok) {
            if (response.status === 401) {
                // Not authenticated, stop updates
                isAuthenticated = false;
                updateAuthUI(false);
                stopUpdates();
            }
            return;
        }
        
        const data = await response.json();
        if (data.success) {
            updateCumulativePnlMetrics(data);
            updateCumulativePnlChart(data);
        }
    } catch (error) {
        console.error('Error updating cumulative P&L:', error);
        // If it's a JSON parse error, it might be a 401 response
        if (error.message && error.message.includes('JSON')) {
            isAuthenticated = false;
            updateAuthUI(false);
            stopUpdates();
        }
    }
}

// Update cumulative P&L metrics
function updateCumulativePnlMetrics(data) {
    const metrics = {
        'all-time': data.all_time || 0,
        'year': data.year || 0,
        'month': data.month || 0,
        'week': data.week || 0,
        'day': data.day || 0
    };
    
    Object.keys(metrics).forEach(key => {
        const valueEl = document.getElementById(`value-${key}`);
        if (valueEl) {
            valueEl.textContent = formatCurrency(metrics[key]);
            valueEl.className = 'metric-value ' + (metrics[key] >= 0 ? 'positive' : 'negative');
        }
    });
}

// Update cumulative P&L chart
function updateCumulativePnlChart(data) {
    const canvas = document.getElementById('cumulativePnlChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    
    if (!cumulativePnlChart) {
        cumulativePnlChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['All Time', 'Year', 'Month', 'Week', 'Day'],
                datasets: [{
                    data: [
                        data.all_time || 0,
                        data.year || 0,
                        data.month || 0,
                        data.week || 0,
                        data.day || 0
                    ],
                    backgroundColor: [
                        '#22c55e',
                        '#3b82f6',
                        '#a855f7',
                        '#14b8a6',
                        '#f97316'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    } else {
        cumulativePnlChart.data.datasets[0].data = [
            data.all_time || 0,
            data.year || 0,
            data.month || 0,
            data.week || 0,
            data.day || 0
        ];
        cumulativePnlChart.update();
    }
}

// Toggle trade filter
function toggleTradeFilter() {
    updateTrades();
}

// Start updates
function startUpdates() {
    if (!isAuthenticated) return;
    
    stopUpdates();
    updateAll();
    
    updateInterval = setInterval(() => {
        if (isAuthenticated) {
            updateAll();
        } else {
            stopUpdates();
        }
    }, 10000); // Update every 10 seconds
    
    // Check connectivity every 15 seconds
    checkConnectivity();
    setInterval(checkConnectivity, 15000);
}

// Stop updates
function stopUpdates() {
    if (updateInterval) {
        clearInterval(updateInterval);
        updateInterval = null;
    }
}

// Toggle auth details
function toggleAuthDetails() {
    const widget = document.querySelector('.auth-details-widget');
    const content = document.getElementById('authDetailsContent');
    const chevron = document.getElementById('authDetailsChevron');
    
    if (widget && content && chevron) {
        const isExpanded = widget.classList.contains('expanded');
        if (isExpanded) {
            widget.classList.remove('expanded');
            content.style.display = 'none';
        } else {
            widget.classList.add('expanded');
            content.style.display = 'block';
            // Load and populate auth details when expanding
            updateAuthDetails();
        }
    }
}

// Update auth details
async function updateAuthDetails() {
    try {
        const response = await fetch('/api/auth/details', {
            credentials: 'include'
        });
        if (!response.ok) return;
        
        const data = await response.json();
        if (data.success && data.details) {
            const details = data.details;
            // Show actual values for reference (user requested to see credentials)
            document.getElementById('authApiKey').textContent = details.api_key || '-';
            document.getElementById('authApiSecret').textContent = details.api_secret || '-';
            document.getElementById('authAccessToken').textContent = details.access_token || '-';
            document.getElementById('authRequestToken').textContent = details.request_token || '-';
            document.getElementById('authEmail').textContent = details.email || '-';
            document.getElementById('authBroker').textContent = details.broker || '-';
            document.getElementById('authUserId').textContent = details.user_id || '-';
            document.getElementById('authAccountName').textContent = details.account_name || '-';
            document.getElementById('authFullName').textContent = details.full_name || '-';
        } else {
            // If no details, try to get from auth status
            const statusResponse = await fetch('/api/auth/status', {
                credentials: 'include'
            });
            if (statusResponse.ok) {
                const statusData = await statusResponse.json();
                if (statusData.authenticated) {
                    // At least show what we have from status
                    document.getElementById('authUserId').textContent = statusData.user_id || '-';
                    document.getElementById('authBroker').textContent = statusData.broker_id || '-';
                    document.getElementById('authEmail').textContent = statusData.email || '-';
                    document.getElementById('authAccountName').textContent = statusData.account_name || '-';
                    document.getElementById('authFullName').textContent = statusData.full_name || '-';
                }
            }
        }
    } catch (error) {
        console.error('Error updating auth details:', error);
    }
}

// Format currency
function formatCurrency(value) {
    if (value === null || value === undefined) return '₹0.00';
    return '₹' + parseFloat(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Format date time
function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    try {
        const date = new Date(dateStr);
        return date.toLocaleString('en-IN', { 
            year: 'numeric', 
            month: '2-digit', 
            day: '2-digit', 
            hour: '2-digit', 
            minute: '2-digit' 
        });
    } catch (e) {
        return dateStr;
    }
}

// Disconnect from Zerodha
async function disconnectZerodha() {
    if (!confirm('Are you sure you want to disconnect from Zerodha? This will clear all authentication credentials.')) {
        return;
    }
    
    try {
        const response = await fetch('/api/auth/disconnect', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Update UI - set authentication state to false
            isAuthenticated = false;
            updateAuthUI(false);
            
            // Clear auth details display
            const fields = ['authApiKey', 'authApiSecret', 'authAccessToken', 'authRequestToken', 
                          'authEmail', 'authBroker', 'authUserId', 'authAccountName', 'authFullName'];
            fields.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '-';
            });
            
            // Stop updates
            stopUpdates();
            
            // Update status indicator
            const statusIndicator = document.getElementById('statusIndicator');
            const heartIcon = document.getElementById('heartIcon');
            const statusText = document.getElementById('statusText');
            if (heartIcon) {
                heartIcon.classList.remove('connected');
                heartIcon.classList.add('disconnected');
            }
            if (statusText) {
                statusText.textContent = 'Not Connected';
            }
            
            // Show auth status button
            const authStatus = document.getElementById('authStatus');
            if (authStatus) {
                authStatus.style.display = 'block';
                authStatus.textContent = '🔒 Not Authenticated';
                authStatus.style.background = '#dc3545';
                authStatus.onclick = showAuthModal;
            }
            
            alert('Disconnected successfully. Please authenticate again to continue.');
            
            // Refresh page to reset state
            window.location.reload();
        } else {
            alert('Error disconnecting: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error disconnecting:', error);
        alert('Error disconnecting: ' + error.message);
    }
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Initialize with NOT authenticated state first
    isAuthenticated = false;
    updateAuthUI(false);
    
    initializeCumulativePnlChart();
    initializePnlCalendar();
    setupEventListeners();
    
    // Check auth status after a small delay to ensure UI is ready
    setTimeout(() => {
        checkAuthStatus();
    }, 100);
    
    // Don't check connectivity or update details until authenticated
    // These will be called by checkAuthStatus if authenticated
});

// Cumulative P&L Chart - Radial Bar Chart (Spiral-like)
let cumulativePnlCanvas = null;
let cumulativePnlCtx = null;
let cumulativePnlData = {
    allTime: 0,
    year: 0,
    month: 0,
    week: 0,
    day: 0,
    todayPnl: 0
};

// Initialize cumulative P&L chart
function initializeCumulativePnlChart() {
    const canvas = document.getElementById('cumulativePnlChart');
    if (!canvas) return;
    
    cumulativePnlCanvas = canvas;
    cumulativePnlCtx = canvas.getContext('2d');
    
    // Set canvas size based on container
    function resizeCanvas() {
        const container = canvas.parentElement;
        const size = Math.min(container.clientWidth, container.clientHeight, 480);
        const dpr = window.devicePixelRatio || 1;
        const displaySize = size;
        canvas.width = displaySize * dpr;
        canvas.height = displaySize * dpr;
        canvas.style.width = displaySize + 'px';
        canvas.style.height = displaySize + 'px';
        cumulativePnlCtx.scale(dpr, dpr);
        drawRadialBarChart();
    }
    
    // Initial resize
    resizeCanvas();
    
    // Resize on window resize
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(resizeCanvas, 100);
    });
}

function drawRadialBarChart() {
    if (!cumulativePnlCtx || !cumulativePnlCanvas) return;
    
    const ctx = cumulativePnlCtx;
    const canvas = cumulativePnlCanvas;
    const displaySize = parseInt(canvas.style.width) || 480;
    const centerX = displaySize / 2;
    const centerY = displaySize / 2;
    const maxRadius = Math.min(centerX, centerY) - 20;
    
    // Clear canvas
    ctx.clearRect(0, 0, displaySize, displaySize);
    
    // Get all values (use absolute values for proportional sizing)
    const values = {
        allTime: Math.abs(cumulativePnlData.allTime) || 0,
        year: Math.abs(cumulativePnlData.year) || 0,
        month: Math.abs(cumulativePnlData.month) || 0,
        week: Math.abs(cumulativePnlData.week) || 0,
        day: Math.abs(cumulativePnlData.day) || 0
    };
    
    const baselineValue = Math.max(values.allTime, 1);
    const maxArcPercentage = 0.92;
    const lineWidth = 12;
    const radiusSpacing = 28;
    
    // Define layers (from outer to inner)
    const layers = [
        { 
            value: cumulativePnlData.allTime,
            absValue: values.allTime,
            label: 'Cumulative Profit', 
            color: 'rgba(34, 197, 94, 0.8)', 
            borderColor: '#22c55e',
            radius: maxRadius
        },
        { 
            value: cumulativePnlData.year,
            absValue: values.year,
            label: 'Year', 
            color: 'rgba(37, 99, 235, 0.8)', 
            borderColor: '#2563eb',
            radius: maxRadius - radiusSpacing
        },
        { 
            value: cumulativePnlData.month,
            absValue: values.month,
            label: 'Month', 
            color: 'rgba(139, 92, 246, 0.8)', 
            borderColor: '#8b5cf6',
            radius: maxRadius - (radiusSpacing * 2)
        },
        { 
            value: cumulativePnlData.week,
            absValue: values.week,
            label: 'Week', 
            color: 'rgba(20, 184, 166, 0.8)', 
            borderColor: '#14b8a6',
            radius: maxRadius - (radiusSpacing * 3)
        },
        { 
            value: cumulativePnlData.day,
            absValue: values.day,
            label: 'Day', 
            color: 'rgba(249, 115, 22, 0.8)', 
            borderColor: '#f97316',
            radius: maxRadius - (radiusSpacing * 4)
        }
    ];
    
    const startAngle = -Math.PI / 2; // Start from top
    const fullCircle = Math.PI * 2;
    
    // Draw each layer as an arc
    layers.forEach((layer, index) => {
        if (layer.absValue > 0 && baselineValue > 0) {
            const percentageOfCumulative = layer.absValue / baselineValue;
            const arcPercentage = index === 0 
                ? maxArcPercentage
                : Math.min(percentageOfCumulative * maxArcPercentage, maxArcPercentage);
            const arcLength = arcPercentage * fullCircle;
            const endAngle = startAngle + arcLength;
            
            const isPositive = layer.value >= 0;
            const strokeColor = isPositive ? layer.borderColor : 'rgba(239, 68, 68, 1)';
            
            ctx.beginPath();
            ctx.arc(centerX, centerY, layer.radius, startAngle, endAngle);
            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = lineWidth;
            ctx.lineCap = 'round';
            ctx.stroke();
        } else {
            // Show a green dot at the starting point for zero values
            const dotX = centerX + layer.radius * Math.cos(startAngle);
            const dotY = centerY + layer.radius * Math.sin(startAngle);
            ctx.beginPath();
            ctx.arc(dotX, dotY, 4, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(16, 185, 129, 1)';
            ctx.fill();
        }
    });
    
    // Draw today's P&L in the center
    const todayPnl = cumulativePnlData.todayPnl || cumulativePnlData.day || 0;
    const todayPnlFormatted = formatCurrencyCompact(todayPnl);
    const isProfit = todayPnl >= 0;
    
    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = 'bold 24px sans-serif';
    ctx.fillStyle = isProfit ? '#22c55e' : '#f97316';
    ctx.fillText(todayPnlFormatted, centerX, centerY);
    ctx.restore();
}

// Format currency for chart display (compact format)
function formatCurrencyCompact(value) {
    if (value >= 100000) {
        return '₹' + (value / 100000).toFixed(2) + 'L';
    } else if (value >= 1000) {
        return '₹' + (value / 1000).toFixed(2) + 'k';
    } else {
        return '₹' + value.toFixed(2);
    }
}

// Update cumulative P&L from API
async function updateCumulativePnl() {
    // Don't update if not authenticated
    if (!isAuthenticated) {
        return;
    }
    
    try {
        const response = await fetch('/api/dashboard/cumulative-pnl', {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'success') {
                cumulativePnlData = {
                    allTime: data.all_time || 0,
                    year: data.year || 0,
                    month: data.month || 0,
                    week: data.week || 0,
                    day: data.day || 0,
                    todayPnl: data.day || 0
                };
                
                // Update metric displays
                updateMetricDisplay('value-all-time', cumulativePnlData.allTime);
                updateMetricDisplay('value-year', cumulativePnlData.year);
                updateMetricDisplay('value-month', cumulativePnlData.month);
                updateMetricDisplay('value-week', cumulativePnlData.week);
                updateMetricDisplay('value-day', cumulativePnlData.day);
                
                // Redraw chart
                drawRadialBarChart();
            }
        } else if (response.status === 401) {
            // Not authenticated, stop updates
            isAuthenticated = false;
            updateAuthUI(false);
            stopUpdates();
        }
    } catch (error) {
        console.error('Error updating cumulative P&L:', error);
        // If it's a JSON parse error, it might be a 401 response
        if (error.message && (error.message.includes('JSON') || error.message.includes('401'))) {
            isAuthenticated = false;
            updateAuthUI(false);
            stopUpdates();
        }
    }
}

function updateMetricDisplay(id, value) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = formatCurrency(value);
        element.className = 'metric-value ' + (value >= 0 ? 'positive' : 'negative');
    }
}

// Initialize P&L Calendar Heatmap
let pnlCalendarData = {};
let pnlFilters = {
    segment: 'all',
    type: 'combined',
    symbol: '',
    dateRange: null
};
let dateRangePickerState = {
    fromDate: null,
    toDate: null,
    fromMonth: null,
    toMonth: null
};

function initializePnlCalendar() {
    const calendarContainer = document.getElementById('pnlCalendarHeatmap');
    if (!calendarContainer) return;
    
    // Set default date range (last 6 months)
    const endDate = new Date();
    const startDate = new Date();
    startDate.setMonth(startDate.getMonth() - 6);
    
    dateRangePickerState.fromDate = startDate;
    dateRangePickerState.toDate = endDate;
    dateRangePickerState.fromMonth = new Date(startDate);
    dateRangePickerState.toMonth = new Date(endDate);
    
    updateDateRangeDisplay();
    
    // Setup date range picker button
    const dateRangeBtn = document.getElementById('pnlDateRangeBtn');
    if (dateRangeBtn) {
        dateRangeBtn.addEventListener('click', () => {
            openDateRangePicker();
        });
    }
    
    // Setup filter handlers
    const applyBtn = document.getElementById('applyPnlFilters');
    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            updatePnlFilters();
            loadPnlCalendarData();
        });
    }
    
    const pnlType = document.getElementById('pnlType');
    if (pnlType) {
        pnlType.addEventListener('change', () => {
            updatePnlFilters();
            loadPnlCalendarData();
        });
    }
    
    // Load initial data
    loadPnlCalendarData();
}

function updatePnlFilters() {
    const segmentEl = document.getElementById('pnlSegment');
    const symbolEl = document.getElementById('pnlSymbol');
    const typeEl = document.getElementById('pnlType');
    
    if (segmentEl) {
        pnlFilters.segment = segmentEl.value;
    }
    if (symbolEl) {
        pnlFilters.symbol = symbolEl.value.trim().toUpperCase();
    }
    if (typeEl) {
        pnlFilters.type = typeEl.value;
    }
}

function updateDateRangeDisplay() {
    const display = document.getElementById('pnlDateRangeDisplay');
    const textDisplay = document.getElementById('pnlDateRangeText');
    const hiddenInput = document.getElementById('pnlDateRange');
    
    if (dateRangePickerState.fromDate && dateRangePickerState.toDate) {
        const fromStr = formatDateForInput(dateRangePickerState.fromDate);
        const toStr = formatDateForInput(dateRangePickerState.toDate);
        const displayText = `${fromStr} ~ ${toStr}`;
        
        if (display) display.textContent = displayText;
        if (textDisplay) textDisplay.textContent = `${fromStr} to ${toStr}`;
        if (hiddenInput) hiddenInput.value = displayText;
    } else {
        if (display) display.textContent = 'Select Date Range';
        if (textDisplay) textDisplay.textContent = 'Select Date Range';
        if (hiddenInput) hiddenInput.value = '';
    }
}

function openDateRangePicker() {
    const modal = document.getElementById('dateRangePickerModal');
    if (modal) {
        modal.style.display = 'flex';
        renderCalendars();
    }
}

function closeDateRangePicker() {
    const modal = document.getElementById('dateRangePickerModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function setQuickDateRange(option) {
    const today = new Date();
    let fromDate, toDate;
    
    switch(option) {
        case 'last7':
            fromDate = new Date(today);
            fromDate.setDate(today.getDate() - 6);
            toDate = new Date(today);
            break;
        case 'last30':
            fromDate = new Date(today);
            fromDate.setDate(today.getDate() - 29);
            toDate = new Date(today);
            break;
        case 'prevFY':
            const currentYear = today.getFullYear();
            const currentMonth = today.getMonth();
            if (currentMonth >= 3) {
                fromDate = new Date(currentYear - 1, 3, 1);
                toDate = new Date(currentYear, 2, 31);
            } else {
                fromDate = new Date(currentYear - 2, 3, 1);
                toDate = new Date(currentYear - 1, 2, 31);
            }
            break;
        case 'currentFY':
            const currYear = today.getFullYear();
            const currMonth = today.getMonth();
            if (currMonth >= 3) {
                fromDate = new Date(currYear, 3, 1);
                toDate = new Date(today);
            } else {
                fromDate = new Date(currYear - 1, 3, 1);
                toDate = new Date(today);
            }
            break;
    }
    
    dateRangePickerState.fromDate = fromDate;
    dateRangePickerState.toDate = toDate;
    dateRangePickerState.fromMonth = new Date(fromDate);
    dateRangePickerState.toMonth = new Date(toDate);
    
    updateDateRangeDisplay();
    renderCalendars();
}

function changeMonth(calendar, months) {
    if (calendar === 'from') {
        dateRangePickerState.fromMonth.setMonth(dateRangePickerState.fromMonth.getMonth() + months);
    } else {
        dateRangePickerState.toMonth.setMonth(dateRangePickerState.toMonth.getMonth() + months);
    }
    renderCalendars();
}

function renderCalendars() {
    renderCalendar('from', dateRangePickerState.fromMonth, dateRangePickerState.fromDate);
    renderCalendar('to', dateRangePickerState.toMonth, dateRangePickerState.toDate);
}

function renderCalendar(type, month, selectedDate) {
    const container = document.getElementById(type + 'Calendar');
    if (!container) return;
    
    const year = month.getFullYear();
    const monthIndex = month.getMonth();
    
    // Update month display
    const monthDisplay = document.getElementById(type + 'MonthDisplay');
    if (monthDisplay) {
        monthDisplay.textContent = new Date(year, monthIndex, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    }
    
    // Get first and last day of month
    const firstDay = new Date(year, monthIndex, 1);
    const lastDay = new Date(year, monthIndex + 1, 0);
    
    let html = '<div class="calendar-weekdays">';
    const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    weekdays.forEach(day => {
        html += `<div class="calendar-weekday">${day}</div>`;
    });
    html += '</div><div class="calendar-days">';
    
    // Previous month days
    const startWeekday = firstDay.getDay();
    const prevMonth = new Date(year, monthIndex - 1, 0);
    for (let i = startWeekday - 1; i >= 0; i--) {
        const day = prevMonth.getDate() - i;
        html += `<div class="calendar-day other-month" onclick="selectDate('${type}', ${year}, ${monthIndex - 1}, ${day})">${day}</div>`;
    }
    
    // Current month days
    for (let day = 1; day <= lastDay.getDate(); day++) {
        const date = new Date(year, monthIndex, day);
        let classes = 'calendar-day';
        if (selectedDate && date.getTime() === selectedDate.getTime()) {
            classes += ' selected';
        }
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const compareDate = new Date(date);
        compareDate.setHours(0, 0, 0, 0);
        if (compareDate.getTime() === today.getTime()) {
            classes += ' today';
        }
        html += `<div class="${classes}" onclick="selectDate('${type}', ${year}, ${monthIndex}, ${day})">${day}</div>`;
    }
    
    // Next month days
    const endWeekday = lastDay.getDay();
    const daysToAdd = 6 - endWeekday;
    for (let day = 1; day <= daysToAdd; day++) {
        html += `<div class="calendar-day other-month" onclick="selectDate('${type}', ${year}, ${monthIndex + 1}, ${day})">${day}</div>`;
    }
    
    html += '</div>';
    container.innerHTML = html;
}

function selectDate(type, year, month, day) {
    const date = new Date(year, month, day);
    if (type === 'from') {
        dateRangePickerState.fromDate = date;
        dateRangePickerState.fromMonth = new Date(date);
    } else {
        dateRangePickerState.toDate = date;
        dateRangePickerState.toMonth = new Date(date);
    }
    renderCalendars();
}

function applyDateRange() {
    updateDateRangeDisplay();
    closeDateRangePicker();
    loadPnlCalendarData();
}

function updatePnlFilters() {
    const segmentEl = document.getElementById('pnlSegment');
    const symbolEl = document.getElementById('pnlSymbol');
    const typeEl = document.getElementById('pnlType');
    
    if (segmentEl) {
        pnlFilters.segment = segmentEl.value;
    }
    if (symbolEl) {
        pnlFilters.symbol = symbolEl.value.trim().toUpperCase();
    }
    if (typeEl) {
        pnlFilters.type = typeEl.value;
    }
}

function updateDateRangeDisplay() {
    const display = document.getElementById('pnlDateRangeDisplay');
    const textDisplay = document.getElementById('pnlDateRangeText');
    const hiddenInput = document.getElementById('pnlDateRange');
    
    if (dateRangePickerState.fromDate && dateRangePickerState.toDate) {
        const fromStr = formatDateForInput(dateRangePickerState.fromDate);
        const toStr = formatDateForInput(dateRangePickerState.toDate);
        const displayText = `${fromStr} ~ ${toStr}`;
        
        if (display) display.textContent = displayText;
        if (textDisplay) textDisplay.textContent = `${fromStr} to ${toStr}`;
        if (hiddenInput) hiddenInput.value = displayText;
    } else {
        if (display) display.textContent = 'Select Date Range';
        if (textDisplay) textDisplay.textContent = 'Select Date Range';
        if (hiddenInput) hiddenInput.value = '';
    }
}

function openDateRangePicker() {
    const modal = document.getElementById('dateRangePickerModal');
    if (modal) {
        modal.style.display = 'flex';
        renderCalendars();
    }
}

function closeDateRangePicker() {
    const modal = document.getElementById('dateRangePickerModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function setQuickDateRange(option) {
    const today = new Date();
    let fromDate, toDate;
    
    switch(option) {
        case 'last7':
            fromDate = new Date(today);
            fromDate.setDate(today.getDate() - 6);
            toDate = new Date(today);
            break;
        case 'last30':
            fromDate = new Date(today);
            fromDate.setDate(today.getDate() - 29);
            toDate = new Date(today);
            break;
        case 'prevFY':
            const currentYear = today.getFullYear();
            const currentMonth = today.getMonth();
            if (currentMonth >= 3) {
                fromDate = new Date(currentYear - 1, 3, 1);
                toDate = new Date(currentYear, 2, 31);
            } else {
                fromDate = new Date(currentYear - 2, 3, 1);
                toDate = new Date(currentYear - 1, 2, 31);
            }
            break;
        case 'currentFY':
            const currYear = today.getFullYear();
            const currMonth = today.getMonth();
            if (currMonth >= 3) {
                fromDate = new Date(currYear, 3, 1);
                toDate = new Date(today);
            } else {
                fromDate = new Date(currYear - 1, 3, 1);
                toDate = new Date(today);
            }
            break;
    }
    
    dateRangePickerState.fromDate = fromDate;
    dateRangePickerState.toDate = toDate;
    dateRangePickerState.fromMonth = new Date(fromDate);
    dateRangePickerState.toMonth = new Date(toDate);
    
    updateDateRangeDisplay();
    renderCalendars();
}

function changeMonth(calendar, months) {
    if (calendar === 'from') {
        dateRangePickerState.fromMonth.setMonth(dateRangePickerState.fromMonth.getMonth() + months);
    } else {
        dateRangePickerState.toMonth.setMonth(dateRangePickerState.toMonth.getMonth() + months);
    }
    renderCalendars();
}

function renderCalendars() {
    renderCalendar('from', dateRangePickerState.fromMonth, dateRangePickerState.fromDate);
    renderCalendar('to', dateRangePickerState.toMonth, dateRangePickerState.toDate);
}

function renderCalendar(type, month, selectedDate) {
    const container = document.getElementById(type + 'Calendar');
    if (!container) return;
    
    const year = month.getFullYear();
    const monthIndex = month.getMonth();
    
    // Update month display
    const monthDisplay = document.getElementById(type + 'MonthDisplay');
    if (monthDisplay) {
        monthDisplay.textContent = new Date(year, monthIndex, 1).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    }
    
    // Get first and last day of month
    const firstDay = new Date(year, monthIndex, 1);
    const lastDay = new Date(year, monthIndex + 1, 0);
    
    let html = '<div class="calendar-weekdays">';
    const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    weekdays.forEach(day => {
        html += `<div class="calendar-weekday">${day}</div>`;
    });
    html += '</div><div class="calendar-days">';
    
    // Previous month days
    const startWeekday = firstDay.getDay();
    const prevMonth = new Date(year, monthIndex - 1, 0);
    for (let i = startWeekday - 1; i >= 0; i--) {
        const day = prevMonth.getDate() - i;
        html += `<div class="calendar-day other-month" onclick="selectDate('${type}', ${year}, ${monthIndex - 1}, ${day})">${day}</div>`;
    }
    
    // Current month days
    for (let day = 1; day <= lastDay.getDate(); day++) {
        const date = new Date(year, monthIndex, day);
        let classes = 'calendar-day';
        if (selectedDate) {
            const selected = new Date(selectedDate);
            selected.setHours(0, 0, 0, 0);
            const compareDate = new Date(date);
            compareDate.setHours(0, 0, 0, 0);
            if (compareDate.getTime() === selected.getTime()) {
                classes += ' selected';
            }
        }
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const compareDate = new Date(date);
        compareDate.setHours(0, 0, 0, 0);
        if (compareDate.getTime() === today.getTime()) {
            classes += ' today';
        }
        html += `<div class="${classes}" onclick="selectDate('${type}', ${year}, ${monthIndex}, ${day})">${day}</div>`;
    }
    
    // Next month days
    const endWeekday = lastDay.getDay();
    const daysToAdd = 6 - endWeekday;
    for (let day = 1; day <= daysToAdd; day++) {
        html += `<div class="calendar-day other-month" onclick="selectDate('${type}', ${year}, ${monthIndex + 1}, ${day})">${day}</div>`;
    }
    
    html += '</div>';
    container.innerHTML = html;
}

function selectDate(type, year, month, day) {
    const date = new Date(year, month, day);
    if (type === 'from') {
        dateRangePickerState.fromDate = date;
        dateRangePickerState.fromMonth = new Date(date);
    } else {
        dateRangePickerState.toDate = date;
        dateRangePickerState.toMonth = new Date(date);
    }
    renderCalendars();
}

function applyDateRange() {
    updateDateRangeDisplay();
    closeDateRangePicker();
    loadPnlCalendarData();
}

async function loadPnlCalendarData() {
    try {
        if (!dateRangePickerState.fromDate || !dateRangePickerState.toDate) {
            return;
        }
        
        const startStr = formatDateForInput(dateRangePickerState.fromDate);
        const endStr = formatDateForInput(dateRangePickerState.toDate);
        
        // Update date range text
        const dateRangeText = document.getElementById('pnlDateRangeText');
        if (dateRangeText) {
            dateRangeText.textContent = `${startStr} to ${endStr}`;
        }
        
        // Try to fetch data from API (if available)
        try {
            const response = await fetch(`/api/dashboard/trade-history?all=true`, {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'success' && data.trades) {
                    // Process trades into daily P&L
                    pnlCalendarData = {};
                    let totalRealisedPnl = 0;
                    let totalPaperPnl = 0;
                    let totalLivePnl = 0;
                    let totalTrades = 0;
                    
                    data.trades.forEach(trade => {
                        const tradeDate = trade.exit_time ? trade.exit_time.split('T')[0] : trade.exitTime ? trade.exitTime.split('T')[0] : null;
                        if (tradeDate) {
                            if (!pnlCalendarData[tradeDate]) {
                                pnlCalendarData[tradeDate] = {
                                    paper_pnl: 0,
                                    live_pnl: 0,
                                    paper_trades: 0,
                                    live_trades: 0
                                };
                            }
                            const pnl = parseFloat(trade.pnl || trade.realised_pnl || 0);
                            pnlCalendarData[tradeDate].live_pnl += pnl;
                            pnlCalendarData[tradeDate].live_trades += 1;
                            totalRealisedPnl += pnl;
                            totalLivePnl += pnl;
                            totalTrades += 1;
                        }
                    });
                    
                    // Update summary
                    updateRealisedPnlSummary(totalRealisedPnl, totalPaperPnl, totalLivePnl, totalTrades);
                }
            }
        } catch (apiError) {
            console.warn('Could not fetch P&L calendar data from API:', apiError);
        }
        
        // Always render calendar
        renderPnlCalendar(dateRangePickerState.fromDate, dateRangePickerState.toDate);
    } catch (error) {
        console.error('Error loading P&L calendar data:', error);
        pnlCalendarData = {};
        updateRealisedPnlSummary(0, 0, 0, 0);
        if (dateRangePickerState.fromDate && dateRangePickerState.toDate) {
            renderPnlCalendar(dateRangePickerState.fromDate, dateRangePickerState.toDate);
        }
    }
}

function updateRealisedPnlSummary(totalRealisedPnl, totalPaperPnl, totalLivePnl, totalTrades) {
    const realisedPnlEl = document.getElementById('realisedPnlValue');
    const paperPnlEl = document.getElementById('paperPnlValue');
    const livePnlEl = document.getElementById('livePnlValue');
    const totalTradesEl = document.getElementById('totalTradesCount');
    
    if (realisedPnlEl) {
        realisedPnlEl.textContent = formatCurrency(totalRealisedPnl);
        realisedPnlEl.style.color = totalRealisedPnl >= 0 ? '#10b981' : '#ef4444';
    }
    
    if (paperPnlEl) {
        paperPnlEl.textContent = formatCurrency(totalPaperPnl);
        paperPnlEl.style.color = totalPaperPnl >= 0 ? '#10b981' : '#ef4444';
    }
    
    if (livePnlEl) {
        livePnlEl.textContent = formatCurrency(totalLivePnl);
        livePnlEl.style.color = totalLivePnl >= 0 ? '#10b981' : '#ef4444';
    }
    
    if (totalTradesEl) {
        totalTradesEl.textContent = totalTrades;
    }
}

function formatDateForInput(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function renderPnlCalendar(startDate, endDate) {
    const container = document.getElementById('pnlCalendarHeatmap');
    if (!container) return;
    
    container.innerHTML = '';
    
    // Group days by month
    const months = {};
    const current = new Date(startDate);
    
    while (current <= endDate) {
        const year = current.getFullYear();
        const month = current.getMonth();
        const key = `${year}-${month}`;
        
        if (!months[key]) {
            months[key] = {
                year,
                month,
                days: []
            };
        }
        
        months[key].days.push(new Date(current));
        current.setDate(current.getDate() + 1);
    }
    
    // Render each month in chronological order
    const sortedMonthKeys = Object.keys(months).sort((a, b) => {
        const [yearA, monthA] = a.split('-').map(Number);
        const [yearB, monthB] = b.split('-').map(Number);
        if (yearA !== yearB) return yearA - yearB;
        return monthA - monthB;
    });
    
    sortedMonthKeys.forEach(key => {
        const monthData = months[key];
        const monthColumn = document.createElement('div');
        monthColumn.className = 'pnl-month-column';
        
        // Month header
        const monthHeader = document.createElement('div');
        monthHeader.className = 'pnl-month-header';
        monthHeader.textContent = new Date(monthData.year, monthData.month, 1)
            .toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
        monthColumn.appendChild(monthHeader);
        
        // Week rows
        const weekRows = [];
        let currentWeek = [];
        
        // Add empty cells for days before month start
        const firstDay = monthData.days[0];
        const firstDayOfWeek = firstDay.getDay(); // 0 = Sunday, 6 = Saturday
        for (let i = 0; i < firstDayOfWeek; i++) {
            currentWeek.push(null);
        }
        
        // Add days
        monthData.days.forEach(day => {
            if (currentWeek.length === 7) {
                weekRows.push(currentWeek);
                currentWeek = [];
            }
            currentWeek.push(day);
        });
        
        // Fill remaining week
        while (currentWeek.length < 7) {
            currentWeek.push(null);
        }
        weekRows.push(currentWeek);
        
        // Render week rows
        weekRows.forEach(week => {
            const weekRow = document.createElement('div');
            weekRow.className = 'pnl-week-row';
            
            week.forEach(day => {
                const dayCell = document.createElement('div');
                dayCell.className = 'pnl-day-cell';
                
                if (day) {
                    const dateStr = formatDateForInput(day);
                    const dayData = pnlCalendarData[dateStr];
                    
                    if (dayData) {
                        const pnlType = pnlFilters.type || 'combined';
                        let pnl = 0;
                        
                        if (pnlType === 'combined') {
                            pnl = parseFloat(dayData.paper_pnl || 0) + parseFloat(dayData.live_pnl || 0);
                        } else if (pnlType === 'paper') {
                            pnl = parseFloat(dayData.paper_pnl || 0);
                        } else if (pnlType === 'live') {
                            pnl = parseFloat(dayData.live_pnl || 0);
                        } else {
                            pnl = parseFloat(dayData.pnl || dayData.realised_pnl || 0);
                        }
                        
                        // Determine color based on P&L amount
                        if (pnl > 0) {
                            if (pnl < 1000) {
                                dayCell.className += ' profit-small';
                            } else if (pnl < 5000) {
                                dayCell.className += ' profit-medium';
                            } else {
                                dayCell.className += ' profit-large';
                            }
                        } else if (pnl < 0) {
                            if (pnl > -1000) {
                                dayCell.className += ' loss-small';
                            } else if (pnl > -5000) {
                                dayCell.className += ' loss-medium';
                            } else {
                                dayCell.className += ' loss-large';
                            }
                        } else {
                            dayCell.className += ' no-data';
                        }
                        
                        const formattedPnl = formatCurrency(pnl);
                        dayCell.title = `${dateStr}: ${formattedPnl}`;
                        dayCell.setAttribute('data-pnl', pnl);
                        dayCell.setAttribute('data-date', dateStr);
                    } else {
                        dayCell.className += ' no-data';
                        dayCell.title = dateStr + '\nNo data';
                    }
                } else {
                    dayCell.className += ' no-data';
                    dayCell.style.visibility = 'hidden';
                }
                
                weekRow.appendChild(dayCell);
            });
            
            monthColumn.appendChild(weekRow);
        });
        
        container.appendChild(monthColumn);
    });
}

// Setup event listeners
function setupEventListeners() {
    const tradeDateFilter = document.getElementById('tradeDateFilter');
    if (tradeDateFilter) {
        tradeDateFilter.value = new Date().toISOString().split('T')[0];
        tradeDateFilter.addEventListener('change', updateTrades);
    }
    
    const showAllTrades = document.getElementById('showAllTrades');
    if (showAllTrades) {
        showAllTrades.addEventListener('change', toggleTradeFilter);
    }
}

// Helper function to safely parse JSON responses
async function safeJsonResponse(response) {
    // Handle 401 Unauthorized
    if (response.status === 401) {
        isAuthenticated = false;
        updateAuthUI(false);
        stopUpdates();
        const text = await response.text();
        try {
            return JSON.parse(text);
        } catch {
            throw new Error('Unauthorized: Please authenticate to continue');
        }
    }
    
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
        const text = await response.text();
        throw new Error(`Server returned ${response.status} ${response.statusText}. Expected JSON but got ${contentType || 'unknown'}`);
    }
    
    try {
        return await response.json();
    } catch (error) {
        // If JSON parsing fails, it might be an error response
        const text = await response.text();
        console.error('Failed to parse JSON response:', text);
        throw new Error(`Failed to parse response: ${error.message}`);
    }
}
