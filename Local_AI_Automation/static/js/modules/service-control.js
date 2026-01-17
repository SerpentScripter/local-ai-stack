/**
 * Service Control Module
 * Start/stop/restart services from the dashboard
 */
export default class ServiceControlModule {
    constructor({ container, eventBus, apiClient, wsManager }) {
        this.container = container;
        this.eventBus = eventBus;
        this.api = apiClient;
        this.ws = wsManager;
        this.services = [];
        this.init();
    }

    async init() {
        // Subscribe to real-time status updates
        this.eventBus.on('ws:service_status', this.handleStatusUpdate.bind(this));

        // Initial render
        await this.refresh();
    }

    async refresh() {
        try {
            this.services = await this.api.get('/services');
            this.render();
        } catch (error) {
            console.error('[ServiceControl] Failed to load services:', error);
            this.renderError(error.message);
        }
    }

    render() {
        this.container.innerHTML = `
            <div class="module-card">
                <div class="module-header">
                    <h3>Service Control</h3>
                    <button class="btn-icon" title="Refresh" id="service-refresh-btn">↻</button>
                </div>
                <div class="service-grid">
                    ${this.services.map(svc => this.renderServiceCard(svc)).join('')}
                </div>
            </div>
        `;

        this.bindEvents();
    }

    renderServiceCard(service) {
        const statusClass = service.status === 'running' ? 'on' :
                           service.status === 'starting' ? 'wait' : 'off';
        const isRunning = service.status === 'running';

        return `
            <div class="service-card" data-service="${service.id}">
                <div class="service-header">
                    <span class="service-name">${service.name}</span>
                    <span class="indicator ${statusClass}" title="${service.status}"></span>
                </div>
                <div class="service-info">
                    <span class="port">Port: ${service.port}</span>
                    <span class="type">${service.type}</span>
                </div>
                <div class="service-actions">
                    <button class="btn-sm btn-success" data-action="start" data-service="${service.id}"
                            ${isRunning ? 'disabled' : ''}>Start</button>
                    <button class="btn-sm btn-danger" data-action="stop" data-service="${service.id}"
                            ${!isRunning ? 'disabled' : ''}>Stop</button>
                    <button class="btn-sm btn-secondary" data-action="restart" data-service="${service.id}">Restart</button>
                </div>
                ${isRunning ? `
                    <div class="service-links">
                        <a href="${service.health_url.replace('/api/tags', '').replace('/health', '').replace('/healthz', '')}"
                           target="_blank" class="btn-link">Open App</a>
                        ${service.type === 'docker' ? `
                            <button class="btn-link" data-action="logs" data-service="${service.id}">View Logs</button>
                        ` : ''}
                    </div>
                ` : ''}
            </div>
        `;
    }

    renderError(message) {
        this.container.innerHTML = `
            <div class="module-card error">
                <div class="module-header">
                    <h3>Service Control</h3>
                    <button class="btn-icon" title="Retry" id="service-refresh-btn">↻</button>
                </div>
                <div class="error-message">
                    <p>Failed to load services: ${message}</p>
                </div>
            </div>
        `;
        this.bindEvents();
    }

    bindEvents() {
        // Refresh button
        const refreshBtn = this.container.querySelector('#service-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refresh());
        }

        // Action buttons
        this.container.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const action = e.target.dataset.action;
                const serviceId = e.target.dataset.service;
                await this.handleAction(action, serviceId, e.target);
            });
        });
    }

    async handleAction(action, serviceId, button) {
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = '...';

        try {
            switch (action) {
                case 'start':
                    await this.api.post(`/services/${serviceId}/start`);
                    this.showToast(`Starting ${serviceId}...`, 'info');
                    break;
                case 'stop':
                    await this.api.post(`/services/${serviceId}/stop`);
                    this.showToast(`Stopping ${serviceId}...`, 'info');
                    break;
                case 'restart':
                    await this.api.post(`/services/${serviceId}/restart`);
                    this.showToast(`Restarting ${serviceId}...`, 'info');
                    break;
                case 'logs':
                    await this.showLogs(serviceId);
                    break;
            }

            // Refresh after action
            setTimeout(() => this.refresh(), 2000);
        } catch (error) {
            this.showToast(`Error: ${error.message}`, 'error');
        } finally {
            button.textContent = originalText;
            button.disabled = false;
        }
    }

    async showLogs(serviceId) {
        try {
            const result = await this.api.get(`/services/${serviceId}/logs`, { lines: 100 });
            this.showLogModal(serviceId, result.logs);
        } catch (error) {
            this.showToast(`Failed to fetch logs: ${error.message}`, 'error');
        }
    }

    showLogModal(serviceId, logs) {
        const modal = document.createElement('div');
        modal.className = 'modal open';
        modal.innerHTML = `
            <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
            <div class="modal-content modal-large">
                <div class="modal-header">
                    <h3>Logs: ${serviceId}</h3>
                    <button class="modal-close" onclick="this.closest('.modal').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <pre class="log-output">${this.escapeHtml(logs)}</pre>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    handleStatusUpdate(data) {
        const card = this.container.querySelector(`[data-service="${data.id}"]`);
        if (card) {
            const indicator = card.querySelector('.indicator');
            if (indicator) {
                indicator.className = `indicator ${data.status === 'running' ? 'on' :
                                                    data.status === 'starting' ? 'wait' : 'off'}`;
            }
        }

        // Refresh the full list after a short delay
        setTimeout(() => this.refresh(), 1000);
    }

    showToast(message, type = 'info') {
        this.eventBus.emit('toast:show', { message, type });

        // Fallback if no toast handler
        const container = document.getElementById('toast-container');
        if (!container) {
            console.log(`[${type.toUpperCase()}] ${message}`);
            return;
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `<span>${message}</span>`;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
