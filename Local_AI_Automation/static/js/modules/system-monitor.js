/**
 * System Monitor Module
 * Real-time CPU, Memory, GPU, and Disk monitoring with Chart.js
 */
export default class SystemMonitorModule {
    constructor({ container, eventBus, apiClient }) {
        this.container = container;
        this.eventBus = eventBus;
        this.api = apiClient;
        this.charts = {};
        this.historyData = {
            cpu: [],
            memory: [],
            gpu: []
        };
        this.maxDataPoints = 30;
        this.updateInterval = null;
        this.init();
    }

    async init() {
        this.render();
        await this.loadChartLibrary();

        if (window.Chart) {
            this.initCharts();
        }

        // Start polling for metrics
        this.startPolling();

        // Listen for WebSocket metrics updates
        this.eventBus.on('ws:metrics', this.handleMetricsUpdate.bind(this));
    }

    render() {
        this.container.innerHTML = `
            <div class="module-card system-monitor">
                <div class="module-header">
                    <h3>System Monitor</h3>
                    <button class="btn-icon" id="metrics-refresh-btn" title="Refresh">↻</button>
                </div>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-header">
                            <span class="metric-label">CPU</span>
                            <span class="metric-value" id="cpu-value">--%</span>
                        </div>
                        <canvas id="cpu-chart" height="50"></canvas>
                    </div>
                    <div class="metric-card">
                        <div class="metric-header">
                            <span class="metric-label">Memory</span>
                            <span class="metric-value" id="memory-value">--%</span>
                        </div>
                        <canvas id="memory-chart" height="50"></canvas>
                    </div>
                    <div class="metric-card">
                        <div class="metric-header">
                            <span class="metric-label">GPU</span>
                            <span class="metric-value" id="gpu-value">--</span>
                        </div>
                        <canvas id="gpu-chart" height="50"></canvas>
                    </div>
                    <div class="metric-card disk-card">
                        <div class="metric-header">
                            <span class="metric-label">Disk (D:)</span>
                            <span class="metric-value" id="disk-value">--%</span>
                        </div>
                        <div class="disk-bar">
                            <div class="disk-used" id="disk-bar-fill" style="width: 0%"></div>
                        </div>
                        <div class="disk-info" id="disk-info">-- GB used</div>
                    </div>
                </div>
            </div>
        `;

        this.bindEvents();
    }

    bindEvents() {
        const refreshBtn = this.container.querySelector('#metrics-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.fetchMetrics());
        }
    }

    async loadChartLibrary() {
        if (window.Chart) return;

        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    initCharts() {
        const chartConfig = {
            type: 'line',
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                },
                scales: {
                    x: { display: false },
                    y: {
                        display: false,
                        min: 0,
                        max: 100
                    }
                },
                elements: {
                    point: { radius: 0 },
                    line: { tension: 0.4 }
                },
                animation: { duration: 0 }
            }
        };

        const metrics = [
            { id: 'cpu', color: '#6366f1' },
            { id: 'memory', color: '#22c55e' },
            { id: 'gpu', color: '#a855f7' }
        ];

        metrics.forEach(({ id, color }) => {
            const canvas = document.getElementById(`${id}-chart`);
            if (!canvas) return;

            const ctx = canvas.getContext('2d');
            this.charts[id] = new Chart(ctx, {
                ...chartConfig,
                data: {
                    labels: Array(this.maxDataPoints).fill(''),
                    datasets: [{
                        data: Array(this.maxDataPoints).fill(0),
                        borderColor: color,
                        borderWidth: 2,
                        fill: true,
                        backgroundColor: `${color}20`
                    }]
                }
            });
        });
    }

    startPolling() {
        // Fetch immediately
        this.fetchMetrics();

        // Then every 5 seconds
        this.updateInterval = setInterval(() => this.fetchMetrics(), 5000);
    }

    stopPolling() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    async fetchMetrics() {
        try {
            const metrics = await this.api.get('/system/metrics');
            this.updateDisplay(metrics);
        } catch (error) {
            console.error('[SystemMonitor] Failed to fetch metrics:', error);
        }
    }

    updateDisplay(metrics) {
        // Update CPU
        const cpuValue = document.getElementById('cpu-value');
        if (cpuValue) cpuValue.textContent = `${metrics.cpu_percent.toFixed(1)}%`;
        this.updateChart('cpu', metrics.cpu_percent);

        // Update Memory
        const memoryValue = document.getElementById('memory-value');
        if (memoryValue) memoryValue.textContent = `${metrics.memory_percent.toFixed(1)}%`;
        this.updateChart('memory', metrics.memory_percent);

        // Update GPU
        const gpuValue = document.getElementById('gpu-value');
        if (gpuValue) {
            if (metrics.gpu_percent !== null && metrics.gpu_percent !== undefined) {
                gpuValue.textContent = `${metrics.gpu_percent.toFixed(1)}%`;
                if (metrics.gpu_temp) {
                    gpuValue.textContent += ` (${metrics.gpu_temp}°C)`;
                }
            } else {
                gpuValue.textContent = 'N/A';
            }
        }
        this.updateChart('gpu', metrics.gpu_percent || 0);

        // Update Disk
        const diskValue = document.getElementById('disk-value');
        const diskBar = document.getElementById('disk-bar-fill');
        const diskInfo = document.getElementById('disk-info');

        if (diskValue) diskValue.textContent = `${metrics.disk_percent.toFixed(1)}%`;
        if (diskBar) {
            diskBar.style.width = `${metrics.disk_percent}%`;
            // Color based on usage
            if (metrics.disk_percent > 90) {
                diskBar.style.backgroundColor = 'var(--danger)';
            } else if (metrics.disk_percent > 75) {
                diskBar.style.backgroundColor = 'var(--warning)';
            } else {
                diskBar.style.backgroundColor = 'var(--accent-primary)';
            }
        }
        if (diskInfo) diskInfo.textContent = `${metrics.disk_used_gb} GB used`;
    }

    updateChart(metric, value) {
        const chart = this.charts[metric];
        if (!chart) return;

        // Add new data point
        this.historyData[metric].push(value);

        // Keep only maxDataPoints
        if (this.historyData[metric].length > this.maxDataPoints) {
            this.historyData[metric].shift();
        }

        // Update chart
        chart.data.datasets[0].data = [...this.historyData[metric]];

        // Pad with zeros if not enough data
        while (chart.data.datasets[0].data.length < this.maxDataPoints) {
            chart.data.datasets[0].data.unshift(0);
        }

        chart.update('none');
    }

    handleMetricsUpdate(metrics) {
        this.updateDisplay(metrics);
    }

    async refresh() {
        await this.fetchMetrics();
    }

    destroy() {
        this.stopPolling();
        Object.values(this.charts).forEach(chart => chart.destroy());
        this.charts = {};
    }
}
