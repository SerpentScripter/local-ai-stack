/**
 * LLM Chat Module
 * Direct chat interface with Ollama models via streaming
 */
export default class LLMChatModule {
    constructor({ container, eventBus, apiClient }) {
        this.container = container;
        this.eventBus = eventBus;
        this.api = apiClient;
        this.models = [];
        this.currentModel = null;
        this.messages = [];
        this.isStreaming = false;
        this.init();
    }

    async init() {
        await this.loadModels();
        this.render();
        this.bindEvents();
    }

    async loadModels() {
        try {
            const data = await this.api.get('/chat/models');
            this.models = data.models || [];
            this.currentModel = this.models[0]?.name || 'qwen2.5:14b';
        } catch (error) {
            console.error('[LLMChat] Failed to load models:', error);
            this.models = [];
        }
    }

    render() {
        this.container.innerHTML = `
            <div class="module-card chat-module">
                <div class="module-header">
                    <h3>LLM Chat</h3>
                    <div class="chat-controls">
                        <select id="model-selector" class="model-select">
                            ${this.models.length > 0 ? this.models.map(m => `
                                <option value="${m.name}" ${m.name === this.currentModel ? 'selected' : ''}>
                                    ${m.name}
                                </option>
                            `).join('') : '<option value="">No models available</option>'}
                        </select>
                        <button class="btn-icon" id="clear-chat-btn" title="Clear chat">🗑</button>
                    </div>
                </div>
                <div class="chat-messages" id="chat-messages">
                    <div class="chat-welcome">
                        <p>Chat with your local LLM. Select a model above and start typing.</p>
                    </div>
                </div>
                <div class="chat-input-area">
                    <textarea id="chat-input" placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
                              rows="2" ${this.models.length === 0 ? 'disabled' : ''}></textarea>
                    <button id="chat-send-btn" class="btn btn-primary" ${this.models.length === 0 ? 'disabled' : ''}>
                        Send
                    </button>
                </div>
            </div>
        `;
    }

    bindEvents() {
        const input = this.container.querySelector('#chat-input');
        const sendBtn = this.container.querySelector('#chat-send-btn');
        const modelSelect = this.container.querySelector('#model-selector');
        const clearBtn = this.container.querySelector('#clear-chat-btn');

        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendMessage());
        }

        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        if (modelSelect) {
            modelSelect.addEventListener('change', (e) => {
                this.currentModel = e.target.value;
            });
        }

        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearChat());
        }
    }

    async sendMessage() {
        const input = this.container.querySelector('#chat-input');
        const message = input?.value.trim();

        if (!message || this.isStreaming || !this.currentModel) return;

        // Clear input
        input.value = '';

        // Remove welcome message
        const welcome = this.container.querySelector('.chat-welcome');
        if (welcome) welcome.remove();

        // Add user message
        this.addMessage('user', message);

        // Create assistant message placeholder
        const assistantMsgEl = this.addMessage('assistant', '', true);
        const contentEl = assistantMsgEl.querySelector('.message-content');

        // Start streaming
        this.isStreaming = true;
        this.updateSendButton(true);

        try {
            const url = `/chat/stream?prompt=${encodeURIComponent(message)}&model=${encodeURIComponent(this.currentModel)}`;
            const eventSource = new EventSource(url);
            let fullResponse = '';

            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    if (data.error) {
                        contentEl.textContent = `Error: ${data.error}`;
                        eventSource.close();
                        this.isStreaming = false;
                        this.updateSendButton(false);
                        return;
                    }

                    if (data.token) {
                        fullResponse += data.token;
                        contentEl.innerHTML = this.formatMessage(fullResponse);
                        this.scrollToBottom();
                    }

                    if (data.done) {
                        eventSource.close();
                        this.isStreaming = false;
                        this.updateSendButton(false);
                        assistantMsgEl.classList.remove('streaming');
                    }
                } catch (e) {
                    console.error('[LLMChat] Parse error:', e);
                }
            };

            eventSource.onerror = (error) => {
                console.error('[LLMChat] EventSource error:', error);
                eventSource.close();
                this.isStreaming = false;
                this.updateSendButton(false);
                if (!fullResponse) {
                    contentEl.textContent = 'Connection error. Please try again.';
                }
            };
        } catch (error) {
            console.error('[LLMChat] Request error:', error);
            contentEl.textContent = `Error: ${error.message}`;
            this.isStreaming = false;
            this.updateSendButton(false);
        }
    }

    addMessage(role, content, streaming = false) {
        const messagesDiv = this.container.querySelector('#chat-messages');
        const msgEl = document.createElement('div');
        msgEl.className = `chat-message ${role} ${streaming ? 'streaming' : ''}`;

        const avatar = role === 'user' ? '👤' : '🤖';
        msgEl.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">${content || (streaming ? '<span class="typing-dots">...</span>' : '')}</div>
        `;

        messagesDiv.appendChild(msgEl);
        this.scrollToBottom();

        return msgEl;
    }

    formatMessage(text) {
        // Basic markdown-like formatting
        return text
            .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em>$1</em>')
            .replace(/\n/g, '<br>');
    }

    scrollToBottom() {
        const messagesDiv = this.container.querySelector('#chat-messages');
        if (messagesDiv) {
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
    }

    updateSendButton(isLoading) {
        const btn = this.container.querySelector('#chat-send-btn');
        const input = this.container.querySelector('#chat-input');

        if (btn) {
            btn.textContent = isLoading ? '...' : 'Send';
            btn.disabled = isLoading;
        }

        if (input) {
            input.disabled = isLoading;
        }
    }

    clearChat() {
        const messagesDiv = this.container.querySelector('#chat-messages');
        if (messagesDiv) {
            messagesDiv.innerHTML = `
                <div class="chat-welcome">
                    <p>Chat cleared. Start a new conversation.</p>
                </div>
            `;
        }
        this.messages = [];
    }

    async refresh() {
        await this.loadModels();
        const select = this.container.querySelector('#model-selector');
        if (select) {
            select.innerHTML = this.models.length > 0 ? this.models.map(m => `
                <option value="${m.name}" ${m.name === this.currentModel ? 'selected' : ''}>
                    ${m.name}
                </option>
            `).join('') : '<option value="">No models available</option>';
        }
    }
}
