/**
 * WebSocket Manager - Real-time connection with auto-reconnect
 * Handles WebSocket lifecycle and message routing
 */
import { eventBus } from './event-bus.js';

class WebSocketManager {
    constructor(url = null) {
        this.url = url || `ws://${window.location.host}/ws`;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.isConnecting = false;
        this.shouldReconnect = true;
        this.pingInterval = null;
        this.messageQueue = [];
    }

    /**
     * Connect to WebSocket server
     * @returns {Promise<void>}
     */
    connect() {
        return new Promise((resolve, reject) => {
            if (this.ws?.readyState === WebSocket.OPEN) {
                resolve();
                return;
            }

            if (this.isConnecting) {
                // Wait for current connection attempt
                eventBus.once('ws:connected', resolve);
                eventBus.once('ws:error', reject);
                return;
            }

            this.isConnecting = true;
            this.ws = new WebSocket(this.url);

            this.ws.onopen = () => {
                console.log('[WS] Connected');
                this.isConnecting = false;
                this.reconnectAttempts = 0;
                this.shouldReconnect = true;

                // Process queued messages
                this.flushQueue();

                // Start ping interval
                this.startPing();

                eventBus.emit('ws:connected');
                resolve();
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    console.error('[WS] Failed to parse message:', error);
                }
            };

            this.ws.onclose = (event) => {
                console.log('[WS] Disconnected', event.code, event.reason);
                this.isConnecting = false;
                this.stopPing();

                eventBus.emit('ws:disconnected', { code: event.code, reason: event.reason });

                if (this.shouldReconnect && !event.wasClean) {
                    this.attemptReconnect();
                }
            };

            this.ws.onerror = (error) => {
                console.error('[WS] Error:', error);
                this.isConnecting = false;
                eventBus.emit('ws:error', error);
                reject(error);
            };
        });
    }

    /**
     * Handle incoming WebSocket message
     * @param {Object} data - Parsed message data
     */
    handleMessage(data) {
        const { type, payload } = data;

        // Handle ping/pong
        if (type === 'pong') {
            return;
        }

        // Emit typed event
        if (type) {
            eventBus.emit(`ws:${type}`, payload);
            eventBus.emit('ws:message', data);
        }
    }

    /**
     * Send a message through WebSocket
     * @param {string} type - Message type
     * @param {Object} payload - Message payload
     */
    send(type, payload = {}) {
        const message = JSON.stringify({ type, payload, timestamp: Date.now() });

        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(message);
        } else {
            // Queue message for later
            this.messageQueue.push(message);

            // Attempt to connect if not already
            if (!this.isConnecting) {
                this.connect();
            }
        }
    }

    /**
     * Flush queued messages
     */
    flushQueue() {
        while (this.messageQueue.length > 0 && this.ws?.readyState === WebSocket.OPEN) {
            const message = this.messageQueue.shift();
            this.ws.send(message);
        }
    }

    /**
     * Attempt to reconnect with exponential backoff
     */
    attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[WS] Max reconnect attempts reached');
            eventBus.emit('ws:reconnect_failed');
            return;
        }

        const delay = Math.min(
            this.reconnectDelay * Math.pow(2, this.reconnectAttempts),
            this.maxReconnectDelay
        );

        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`);

        eventBus.emit('ws:reconnecting', {
            attempt: this.reconnectAttempts + 1,
            maxAttempts: this.maxReconnectAttempts,
            delay
        });

        setTimeout(() => {
            this.reconnectAttempts++;
            this.connect().catch(() => {
                // Error handled in connect()
            });
        }, delay);
    }

    /**
     * Start ping interval to keep connection alive
     */
    startPing() {
        this.stopPing();
        this.pingInterval = setInterval(() => {
            if (this.ws?.readyState === WebSocket.OPEN) {
                this.send('ping');
            }
        }, 30000);
    }

    /**
     * Stop ping interval
     */
    stopPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    /**
     * Disconnect from WebSocket
     */
    disconnect() {
        this.shouldReconnect = false;
        this.stopPing();

        if (this.ws) {
            this.ws.close(1000, 'Client disconnecting');
            this.ws = null;
        }
    }

    /**
     * Get current connection state
     * @returns {string}
     */
    getState() {
        if (!this.ws) return 'CLOSED';

        switch (this.ws.readyState) {
            case WebSocket.CONNECTING: return 'CONNECTING';
            case WebSocket.OPEN: return 'OPEN';
            case WebSocket.CLOSING: return 'CLOSING';
            case WebSocket.CLOSED: return 'CLOSED';
            default: return 'UNKNOWN';
        }
    }

    /**
     * Check if connected
     * @returns {boolean}
     */
    isConnected() {
        return this.ws?.readyState === WebSocket.OPEN;
    }
}

// Export singleton instance
export const wsManager = new WebSocketManager();
export default WebSocketManager;
