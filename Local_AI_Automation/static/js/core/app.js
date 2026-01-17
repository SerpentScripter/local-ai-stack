/**
 * Dashboard Application Controller
 * Main entry point for the TR Local AI Hub dashboard
 */
import { eventBus } from './event-bus.js';
import { apiClient } from './api-client.js';
import { wsManager } from './websocket-manager.js';

class DashboardApp {
    constructor() {
        this.modules = new Map();
        this.isInitialized = false;
    }

    /**
     * Initialize the dashboard application
     */
    async init() {
        if (this.isInitialized) {
            console.warn('[App] Already initialized');
            return;
        }

        console.log('[App] Initializing TR Local AI Hub Dashboard...');

        try {
            // Set up global error handling
            this.setupErrorHandling();

            // Connect WebSocket
            await this.connectWebSocket();

            // Load modules dynamically
            await this.loadModules();

            // Set up global event listeners
            this.setupEventListeners();

            this.isInitialized = true;
            console.log('[App] Dashboard initialized successfully');

            eventBus.emit('app:ready');
        } catch (error) {
            console.error('[App] Failed to initialize:', error);
            this.showError('Failed to initialize dashboard. Please refresh the page.');
        }
    }

    /**
     * Connect to WebSocket server
     */
    async connectWebSocket() {
        try {
            await wsManager.connect();
            this.updateConnectionStatus(true);
        } catch (error) {
            console.warn('[App] WebSocket connection failed, will retry:', error);
            this.updateConnectionStatus(false);
        }

        // Listen for connection state changes
        eventBus.on('ws:connected', () => this.updateConnectionStatus(true));
        eventBus.on('ws:disconnected', () => this.updateConnectionStatus(false));
        eventBus.on('ws:reconnecting', (data) => {
            this.showToast(`Reconnecting... (${data.attempt}/${data.maxAttempts})`, 'warning');
        });
    }

    /**
     * Load dashboard modules
     */
    async loadModules() {
        const moduleConfigs = [
            { name: 'service-control', container: 'service-control-panel' },
            { name: 'llm-chat', container: 'llm-chat-panel' },
            { name: 'system-monitor', container: 'system-monitor-panel' },
            { name: 'workflow-builder', container: 'workflow-builder-panel' }
        ];

        for (const config of moduleConfigs) {
            const container = document.getElementById(config.container);
            if (!container) {
                console.log(`[App] Container not found for module: ${config.name}`);
                continue;
            }

            try {
                const module = await import(`../modules/${config.name}.js`);
                const instance = new module.default({
                    container,
                    eventBus,
                    apiClient,
                    wsManager
                });

                this.modules.set(config.name, instance);
                console.log(`[App] Loaded module: ${config.name}`);
            } catch (error) {
                console.warn(`[App] Failed to load module ${config.name}:`, error.message);
            }
        }
    }

    /**
     * Set up global event listeners
     */
    setupEventListeners() {
        // WebSocket message routing
        eventBus.on('ws:service_status', (data) => {
            eventBus.emit('service:status_update', data);
        });

        eventBus.on('ws:metrics', (data) => {
            eventBus.emit('system:metrics_update', data);
        });

        eventBus.on('ws:chat_token', (data) => {
            eventBus.emit('chat:token', data);
        });

        // Global keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl+K: Focus search/chat
            if (e.ctrlKey && e.key === 'k') {
                e.preventDefault();
                const chatInput = document.getElementById('chat-input');
                if (chatInput) chatInput.focus();
            }

            // Escape: Close modals
            if (e.key === 'Escape') {
                this.closeAllModals();
            }
        });
    }

    /**
     * Set up global error handling
     */
    setupErrorHandling() {
        window.addEventListener('unhandledrejection', (event) => {
            console.error('[App] Unhandled promise rejection:', event.reason);
            if (event.reason?.message) {
                this.showError(event.reason.message);
            }
        });

        window.addEventListener('error', (event) => {
            console.error('[App] Global error:', event.error);
        });
    }

    /**
     * Update connection status indicator
     * @param {boolean} connected
     */
    updateConnectionStatus(connected) {
        const indicator = document.getElementById('connection-status');
        if (indicator) {
            indicator.className = `indicator ${connected ? 'on' : 'off'}`;
            indicator.title = connected ? 'Connected' : 'Disconnected';
        }

        eventBus.emit('app:connection_status', { connected });
    }

    /**
     * Show a toast notification
     * @param {string} message
     * @param {string} type - 'success', 'error', 'warning', 'info'
     * @param {number} duration - Duration in milliseconds
     */
    showToast(message, type = 'info', duration = 3000) {
        const container = document.getElementById('toast-container') || this.createToastContainer();

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
        `;

        container.appendChild(toast);

        // Auto-remove after duration
        setTimeout(() => {
            toast.classList.add('toast-fade-out');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    /**
     * Create toast container if it doesn't exist
     * @returns {HTMLElement}
     */
    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
        return container;
    }

    /**
     * Show error message
     * @param {string} message
     */
    showError(message) {
        this.showToast(message, 'error', 5000);
    }

    /**
     * Show success message
     * @param {string} message
     */
    showSuccess(message) {
        this.showToast(message, 'success');
    }

    /**
     * Close all open modals
     */
    closeAllModals() {
        document.querySelectorAll('.modal.open').forEach(modal => {
            modal.classList.remove('open');
        });
        eventBus.emit('modal:closed');
    }

    /**
     * Get a loaded module by name
     * @param {string} name
     * @returns {Object|undefined}
     */
    getModule(name) {
        return this.modules.get(name);
    }

    /**
     * Refresh all modules
     */
    async refreshAll() {
        for (const [name, module] of this.modules) {
            if (typeof module.refresh === 'function') {
                try {
                    await module.refresh();
                } catch (error) {
                    console.error(`[App] Failed to refresh module ${name}:`, error);
                }
            }
        }
    }
}

// Create and export singleton instance
export const app = new DashboardApp();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => app.init());
} else {
    app.init();
}

export default DashboardApp;
