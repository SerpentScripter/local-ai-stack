/**
 * Local AI Hub - Vue 3 Application
 * Main application entry point
 */

const { createApp, ref, reactive, computed, onMounted, onUnmounted, watch, provide, inject } = Vue;

// ==================== API Service ====================
const API_BASE = '';

const api = {
    async get(endpoint) {
        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        return response.json();
    },

    async post(endpoint, data) {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        return response.json();
    },

    async put(endpoint, data) {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        return response.json();
    },

    async delete(endpoint) {
        const response = await fetch(`${API_BASE}${endpoint}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
        return response.json();
    }
};

// ==================== WebSocket Service ====================
class WebSocketService {
    constructor() {
        this.ws = null;
        this.listeners = new Map();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        this.ws.onopen = () => {
            console.log('[WS] Connected');
            this.reconnectAttempts = 0;
            this.emit('connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.emit(data.type || 'message', data);
            } catch {
                this.emit('message', event.data);
            }
        };

        this.ws.onclose = () => {
            console.log('[WS] Disconnected');
            this.emit('disconnected');
            this.attemptReconnect();
        };

        this.ws.onerror = (error) => {
            console.error('[WS] Error:', error);
            this.emit('error', error);
        };
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => this.connect(), 2000 * this.reconnectAttempts);
        }
    }

    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    off(event, callback) {
        if (this.listeners.has(event)) {
            const callbacks = this.listeners.get(event);
            const index = callbacks.indexOf(callback);
            if (index > -1) callbacks.splice(index, 1);
        }
    }

    emit(event, data) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(cb => cb(data));
        }
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(typeof data === 'string' ? data : JSON.stringify(data));
        }
    }
}

const wsService = new WebSocketService();

// ==================== Toast Notifications ====================
const ToastComponent = {
    template: `
        <div class="toast-container" role="alert" aria-live="polite" aria-atomic="true">
            <transition-group name="toast">
                <div
                    v-for="toast in toasts"
                    :key="toast.id"
                    :class="['toast', 'toast-' + toast.type]"
                    role="alert"
                >
                    <span class="toast-icon" aria-hidden="true">{{ getIcon(toast.type) }}</span>
                    <span class="toast-message">{{ toast.message }}</span>
                    <button
                        class="toast-close"
                        @click="removeToast(toast.id)"
                        aria-label="Dismiss notification"
                    >&times;</button>
                </div>
            </transition-group>
        </div>
    `,
    setup() {
        const toasts = ref([]);
        let toastId = 0;

        const addToast = (message, type = 'info', duration = 4000) => {
            const id = ++toastId;
            toasts.value.push({ id, message, type });
            if (duration > 0) {
                setTimeout(() => removeToast(id), duration);
            }
        };

        const removeToast = (id) => {
            const index = toasts.value.findIndex(t => t.id === id);
            if (index > -1) toasts.value.splice(index, 1);
        };

        const getIcon = (type) => {
            const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
            return icons[type] || icons.info;
        };

        // Expose for global use
        window.showToast = addToast;

        return { toasts, addToast, removeToast, getIcon };
    }
};

// ==================== Navigation Component ====================
const NavigationComponent = {
    template: `
        <nav class="main-nav" role="navigation" aria-label="Main navigation">
            <div class="nav-brand">
                <h1>Local AI Hub</h1>
                <span class="nav-version" aria-label="Version">v3.0</span>
            </div>
            <ul class="nav-links" role="menubar">
                <li v-for="item in navItems" :key="item.id" role="none">
                    <a
                        :href="'#' + item.id"
                        :class="{ active: activeSection === item.id }"
                        @click.prevent="setActive(item.id)"
                        role="menuitem"
                        :aria-current="activeSection === item.id ? 'page' : undefined"
                    >
                        <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
                        <span class="nav-label">{{ item.label }}</span>
                    </a>
                </li>
            </ul>
            <div class="nav-status" role="status" aria-live="polite">
                <span :class="['status-dot', wsConnected ? 'connected' : 'disconnected']" aria-hidden="true"></span>
                <span class="sr-only">{{ wsConnected ? 'Connected' : 'Disconnected' }}</span>
            </div>
        </nav>
    `,
    props: ['activeSection', 'wsConnected'],
    emits: ['navigate'],
    setup(props, { emit }) {
        const navItems = [
            { id: 'dashboard', label: 'Dashboard', icon: '📊' },
            { id: 'kanban', label: 'Sessions', icon: '📌' },
            { id: 'backlog', label: 'Backlog', icon: '📋' },
            { id: 'agents', label: 'Agents', icon: '🤖' },
            { id: 'services', label: 'Services', icon: '🖥️' },
            { id: 'chat', label: 'Chat', icon: '💬' },
            { id: 'assessment', label: 'Health', icon: '🏥' },
            { id: 'settings', label: 'Settings', icon: '⚙️' }
        ];

        const setActive = (id) => emit('navigate', id);

        return { navItems, setActive };
    }
};

// ==================== Dashboard Component ====================
const DashboardComponent = {
    template: `
        <section class="dashboard-section" aria-labelledby="dashboard-heading">
            <h2 id="dashboard-heading" class="sr-only">Dashboard Overview</h2>

            <!-- Stats Cards -->
            <div class="stats-grid" role="region" aria-label="Statistics">
                <article class="stat-card" v-for="stat in stats" :key="stat.label">
                    <span class="stat-icon" aria-hidden="true">{{ stat.icon }}</span>
                    <div class="stat-content">
                        <span class="stat-value">{{ stat.value }}</span>
                        <span class="stat-label">{{ stat.label }}</span>
                    </div>
                </article>
            </div>

            <!-- Health Score -->
            <div class="health-card" role="region" aria-label="System Health">
                <h3>System Health</h3>
                <div class="health-score" :class="'grade-' + healthGrade.toLowerCase()">
                    <span class="score-letter" aria-label="Health grade">{{ healthGrade }}</span>
                    <span class="score-value">{{ healthScore }}%</span>
                </div>
                <p class="health-trend" v-if="healthTrend">
                    <span :class="'trend-' + healthTrend.trend">
                        {{ healthTrend.trend === 'improving' ? '↑' : healthTrend.trend === 'declining' ? '↓' : '→' }}
                        {{ healthTrend.change > 0 ? '+' : '' }}{{ healthTrend.change }}%
                    </span>
                    over 30 days
                </p>
            </div>

            <!-- Quick Actions -->
            <div class="quick-actions" role="region" aria-label="Quick Actions">
                <h3>Quick Actions</h3>
                <div class="action-buttons">
                    <button @click="runAssessment" class="action-btn" :disabled="loading">
                        Run Assessment
                    </button>
                    <button @click="checkUpdates" class="action-btn" :disabled="loading">
                        Check Updates
                    </button>
                    <button @click="whatNext" class="action-btn primary" :disabled="loading">
                        What Should I Do?
                    </button>
                </div>
            </div>

            <!-- Recommendation -->
            <div v-if="recommendation" class="recommendation-card" role="region" aria-label="Task Recommendation">
                <h3>Recommended Next Task</h3>
                <div class="recommendation-content">
                    <span class="rec-priority" :class="'priority-' + recommendation.priority">
                        {{ recommendation.priority }}
                    </span>
                    <p class="rec-title">{{ recommendation.title }}</p>
                    <p class="rec-reason">{{ recommendation.reason }}</p>
                </div>
            </div>
        </section>
    `,
    setup() {
        const stats = ref([]);
        const healthGrade = ref('B');
        const healthScore = ref(75);
        const healthTrend = ref(null);
        const recommendation = ref(null);
        const loading = ref(false);

        const loadDashboard = async () => {
            try {
                // Load stats
                const statsData = await api.get('/stats');
                const totalTasks = Object.values(statsData.by_status || {}).reduce((a, b) => a + b, 0);
                const doneTasks = statsData.by_status?.done || 0;

                stats.value = [
                    { icon: '📋', value: totalTasks, label: 'Total Tasks' },
                    { icon: '✅', value: doneTasks, label: 'Completed' },
                    { icon: '📈', value: statsData.recent_created || 0, label: 'This Week' },
                    { icon: '🎯', value: statsData.recent_completed || 0, label: 'Done This Week' }
                ];

                // Load health
                try {
                    const health = await api.get('/assessment/grade');
                    healthGrade.value = health.grade || 'B';
                    healthScore.value = Math.round(health.score || 75);
                } catch { }

                // Load trend
                try {
                    healthTrend.value = await api.get('/assessment/trend');
                } catch { }

            } catch (error) {
                console.error('Dashboard load error:', error);
            }
        };

        const runAssessment = async () => {
            loading.value = true;
            try {
                await api.get('/assessment/run');
                await loadDashboard();
                window.showToast('Assessment complete', 'success');
            } catch (error) {
                window.showToast('Assessment failed', 'error');
            }
            loading.value = false;
        };

        const checkUpdates = async () => {
            loading.value = true;
            try {
                const result = await api.get('/updates/check');
                window.showToast(`${result.updates_available} updates available`, 'info');
            } catch (error) {
                window.showToast('Update check failed', 'error');
            }
            loading.value = false;
        };

        const whatNext = async () => {
            loading.value = true;
            try {
                const result = await api.get('/prioritize/next');
                if (result.recommendation) {
                    recommendation.value = result.recommendation;
                } else {
                    window.showToast(result.message, 'info');
                }
            } catch (error) {
                window.showToast('Could not get recommendation', 'error');
            }
            loading.value = false;
        };

        onMounted(loadDashboard);

        return {
            stats, healthGrade, healthScore, healthTrend, recommendation, loading,
            runAssessment, checkUpdates, whatNext
        };
    }
};

// ==================== Backlog Component ====================
const BacklogComponent = {
    template: `
        <section class="backlog-section" aria-labelledby="backlog-heading">
            <header class="section-header">
                <h2 id="backlog-heading">Backlog</h2>
                <div class="header-actions">
                    <button @click="showCreateModal = true" class="btn-primary" aria-haspopup="dialog">
                        + New Task
                    </button>
                </div>
            </header>

            <!-- Filters -->
            <div class="filters" role="search" aria-label="Filter tasks">
                <label class="filter-group">
                    <span class="sr-only">Filter by status</span>
                    <select v-model="filters.status" @change="loadTasks" aria-label="Status filter">
                        <option value="">All Statuses</option>
                        <option value="backlog">Backlog</option>
                        <option value="in_progress">In Progress</option>
                        <option value="done">Done</option>
                    </select>
                </label>
                <label class="filter-group">
                    <span class="sr-only">Filter by priority</span>
                    <select v-model="filters.priority" @change="loadTasks" aria-label="Priority filter">
                        <option value="">All Priorities</option>
                        <option value="P0">P0 - Critical</option>
                        <option value="P1">P1 - High</option>
                        <option value="P2">P2 - Medium</option>
                        <option value="P3">P3 - Low</option>
                    </select>
                </label>
                <input
                    type="search"
                    v-model="searchQuery"
                    @input="debouncedSearch"
                    placeholder="Search tasks..."
                    aria-label="Search tasks"
                >
            </div>

            <!-- Task List -->
            <div class="task-list" role="list" aria-label="Tasks">
                <article
                    v-for="task in tasks"
                    :key="task.external_id"
                    class="task-card"
                    :class="'status-' + task.status"
                    role="listitem"
                    tabindex="0"
                    @keydown.enter="editTask(task)"
                >
                    <div class="task-header">
                        <span class="task-priority" :class="'priority-' + task.priority">
                            {{ task.priority }}
                        </span>
                        <span class="task-category">{{ task.category }}</span>
                    </div>
                    <h3 class="task-title">{{ task.title }}</h3>
                    <p class="task-description" v-if="task.description">
                        {{ truncate(task.description, 100) }}
                    </p>
                    <footer class="task-footer">
                        <span class="task-status">{{ formatStatus(task.status) }}</span>
                        <div class="task-actions">
                            <button @click="editTask(task)" aria-label="Edit task">Edit</button>
                            <button @click="deleteTask(task)" aria-label="Delete task">Delete</button>
                        </div>
                    </footer>
                </article>

                <p v-if="tasks.length === 0 && !loading" class="empty-state">
                    No tasks found. Create your first task!
                </p>
            </div>

            <!-- Create/Edit Modal -->
            <div v-if="showCreateModal || editingTask" class="modal-overlay" @click.self="closeModal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
                <div class="modal-content">
                    <h3 id="modal-title">{{ editingTask ? 'Edit Task' : 'Create Task' }}</h3>
                    <form @submit.prevent="saveTask">
                        <label class="form-group">
                            <span>Title</span>
                            <input v-model="taskForm.title" required aria-required="true">
                        </label>
                        <label class="form-group">
                            <span>Description</span>
                            <textarea v-model="taskForm.description" rows="3"></textarea>
                        </label>
                        <div class="form-row">
                            <label class="form-group">
                                <span>Priority</span>
                                <select v-model="taskForm.priority">
                                    <option value="P0">P0 - Critical</option>
                                    <option value="P1">P1 - High</option>
                                    <option value="P2">P2 - Medium</option>
                                    <option value="P3">P3 - Low</option>
                                </select>
                            </label>
                            <label class="form-group">
                                <span>Category</span>
                                <select v-model="taskForm.category">
                                    <option v-for="cat in categories" :key="cat.id" :value="cat.id">
                                        {{ cat.name }}
                                    </option>
                                </select>
                            </label>
                        </div>
                        <div class="modal-actions">
                            <button type="button" @click="closeModal">Cancel</button>
                            <button type="submit" class="btn-primary">
                                {{ editingTask ? 'Update' : 'Create' }}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </section>
    `,
    setup() {
        const tasks = ref([]);
        const categories = ref([]);
        const loading = ref(false);
        const showCreateModal = ref(false);
        const editingTask = ref(null);
        const searchQuery = ref('');
        const filters = reactive({ status: '', priority: '' });

        const taskForm = reactive({
            title: '',
            description: '',
            priority: 'P2',
            category: 'feature'
        });

        let searchTimeout = null;
        const debouncedSearch = () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(loadTasks, 300);
        };

        const loadTasks = async () => {
            loading.value = true;
            try {
                let url = '/backlog?';
                if (filters.status) url += `status=${filters.status}&`;
                if (filters.priority) url += `priority=${filters.priority}&`;
                if (searchQuery.value) url += `search=${encodeURIComponent(searchQuery.value)}`;

                tasks.value = await api.get(url);
            } catch (error) {
                window.showToast('Failed to load tasks', 'error');
            }
            loading.value = false;
        };

        const loadCategories = async () => {
            try {
                categories.value = await api.get('/categories');
            } catch { }
        };

        const saveTask = async () => {
            try {
                if (editingTask.value) {
                    await api.put(`/backlog/${editingTask.value.external_id}`, taskForm);
                    window.showToast('Task updated', 'success');
                } else {
                    await api.post('/backlog', taskForm);
                    window.showToast('Task created', 'success');
                }
                closeModal();
                loadTasks();
            } catch (error) {
                window.showToast('Failed to save task', 'error');
            }
        };

        const editTask = (task) => {
            editingTask.value = task;
            Object.assign(taskForm, {
                title: task.title,
                description: task.description || '',
                priority: task.priority,
                category: task.category
            });
        };

        const deleteTask = async (task) => {
            if (!confirm(`Delete "${task.title}"?`)) return;
            try {
                await api.delete(`/backlog/${task.external_id}`);
                window.showToast('Task deleted', 'success');
                loadTasks();
            } catch (error) {
                window.showToast('Failed to delete task', 'error');
            }
        };

        const closeModal = () => {
            showCreateModal.value = false;
            editingTask.value = null;
            Object.assign(taskForm, { title: '', description: '', priority: 'P2', category: 'feature' });
        };

        const truncate = (text, length) => {
            return text.length > length ? text.substring(0, length) + '...' : text;
        };

        const formatStatus = (status) => {
            const map = { backlog: 'Backlog', in_progress: 'In Progress', done: 'Done' };
            return map[status] || status;
        };

        onMounted(() => {
            loadTasks();
            loadCategories();
        });

        return {
            tasks, categories, loading, showCreateModal, editingTask, searchQuery, filters,
            taskForm, debouncedSearch, loadTasks, saveTask, editTask, deleteTask, closeModal,
            truncate, formatStatus
        };
    }
};

// ==================== Services Component ====================
const ServicesComponent = {
    template: `
        <section class="services-section" aria-labelledby="services-heading">
            <h2 id="services-heading">Services</h2>

            <div class="services-grid" role="list">
                <article
                    v-for="service in services"
                    :key="service.id"
                    class="service-card"
                    :class="'status-' + service.status"
                    role="listitem"
                >
                    <header class="service-header">
                        <span class="service-icon" aria-hidden="true">{{ service.icon }}</span>
                        <h3>{{ service.name }}</h3>
                    </header>
                    <div class="service-info">
                        <p class="service-url">{{ service.url }}</p>
                        <span class="service-status" :class="service.status" role="status">
                            {{ service.status }}
                        </span>
                    </div>
                    <footer class="service-actions">
                        <button
                            @click="toggleService(service)"
                            :disabled="service.loading"
                            :aria-label="service.status === 'running' ? 'Stop ' + service.name : 'Start ' + service.name"
                        >
                            {{ service.status === 'running' ? 'Stop' : 'Start' }}
                        </button>
                        <a :href="service.url" target="_blank" rel="noopener" v-if="service.status === 'running'">
                            Open
                        </a>
                    </footer>
                </article>
            </div>

            <!-- System Metrics -->
            <div class="metrics-panel" role="region" aria-label="System Metrics">
                <h3>System Metrics</h3>
                <div class="metrics-grid">
                    <div class="metric">
                        <span class="metric-label">CPU</span>
                        <div class="metric-bar" role="progressbar" :aria-valuenow="metrics.cpu" aria-valuemin="0" aria-valuemax="100">
                            <div class="metric-fill" :style="{ width: metrics.cpu + '%' }"></div>
                        </div>
                        <span class="metric-value">{{ metrics.cpu }}%</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Memory</span>
                        <div class="metric-bar" role="progressbar" :aria-valuenow="metrics.memory" aria-valuemin="0" aria-valuemax="100">
                            <div class="metric-fill" :style="{ width: metrics.memory + '%' }"></div>
                        </div>
                        <span class="metric-value">{{ metrics.memory }}%</span>
                    </div>
                    <div class="metric" v-if="metrics.gpu !== undefined">
                        <span class="metric-label">GPU</span>
                        <div class="metric-bar" role="progressbar" :aria-valuenow="metrics.gpu" aria-valuemin="0" aria-valuemax="100">
                            <div class="metric-fill gpu" :style="{ width: metrics.gpu + '%' }"></div>
                        </div>
                        <span class="metric-value">{{ metrics.gpu }}%</span>
                    </div>
                </div>
            </div>
        </section>
    `,
    setup() {
        const services = ref([]);
        const metrics = ref({ cpu: 0, memory: 0 });

        const loadServices = async () => {
            try {
                services.value = await api.get('/services');
            } catch (error) {
                window.showToast('Failed to load services', 'error');
            }
        };

        const loadMetrics = async () => {
            try {
                metrics.value = await api.get('/metrics');
            } catch { }
        };

        const toggleService = async (service) => {
            service.loading = true;
            try {
                const action = service.status === 'running' ? 'stop' : 'start';
                await api.post(`/services/${service.id}/${action}`);
                await loadServices();
                window.showToast(`${service.name} ${action}ed`, 'success');
            } catch (error) {
                window.showToast(`Failed to ${action} ${service.name}`, 'error');
            }
            service.loading = false;
        };

        let metricsInterval = null;

        onMounted(() => {
            loadServices();
            loadMetrics();
            metricsInterval = setInterval(loadMetrics, 5000);
        });

        onUnmounted(() => {
            if (metricsInterval) clearInterval(metricsInterval);
        });

        return { services, metrics, toggleService };
    }
};

// ==================== Chat Component ====================
const ChatComponent = {
    template: `
        <section class="chat-section" aria-labelledby="chat-heading">
            <h2 id="chat-heading" class="sr-only">AI Chat</h2>

            <!-- Model Selection -->
            <div class="chat-header">
                <label class="model-select">
                    <span>Model:</span>
                    <select v-model="selectedModel" aria-label="Select AI model">
                        <option v-for="model in models" :key="model.name" :value="model.name">
                            {{ model.name }}
                        </option>
                    </select>
                </label>
                <button @click="clearChat" aria-label="Clear chat history">Clear</button>
            </div>

            <!-- Messages -->
            <div
                ref="messagesContainer"
                class="chat-messages"
                role="log"
                aria-live="polite"
                aria-label="Chat messages"
            >
                <div
                    v-for="(msg, index) in messages"
                    :key="index"
                    :class="['message', 'message-' + msg.role]"
                >
                    <span class="message-role">{{ msg.role === 'user' ? 'You' : 'AI' }}</span>
                    <div class="message-content" v-html="formatMessage(msg.content)"></div>
                </div>
                <div v-if="loading" class="message message-assistant loading">
                    <span class="typing-indicator" aria-label="AI is typing">
                        <span></span><span></span><span></span>
                    </span>
                </div>
            </div>

            <!-- Input -->
            <form @submit.prevent="sendMessage" class="chat-input">
                <label class="sr-only" for="chat-input">Type your message</label>
                <textarea
                    id="chat-input"
                    v-model="input"
                    @keydown.enter.exact.prevent="sendMessage"
                    placeholder="Type a message..."
                    rows="2"
                    :disabled="loading"
                    aria-label="Chat message input"
                ></textarea>
                <button type="submit" :disabled="loading || !input.trim()" aria-label="Send message">
                    Send
                </button>
            </form>
        </section>
    `,
    setup() {
        const messages = ref([]);
        const input = ref('');
        const loading = ref(false);
        const models = ref([]);
        const selectedModel = ref('llama3.2');
        const messagesContainer = ref(null);

        const loadModels = async () => {
            try {
                const result = await api.get('/chat/models');
                models.value = result.models || [];
                if (models.value.length && !models.value.find(m => m.name === selectedModel.value)) {
                    selectedModel.value = models.value[0].name;
                }
            } catch { }
        };

        const sendMessage = async () => {
            if (!input.value.trim() || loading.value) return;

            const userMessage = input.value.trim();
            messages.value.push({ role: 'user', content: userMessage });
            input.value = '';
            loading.value = true;

            scrollToBottom();

            try {
                const response = await api.post('/chat', {
                    message: userMessage,
                    model: selectedModel.value
                });
                messages.value.push({ role: 'assistant', content: response.response });
            } catch (error) {
                messages.value.push({
                    role: 'assistant',
                    content: 'Sorry, I encountered an error. Please try again.'
                });
            }

            loading.value = false;
            scrollToBottom();
        };

        const clearChat = () => {
            messages.value = [];
        };

        const formatMessage = (content) => {
            // Basic markdown-like formatting
            return content
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                .replace(/\n/g, '<br>');
        };

        const scrollToBottom = () => {
            setTimeout(() => {
                if (messagesContainer.value) {
                    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
                }
            }, 100);
        };

        onMounted(loadModels);

        return {
            messages, input, loading, models, selectedModel, messagesContainer,
            sendMessage, clearChat, formatMessage
        };
    }
};

// ==================== Kanban Board Component ====================
const KanbanComponent = {
    template: `
        <section class="kanban-section" aria-labelledby="kanban-heading">
            <header class="section-header">
                <h2 id="kanban-heading">Agent Sessions</h2>
                <div class="header-actions">
                    <button @click="showCreateModal = true" class="btn-primary" aria-haspopup="dialog">
                        + New Session
                    </button>
                    <button @click="loadBoard" class="btn-secondary" :disabled="loading">
                        Refresh
                    </button>
                </div>
            </header>

            <!-- Kanban Board -->
            <div class="kanban-board" role="region" aria-label="Kanban Board">
                <div
                    v-for="column in columns"
                    :key="column.id"
                    class="kanban-column"
                    :class="'column-' + column.id"
                    role="region"
                    :aria-label="column.name + ' column'"
                >
                    <header class="column-header">
                        <h3>{{ column.name }}</h3>
                        <span class="column-count" aria-label="Session count">
                            {{ (board[column.id] || []).length }}
                        </span>
                    </header>
                    <div class="column-content" role="list">
                        <article
                            v-for="session in (board[column.id] || [])"
                            :key="session.session_id"
                            class="session-card"
                            :class="'state-' + session.state"
                            role="listitem"
                            tabindex="0"
                            @click="selectSession(session)"
                            @keydown.enter="selectSession(session)"
                        >
                            <div class="session-header">
                                <span class="session-agent" :class="'agent-' + session.agent_type">
                                    {{ session.agent_type }}
                                </span>
                                <span class="session-project">{{ session.project_id }}</span>
                            </div>
                            <p class="session-goal">{{ truncate(session.goal, 80) }}</p>
                            <div class="session-meta">
                                <span class="session-time" :title="session.updated_at">
                                    {{ formatTime(session.updated_at) }}
                                </span>
                                <span v-if="session.pr_url" class="session-pr">
                                    <a :href="session.pr_url" target="_blank" @click.stop>PR</a>
                                </span>
                                <span v-if="session.ci_status" class="session-ci" :class="'ci-' + session.ci_status">
                                    {{ session.ci_status }}
                                </span>
                            </div>
                            <p v-if="session.summary" class="session-summary">
                                {{ truncate(session.summary, 60) }}
                            </p>
                            <!-- Quick Actions -->
                            <div class="session-actions" @click.stop>
                                <button
                                    v-if="session.state === 'idle'"
                                    @click="startSession(session.session_id)"
                                    class="action-start"
                                    aria-label="Start session"
                                >▶</button>
                                <button
                                    v-if="session.state === 'waiting_for_approval'"
                                    @click="approveSession(session.session_id, true)"
                                    class="action-approve"
                                    aria-label="Approve"
                                >✓</button>
                                <button
                                    v-if="session.state === 'waiting_for_approval'"
                                    @click="approveSession(session.session_id, false)"
                                    class="action-deny"
                                    aria-label="Deny"
                                >✕</button>
                                <button
                                    v-if="session.state === 'working'"
                                    @click="pauseSession(session.session_id)"
                                    class="action-pause"
                                    aria-label="Pause"
                                >⏸</button>
                                <button
                                    v-if="session.state === 'paused'"
                                    @click="resumeSession(session.session_id)"
                                    class="action-resume"
                                    aria-label="Resume"
                                >▶</button>
                            </div>
                        </article>
                        <p v-if="(board[column.id] || []).length === 0" class="empty-column">
                            No sessions
                        </p>
                    </div>
                </div>
            </div>

            <!-- Stats Bar -->
            <div class="kanban-stats" role="status" aria-label="Session Statistics">
                <span class="stat">
                    <strong>{{ stats.total || 0 }}</strong> Total
                </span>
                <span class="stat">
                    <strong>{{ stats.by_state?.working || 0 }}</strong> Working
                </span>
                <span class="stat">
                    <strong>{{ stats.by_state?.waiting_for_approval || 0 }}</strong> Pending
                </span>
                <span class="stat">
                    <strong>{{ stats.by_state?.completed || 0 }}</strong> Completed
                </span>
            </div>

            <!-- Session Detail Modal -->
            <div v-if="selectedSession" class="modal-overlay" @click.self="selectedSession = null" role="dialog" aria-modal="true" aria-labelledby="session-detail-title">
                <div class="modal-content session-detail">
                    <header class="modal-header">
                        <h3 id="session-detail-title">Session: {{ selectedSession.session_id }}</h3>
                        <button @click="selectedSession = null" class="modal-close" aria-label="Close">&times;</button>
                    </header>
                    <div class="session-detail-content">
                        <dl class="detail-grid">
                            <dt>State</dt>
                            <dd><span class="state-badge" :class="'state-' + selectedSession.state">{{ selectedSession.state }}</span></dd>
                            <dt>Agent</dt>
                            <dd>{{ selectedSession.agent_type }}</dd>
                            <dt>Project</dt>
                            <dd>{{ selectedSession.project_id }}</dd>
                            <dt>Goal</dt>
                            <dd>{{ selectedSession.goal }}</dd>
                            <dt>Created</dt>
                            <dd>{{ new Date(selectedSession.created_at).toLocaleString() }}</dd>
                            <dt>Updated</dt>
                            <dd>{{ new Date(selectedSession.updated_at).toLocaleString() }}</dd>
                            <dt v-if="selectedSession.pr_url">PR</dt>
                            <dd v-if="selectedSession.pr_url"><a :href="selectedSession.pr_url" target="_blank">{{ selectedSession.pr_url }}</a></dd>
                            <dt v-if="selectedSession.ci_status">CI Status</dt>
                            <dd v-if="selectedSession.ci_status"><span :class="'ci-' + selectedSession.ci_status">{{ selectedSession.ci_status }}</span></dd>
                        </dl>
                        <div v-if="selectedSession.summary" class="session-summary-full">
                            <h4>AI Summary</h4>
                            <p>{{ selectedSession.summary }}</p>
                        </div>
                        <div v-if="selectedSession.context" class="session-context">
                            <h4>Context</h4>
                            <pre>{{ JSON.stringify(selectedSession.context, null, 2) }}</pre>
                        </div>
                        <div v-if="selectedSession.result" class="session-result">
                            <h4>Result</h4>
                            <pre>{{ JSON.stringify(selectedSession.result, null, 2) }}</pre>
                        </div>
                        <div v-if="selectedSession.error" class="session-error">
                            <h4>Error</h4>
                            <p class="error-message">{{ selectedSession.error }}</p>
                        </div>
                    </div>
                    <footer class="modal-actions">
                        <button v-if="selectedSession.state === 'idle'" @click="startSession(selectedSession.session_id)" class="btn-primary">Start</button>
                        <button v-if="selectedSession.state === 'working'" @click="pauseSession(selectedSession.session_id)">Pause</button>
                        <button v-if="selectedSession.state === 'paused'" @click="resumeSession(selectedSession.session_id)" class="btn-primary">Resume</button>
                        <button v-if="selectedSession.state === 'waiting_for_approval'" @click="approveSession(selectedSession.session_id, true)" class="btn-success">Approve</button>
                        <button v-if="selectedSession.state === 'waiting_for_approval'" @click="approveSession(selectedSession.session_id, false)" class="btn-danger">Deny</button>
                        <button v-if="selectedSession.state === 'working'" @click="completeSession(selectedSession.session_id)" class="btn-success">Complete</button>
                        <button v-if="['working', 'paused'].includes(selectedSession.state)" @click="failSession(selectedSession.session_id)" class="btn-danger">Fail</button>
                    </footer>
                </div>
            </div>

            <!-- Create Session Modal -->
            <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false" role="dialog" aria-modal="true" aria-labelledby="create-session-title">
                <div class="modal-content">
                    <h3 id="create-session-title">Create New Session</h3>
                    <form @submit.prevent="createSession">
                        <label class="form-group">
                            <span>Session ID</span>
                            <input v-model="newSession.session_id" required placeholder="unique-session-id" aria-required="true">
                        </label>
                        <label class="form-group">
                            <span>Project ID</span>
                            <input v-model="newSession.project_id" required placeholder="my-project" aria-required="true">
                        </label>
                        <label class="form-group">
                            <span>Goal</span>
                            <textarea v-model="newSession.goal" required rows="3" placeholder="What should this agent accomplish?" aria-required="true"></textarea>
                        </label>
                        <label class="form-group">
                            <span>Agent Type</span>
                            <select v-model="newSession.agent_type">
                                <option value="general">General</option>
                                <option value="research">Research</option>
                                <option value="code">Code</option>
                                <option value="review">Review</option>
                                <option value="test">Test</option>
                            </select>
                        </label>
                        <div class="modal-actions">
                            <button type="button" @click="showCreateModal = false">Cancel</button>
                            <button type="submit" class="btn-primary">Create Session</button>
                        </div>
                    </form>
                </div>
            </div>
        </section>
    `,
    setup() {
        const board = ref({});
        const stats = ref({});
        const loading = ref(false);
        const showCreateModal = ref(false);
        const selectedSession = ref(null);
        const wsKanban = ref(null);

        const columns = [
            { id: 'working', name: 'Working' },
            { id: 'needs_approval', name: 'Needs Approval' },
            { id: 'waiting', name: 'Waiting' },
            { id: 'idle', name: 'Idle' },
            { id: 'completed', name: 'Completed' },
            { id: 'failed', name: 'Failed' }
        ];

        const newSession = reactive({
            session_id: '',
            project_id: '',
            goal: '',
            agent_type: 'general',
            context: null
        });

        const loadBoard = async () => {
            loading.value = true;
            try {
                board.value = await api.get('/kanban/board');
                stats.value = await api.get('/kanban/stats');
            } catch (error) {
                window.showToast('Failed to load Kanban board', 'error');
            }
            loading.value = false;
        };

        const createSession = async () => {
            try {
                await api.post('/kanban/sessions', newSession);
                window.showToast('Session created', 'success');
                showCreateModal.value = false;
                Object.assign(newSession, { session_id: '', project_id: '', goal: '', agent_type: 'general', context: null });
                loadBoard();
            } catch (error) {
                window.showToast('Failed to create session', 'error');
            }
        };

        const startSession = async (sessionId) => {
            try {
                await api.post(`/kanban/sessions/${sessionId}/start`);
                window.showToast('Session started', 'success');
                loadBoard();
                if (selectedSession.value?.session_id === sessionId) {
                    selectedSession.value = await api.get(`/kanban/sessions/${sessionId}`);
                }
            } catch (error) {
                window.showToast('Failed to start session', 'error');
            }
        };

        const pauseSession = async (sessionId) => {
            try {
                await api.post(`/kanban/sessions/${sessionId}/pause`);
                window.showToast('Session paused', 'success');
                loadBoard();
                if (selectedSession.value?.session_id === sessionId) {
                    selectedSession.value = await api.get(`/kanban/sessions/${sessionId}`);
                }
            } catch (error) {
                window.showToast('Failed to pause session', 'error');
            }
        };

        const resumeSession = async (sessionId) => {
            try {
                await api.post(`/kanban/sessions/${sessionId}/resume`);
                window.showToast('Session resumed', 'success');
                loadBoard();
                if (selectedSession.value?.session_id === sessionId) {
                    selectedSession.value = await api.get(`/kanban/sessions/${sessionId}`);
                }
            } catch (error) {
                window.showToast('Failed to resume session', 'error');
            }
        };

        const approveSession = async (sessionId, approved) => {
            try {
                await api.post(`/kanban/sessions/${sessionId}/approval`, { approved, reason: approved ? null : 'Denied by user' });
                window.showToast(approved ? 'Session approved' : 'Session denied', 'success');
                loadBoard();
                if (selectedSession.value?.session_id === sessionId) {
                    selectedSession.value = await api.get(`/kanban/sessions/${sessionId}`);
                }
            } catch (error) {
                window.showToast('Failed to process approval', 'error');
            }
        };

        const completeSession = async (sessionId) => {
            try {
                await api.post(`/kanban/sessions/${sessionId}/complete`);
                window.showToast('Session completed', 'success');
                loadBoard();
                if (selectedSession.value?.session_id === sessionId) {
                    selectedSession.value = await api.get(`/kanban/sessions/${sessionId}`);
                }
            } catch (error) {
                window.showToast('Failed to complete session', 'error');
            }
        };

        const failSession = async (sessionId) => {
            try {
                await api.post(`/kanban/sessions/${sessionId}/fail`);
                window.showToast('Session marked as failed', 'warning');
                loadBoard();
                if (selectedSession.value?.session_id === sessionId) {
                    selectedSession.value = await api.get(`/kanban/sessions/${sessionId}`);
                }
            } catch (error) {
                window.showToast('Failed to fail session', 'error');
            }
        };

        const selectSession = (session) => {
            selectedSession.value = session;
        };

        const truncate = (text, length) => {
            if (!text) return '';
            return text.length > length ? text.substring(0, length) + '...' : text;
        };

        const formatTime = (timestamp) => {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);

            if (diffMins < 1) return 'just now';
            if (diffMins < 60) return `${diffMins}m ago`;
            if (diffHours < 24) return `${diffHours}h ago`;
            return `${diffDays}d ago`;
        };

        // WebSocket for real-time updates
        const connectKanbanWs = () => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            wsKanban.value = new WebSocket(`${protocol}//${window.location.host}/kanban/ws`);

            wsKanban.value.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'board') {
                        board.value = data.data;
                    } else if (data.type === 'state_changed') {
                        // Refresh board on state change
                        loadBoard();
                    }
                } catch { }
            };

            wsKanban.value.onclose = () => {
                setTimeout(connectKanbanWs, 3000);
            };
        };

        onMounted(() => {
            loadBoard();
            connectKanbanWs();
        });

        onUnmounted(() => {
            if (wsKanban.value) {
                wsKanban.value.close();
            }
        });

        return {
            board, stats, loading, showCreateModal, selectedSession, columns, newSession,
            loadBoard, createSession, startSession, pauseSession, resumeSession,
            approveSession, completeSession, failSession, selectSession, truncate, formatTime
        };
    }
};

// ==================== Assessment Component ====================
const AssessmentComponent = {
    template: `
        <section class="assessment-section" aria-labelledby="assessment-heading">
            <h2 id="assessment-heading">System Health Assessment</h2>

            <div class="assessment-header">
                <button @click="runAssessment" :disabled="loading" class="btn-primary">
                    {{ loading ? 'Running...' : 'Run Assessment' }}
                </button>
            </div>

            <div v-if="scoreboard" class="scoreboard">
                <!-- Overall Score -->
                <div class="overall-score" :class="'grade-' + scoreboard.overall.grade.toLowerCase()">
                    <span class="grade">{{ scoreboard.overall.grade }}</span>
                    <span class="score">{{ scoreboard.overall.score }}%</span>
                    <span class="trend" :class="'trend-' + scoreboard.overall.trend">
                        {{ scoreboard.overall.trend }}
                        ({{ scoreboard.overall.change > 0 ? '+' : '' }}{{ scoreboard.overall.change }}%)
                    </span>
                </div>

                <!-- Dimensions -->
                <div class="dimensions-grid" role="list">
                    <article
                        v-for="dim in scoreboard.dimensions"
                        :key="dim.name"
                        class="dimension-card"
                        :class="'status-' + dim.status"
                        role="listitem"
                    >
                        <h3>{{ dim.name }}</h3>
                        <div class="dimension-score">
                            <span class="grade" :class="'grade-' + dim.grade.toLowerCase()">{{ dim.grade }}</span>
                            <span class="score">{{ dim.score }}%</span>
                        </div>
                    </article>
                </div>

                <!-- Issues & Recommendations -->
                <div class="issues-panel" v-if="scoreboard.top_issues.length">
                    <h3>Critical Issues</h3>
                    <ul role="list">
                        <li v-for="issue in scoreboard.top_issues" :key="issue">{{ issue }}</li>
                    </ul>
                </div>

                <div class="recommendations-panel" v-if="scoreboard.top_recommendations.length">
                    <h3>Recommendations</h3>
                    <ul role="list">
                        <li v-for="rec in scoreboard.top_recommendations" :key="rec">{{ rec }}</li>
                    </ul>
                </div>
            </div>

            <p v-else class="empty-state">
                Run an assessment to see your system health score.
            </p>
        </section>
    `,
    setup() {
        const scoreboard = ref(null);
        const loading = ref(false);

        const runAssessment = async () => {
            loading.value = true;
            try {
                scoreboard.value = await api.get('/assessment/scoreboard');
                window.showToast('Assessment complete', 'success');
            } catch (error) {
                window.showToast('Assessment failed', 'error');
            }
            loading.value = false;
        };

        onMounted(async () => {
            try {
                scoreboard.value = await api.get('/assessment/scoreboard');
            } catch { }
        });

        return { scoreboard, loading, runAssessment };
    }
};

// ==================== Main App ====================
const App = {
    components: {
        'toast-notifications': ToastComponent,
        'main-navigation': NavigationComponent,
        'dashboard-view': DashboardComponent,
        'kanban-view': KanbanComponent,
        'backlog-view': BacklogComponent,
        'services-view': ServicesComponent,
        'chat-view': ChatComponent,
        'assessment-view': AssessmentComponent
    },
    template: `
        <div class="app-container">
            <toast-notifications></toast-notifications>
            <main-navigation
                :active-section="activeSection"
                :ws-connected="wsConnected"
                @navigate="activeSection = $event"
            ></main-navigation>
            <main class="main-content" role="main">
                <dashboard-view v-if="activeSection === 'dashboard'"></dashboard-view>
                <kanban-view v-if="activeSection === 'kanban'"></kanban-view>
                <backlog-view v-if="activeSection === 'backlog'"></backlog-view>
                <services-view v-if="activeSection === 'services'"></services-view>
                <chat-view v-if="activeSection === 'chat'"></chat-view>
                <assessment-view v-if="activeSection === 'assessment'"></assessment-view>
                <div v-if="activeSection === 'agents'" class="coming-soon">
                    <h2>Agents</h2>
                    <p>Agent management coming soon.</p>
                </div>
                <div v-if="activeSection === 'settings'" class="coming-soon">
                    <h2>Settings</h2>
                    <p>Settings panel coming soon.</p>
                </div>
            </main>
        </div>
    `,
    setup() {
        const activeSection = ref('dashboard');
        const wsConnected = ref(false);

        onMounted(() => {
            wsService.connect();
            wsService.on('connected', () => wsConnected.value = true);
            wsService.on('disconnected', () => wsConnected.value = false);

            // Handle hash navigation
            const hash = window.location.hash.slice(1);
            if (hash) activeSection.value = hash;

            window.addEventListener('hashchange', () => {
                activeSection.value = window.location.hash.slice(1) || 'dashboard';
            });
        });

        watch(activeSection, (newSection) => {
            window.location.hash = newSection;
        });

        return { activeSection, wsConnected };
    }
};

// Mount the app
createApp(App).mount('#app');
