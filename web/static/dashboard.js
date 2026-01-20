/**
 * Dashboard JavaScript for Polymarket Strategy Tester
 */

let ws = null;
let reconnectAttempts = 0;
let engineStartTime = null;
let runtimeInterval = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    fetchInitialData();
});

// WebSocket connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        reconnectAttempts = 0;
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateDashboard(data);
    };

    ws.onclose = () => {
        console.log('WebSocket closed, reconnecting...');
        setTimeout(connectWebSocket, Math.min(1000 * Math.pow(2, reconnectAttempts++), 30000));
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

// Fetch initial data
async function fetchInitialData() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateDashboard(data);
    } catch (error) {
        console.error('Error fetching initial data:', error);
    }
}

// Update entire dashboard
function updateDashboard(data) {
    updateEngineStatus(data.engine);
    updateMarkets(data.markets);
    updatePrices(data.prices);
    updateMetrics(data.metrics);
    updateOrders(data.orders || []);
    updateTrades(data.recent_trades || []);
}

// Update engine status
function updateEngineStatus(engine) {
    const badge = document.getElementById('status-badge');

    if (engine.is_running) {
        badge.textContent = 'RUNNING';
        badge.className = 'status-badge status-running';

        // Handle runtime
        if (engine.start_time) {
            if (!engineStartTime || engineStartTime !== engine.start_time) {
                engineStartTime = engine.start_time;
                if (runtimeInterval) clearInterval(runtimeInterval);
                runtimeInterval = setInterval(updateRuntime, 1000);
                updateRuntime();
            }
        }
    } else {
        badge.textContent = 'STOPPED';
        badge.className = 'status-badge status-stopped';

        // Stop runtime
        if (runtimeInterval) {
            clearInterval(runtimeInterval);
            runtimeInterval = null;
            engineStartTime = null;
            const runtimeEl = document.getElementById('runtime');
            if (runtimeEl) runtimeEl.textContent = '00:00:00';
        }
    }

    if (engine.config) {
        document.getElementById('threshold-undervalued').textContent = `$${engine.config.undervalued_threshold.toFixed(2)}`;
        document.getElementById('threshold-momentum').textContent = `$${engine.config.momentum_threshold.toFixed(2)}`;
        document.getElementById('order-size').textContent = `${engine.config.order_size} shares`;
    }
}

function updateRuntime() {
    if (!engineStartTime) return;
    const now = Date.now() / 1000;
    const diff = Math.floor(now - engineStartTime);

    if (diff < 0) return;

    const hours = Math.floor(diff / 3600);
    const minutes = Math.floor((diff % 3600) / 60);
    const seconds = diff % 60;

    const runtimeEl = document.getElementById('runtime');
    if (runtimeEl) {
        runtimeEl.textContent =
            `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }
}

// Update market info
function updateMarkets(markets) {
    if (!markets) return;

    const t1 = markets.t1_market;
    if (t1) {
        document.getElementById('market-slug').textContent = t1.slug || '--';

        const countdown = t1.countdown_to_active || 0;
        const minutes = Math.floor(countdown / 60);
        const seconds = countdown % 60;
        document.getElementById('countdown').textContent =
            `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }
}

// Update prices
function updatePrices(prices) {
    if (!prices) {
        document.getElementById('up-price').textContent = '$--';
        document.getElementById('down-price').textContent = '$--';
        document.getElementById('sum-price').textContent = '$--';
        return;
    }

    document.getElementById('up-price').textContent = prices.up ? `$${prices.up.toFixed(2)}` : '$--';
    document.getElementById('down-price').textContent = prices.down ? `$${prices.down.toFixed(2)}` : '$--';
    document.getElementById('sum-price').textContent = prices.sum ? `$${prices.sum.toFixed(2)}` : '$--';
}

// Update metrics for both strategies
function updateMetrics(metrics) {
    if (!metrics) return;

    // Undervalued strategy
    const u = metrics.undervalued;
    if (u) {
        document.getElementById('undervalued-trades').textContent = u.total_trades;
        document.getElementById('undervalued-winrate').textContent = `${u.win_rate}%`;

        const pnlEl = document.getElementById('undervalued-pnl');
        pnlEl.textContent = `$${u.total_pnl.toFixed(2)}`;
        pnlEl.className = 'metric-value ' + (u.total_pnl >= 0 ? 'pnl-positive' : 'pnl-negative');

        document.getElementById('undervalued-roi').textContent = `${u.roi}%`;
    }

    // Momentum strategy
    const m = metrics.momentum;
    if (m) {
        document.getElementById('momentum-trades').textContent = m.total_trades;
        document.getElementById('momentum-winrate').textContent = `${m.win_rate}%`;

        const pnlEl = document.getElementById('momentum-pnl');
        pnlEl.textContent = `$${m.total_pnl.toFixed(2)}`;
        pnlEl.className = 'metric-value ' + (m.total_pnl >= 0 ? 'pnl-positive' : 'pnl-negative');

        document.getElementById('momentum-roi').textContent = `${m.roi}%`;
    }
}

// Update orders table
function updateOrders(orders) {
    const tbody = document.getElementById('orders-body');
    if (!tbody) return;

    if (!orders || orders.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="empty-state">No open orders.</td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = orders.map(order => {
        const statusClass = order.status === 'filled' ? 'result-win' :
            order.status === 'open' ? 'result-pending' : 'result-loss';
        const createdTime = order.created_at ? new Date(order.created_at * 1000).toLocaleTimeString() : '--';
        const marketShort = order.market_slug ? order.market_slug.slice(-10) : '--';
        const filledPct = order.size > 0 ? Math.round((order.filled_size / order.size) * 100) : 0;

        return `
            <tr>
                <td>${order.strategy}</td>
                <td title="${order.market_slug}">${marketShort}</td>
                <td>${order.outcome}</td>
                <td>$${order.price.toFixed(2)}</td>
                <td>${order.filled_size}/${order.size} (${filledPct}%)</td>
                <td class="${statusClass}">${order.status.toUpperCase()}</td>
                <td>${createdTime}</td>
            </tr>
        `;
    }).join('');
}

function updateTrades(trades) {
    const tbody = document.getElementById('trades-body');

    if (!trades || trades.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="empty-state">No trades yet. Start the engine to begin testing.</td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = trades.map(trade => {
        const resultClass = trade.result === 'win' ? 'result-win' :
            trade.result === 'loss' ? 'result-loss' : 'result-pending';
        const pnlClass = trade.pnl >= 0 ? 'pnl-positive' : 'pnl-negative';

        // Format fill timestamp
        const fillTime = trade.entry_time ? new Date(trade.entry_time * 1000).toLocaleTimeString() : '--';

        // Show filled/size (for partial fills)
        const filledInfo = trade.filled_size !== undefined
            ? `${trade.filled_size}/${trade.size}`
            : `${trade.size}`;

        // Market short slug
        const marketShort = trade.market_slug ? trade.market_slug.slice(-10) : '--';

        return `
            <tr>
                <td>${trade.strategy}</td>
                <td title="${trade.market_slug}">${marketShort}</td>
                <td>${trade.outcome}</td>
                <td>$${trade.entry_price.toFixed(2)}</td>
                <td>${filledInfo}</td>
                <td>${fillTime}</td>
                <td class="${resultClass}">${trade.result.toUpperCase()}</td>
                <td class="${pnlClass}">$${trade.pnl.toFixed(2)}</td>
            </tr>
        `;
    }).join('');
}

// Start engine
async function startEngine() {
    try {
        const response = await fetch('/api/start', { method: 'POST' });
        const data = await response.json();
        console.log('Start response:', data);
    } catch (error) {
        console.error('Error starting engine:', error);
    }
}

// Stop engine
async function stopEngine() {
    try {
        const response = await fetch('/api/stop', { method: 'POST' });
        const data = await response.json();
        console.log('Stop response:', data);
    } catch (error) {
        console.error('Error stopping engine:', error);
    }
}
