/**
 * Workflow Builder Module
 * Visual workflow builder for connecting services
 */
export default class WorkflowBuilderModule {
    constructor({ container, eventBus, apiClient }) {
        this.container = container;
        this.eventBus = eventBus;
        this.api = apiClient;
        this.presets = [];
        this.currentWorkflow = null;
        this.selectedNode = null;
        this.isDragging = false;
        this.init();
    }

    async init() {
        await this.loadPresets();
        this.render();
        this.bindEvents();
    }

    async loadPresets() {
        try {
            this.presets = await this.api.get('/workflows/presets');
        } catch (error) {
            console.error('[WorkflowBuilder] Failed to load presets:', error);
            this.presets = [];
        }
    }

    render() {
        this.container.innerHTML = `
            <div class="module-card workflow-builder">
                <div class="module-header">
                    <h3>Workflow Builder</h3>
                    <div class="workflow-controls">
                        <select id="workflow-preset-select" class="preset-select">
                            <option value="">Select a preset...</option>
                            ${this.presets.map(p => `
                                <option value="${p.id}">${p.name}</option>
                            `).join('')}
                        </select>
                        <button class="btn-sm btn-secondary" id="workflow-clear-btn">Clear</button>
                    </div>
                </div>
                <div class="workflow-canvas-container">
                    <svg id="workflow-canvas" class="workflow-canvas">
                        <defs>
                            <marker id="arrowhead" markerWidth="10" markerHeight="7"
                                    refX="9" refY="3.5" orient="auto">
                                <polygon points="0 0, 10 3.5, 0 7" fill="var(--accent-primary)" />
                            </marker>
                        </defs>
                        <g id="connections-layer"></g>
                        <g id="nodes-layer"></g>
                    </svg>
                    <div class="workflow-empty" id="workflow-empty">
                        <p>Select a preset workflow to visualize, or create your own by dragging nodes.</p>
                    </div>
                </div>
                <div class="workflow-info" id="workflow-info" style="display: none;">
                    <div class="info-name" id="workflow-name"></div>
                    <div class="info-description" id="workflow-description"></div>
                </div>
            </div>
        `;
    }

    bindEvents() {
        const presetSelect = this.container.querySelector('#workflow-preset-select');
        const clearBtn = this.container.querySelector('#workflow-clear-btn');

        if (presetSelect) {
            presetSelect.addEventListener('change', (e) => {
                const presetId = e.target.value;
                if (presetId) {
                    const preset = this.presets.find(p => p.id === presetId);
                    if (preset) {
                        this.loadWorkflow(preset);
                    }
                }
            });
        }

        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearCanvas());
        }
    }

    loadWorkflow(workflow) {
        this.currentWorkflow = workflow;

        // Hide empty state
        const emptyDiv = this.container.querySelector('#workflow-empty');
        if (emptyDiv) emptyDiv.style.display = 'none';

        // Show info
        const infoDiv = this.container.querySelector('#workflow-info');
        const nameDiv = this.container.querySelector('#workflow-name');
        const descDiv = this.container.querySelector('#workflow-description');

        if (infoDiv) infoDiv.style.display = 'block';
        if (nameDiv) nameDiv.textContent = workflow.name;
        if (descDiv) descDiv.textContent = workflow.description;

        // Render the workflow
        this.renderWorkflow(workflow);
    }

    renderWorkflow(workflow) {
        const nodesLayer = this.container.querySelector('#nodes-layer');
        const connectionsLayer = this.container.querySelector('#connections-layer');

        if (!nodesLayer || !connectionsLayer) return;

        // Clear existing
        nodesLayer.innerHTML = '';
        connectionsLayer.innerHTML = '';

        // Render nodes
        workflow.nodes.forEach(node => {
            const nodeGroup = this.createNodeElement(node);
            nodesLayer.appendChild(nodeGroup);
        });

        // Render connections
        workflow.connections.forEach(conn => {
            const fromNode = workflow.nodes.find(n => n.id === conn.from);
            const toNode = workflow.nodes.find(n => n.id === conn.to);

            if (fromNode && toNode) {
                const path = this.createConnectionPath(fromNode, toNode);
                connectionsLayer.appendChild(path);
            }
        });
    }

    createNodeElement(node) {
        const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        group.setAttribute('class', `workflow-node node-${node.type}`);
        group.setAttribute('transform', `translate(${node.x}, ${node.y})`);
        group.setAttribute('data-node-id', node.id);

        // Node background
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        rect.setAttribute('width', '120');
        rect.setAttribute('height', '60');
        rect.setAttribute('rx', '8');
        rect.setAttribute('class', 'node-bg');

        // Node icon based on type
        const icon = this.getNodeIcon(node);
        const iconText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        iconText.setAttribute('x', '15');
        iconText.setAttribute('y', '35');
        iconText.setAttribute('class', 'node-icon');
        iconText.textContent = icon;

        // Node label
        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        label.setAttribute('x', '40');
        label.setAttribute('y', '35');
        label.setAttribute('class', 'node-label');
        label.textContent = node.label.length > 12 ? node.label.substring(0, 12) + '...' : node.label;

        // Input port
        const inputPort = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        inputPort.setAttribute('cx', '0');
        inputPort.setAttribute('cy', '30');
        inputPort.setAttribute('r', '6');
        inputPort.setAttribute('class', 'port input-port');

        // Output port
        const outputPort = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        outputPort.setAttribute('cx', '120');
        outputPort.setAttribute('cy', '30');
        outputPort.setAttribute('r', '6');
        outputPort.setAttribute('class', 'port output-port');

        group.appendChild(rect);
        group.appendChild(iconText);
        group.appendChild(label);
        group.appendChild(inputPort);
        group.appendChild(outputPort);

        return group;
    }

    getNodeIcon(node) {
        switch (node.type) {
            case 'input': return '📥';
            case 'output': return '📤';
            case 'service':
                if (node.service === 'ollama') return '🤖';
                return '⚙️';
            case 'agent': return '🔧';
            case 'tool': return '🛠️';
            default: return '📦';
        }
    }

    createConnectionPath(fromNode, toNode) {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');

        // Calculate bezier curve
        const startX = fromNode.x + 120;  // Output port
        const startY = fromNode.y + 30;
        const endX = toNode.x;            // Input port
        const endY = toNode.y + 30;

        // Control points for smooth curve
        const dx = Math.abs(endX - startX);
        const cp1x = startX + dx * 0.5;
        const cp1y = startY;
        const cp2x = endX - dx * 0.5;
        const cp2y = endY;

        const d = `M ${startX} ${startY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${endX} ${endY}`;

        path.setAttribute('d', d);
        path.setAttribute('class', 'connection-path');
        path.setAttribute('marker-end', 'url(#arrowhead)');

        return path;
    }

    clearCanvas() {
        this.currentWorkflow = null;

        const nodesLayer = this.container.querySelector('#nodes-layer');
        const connectionsLayer = this.container.querySelector('#connections-layer');
        const emptyDiv = this.container.querySelector('#workflow-empty');
        const infoDiv = this.container.querySelector('#workflow-info');
        const presetSelect = this.container.querySelector('#workflow-preset-select');

        if (nodesLayer) nodesLayer.innerHTML = '';
        if (connectionsLayer) connectionsLayer.innerHTML = '';
        if (emptyDiv) emptyDiv.style.display = 'block';
        if (infoDiv) infoDiv.style.display = 'none';
        if (presetSelect) presetSelect.value = '';
    }

    async refresh() {
        await this.loadPresets();
        const select = this.container.querySelector('#workflow-preset-select');
        if (select) {
            select.innerHTML = `
                <option value="">Select a preset...</option>
                ${this.presets.map(p => `
                    <option value="${p.id}">${p.name}</option>
                `).join('')}
            `;
        }
    }
}
