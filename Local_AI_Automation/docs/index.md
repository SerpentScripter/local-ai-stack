# Local AI Hub Documentation

**Version 3.0.0**

A comprehensive, self-hosted AI orchestration platform for local development and automation.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Ollama
- 16GB+ RAM recommended
- NVIDIA GPU (optional, for acceleration)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd local-ai-stack/Local_AI_Automation

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Start services
docker-compose up -d

# Start the API
uvicorn api.main:app --host 127.0.0.1 --port 8765 --reload
```

### Verify Installation

```bash
# Check API health
curl http://localhost:8765/health

# Check API info
curl http://localhost:8765/api/info
```

---

## Architecture Overview

```
+-------------------+     +-------------------+     +-------------------+
|   Vue 3 Frontend  | <-> |   FastAPI Backend | <-> |   Ollama / LLMs   |
+-------------------+     +-------------------+     +-------------------+
                                   |
              +--------------------+--------------------+
              |                    |                    |
    +----------------+   +----------------+   +----------------+
    |   Orchestrator |   |  Message Bus   |   |  Event Bridge  |
    +----------------+   +----------------+   +----------------+
              |                    |                    |
    +----------------+   +----------------+   +----------------+
    | Shared Memory  |   |  Job Queue     |   | Capabilities   |
    +----------------+   +----------------+   +----------------+
```

---

## Core Modules

### 1. Backlog Management

CRUD operations for task management with priority-based sorting.

**Endpoints:**
- `GET /backlog` - List tasks
- `POST /backlog` - Create task
- `GET /backlog/{id}` - Get task
- `PUT /backlog/{id}` - Update task
- `DELETE /backlog/{id}` - Delete task

**Example:**
```bash
curl -X POST http://localhost:8765/backlog \
  -H "Content-Type: application/json" \
  -d '{"title": "Research AI frameworks", "priority": "P1", "category": "research"}'
```

### 2. Agent Orchestration

Multi-agent coordination with supervisor pattern.

**Features:**
- Parallel execution
- Pipeline workflows
- Map-reduce patterns
- Fault tolerance
- Agent lifecycle management

**Endpoints:**
- `POST /orchestration/execute` - Execute agent task
- `GET /orchestration/sessions` - List sessions
- `GET /orchestration/timeline` - Execution timeline

### 3. Prioritization Engine

AI-driven task prioritization with multi-factor scoring.

**Factors:**
- Priority weight (P0-P3)
- Deadline urgency
- Dependency impact
- Task age
- Energy level match
- Context switch cost

**Endpoints:**
- `GET /prioritize/recommend` - Get recommendations
- `GET /prioritize/next` - What should I do next?
- `GET /prioritize/scope-creep` - Detect scope creep

### 4. Self-Assessment System

Automated health monitoring with grading.

**Dimensions:**
- Model Currency (20%)
- Tool Versions (15%)
- Capability Coverage (20%)
- Benchmark Scores (10%)
- Security Posture (20%)
- System Health (15%)

**Endpoints:**
- `GET /assessment/run` - Run assessment
- `GET /assessment/scoreboard` - Get scoreboard
- `GET /assessment/trend` - Score trend

### 5. Workflow Generator

Natural language to n8n workflow conversion.

**Flow:**
1. User describes workflow in natural language
2. LLM generates workflow JSON
3. Human reviews and approves
4. Deploy to n8n

**Endpoints:**
- `POST /workflow-gen/generate` - Generate workflow
- `GET /workflow-gen/pending` - List pending
- `POST /workflow-gen/{id}/review` - Approve/reject
- `POST /workflow-gen/{id}/deploy` - Deploy to n8n

### 6. Model Benchmarks

Performance tracking and quality benchmarks.

**Benchmark Types:**
- Response time
- Coherence
- Instruction following
- Code generation
- Reasoning
- Creativity
- Factual accuracy

**Endpoints:**
- `POST /benchmarks/run` - Run benchmarks
- `POST /benchmarks/compare` - Compare models
- `GET /benchmarks/leaderboard` - Model rankings

### 7. Update Manager

Automated updates with rollback capability.

**Features:**
- Version tracking
- Backup before update
- Health check after update
- Automatic rollback on failure

**Endpoints:**
- `GET /updates/check` - Check for updates
- `POST /updates/update` - Update component
- `POST /updates/rollback/{id}` - Rollback

### 8. Distributed Agents

Multi-node agent execution.

**Features:**
- Node registration
- Load balancing (round-robin, least-loaded)
- Task distribution
- Health monitoring
- Failure recovery

**Endpoints:**
- `GET /distributed/stats` - System stats
- `POST /distributed/nodes/register` - Register node
- `POST /distributed/tasks/submit` - Submit task

### 9. Kanban Board & Session Management

XState-inspired state machine for agent session tracking with visual Kanban board.

**Session States:**
- `idle` - Session created but not started
- `working` - Agent actively processing
- `waiting_for_approval` - Requires human approval
- `waiting_for_input` - Waiting for user input
- `paused` - Session paused
- `completed` - Session finished successfully
- `failed` - Session ended with error

**Kanban Columns:**
- Working
- Needs Approval
- Waiting
- Idle
- Completed
- Failed

**Endpoints:**
- `GET /kanban/board` - Get full Kanban board
- `POST /kanban/sessions` - Create new session
- `GET /kanban/sessions/{id}` - Get session
- `POST /kanban/sessions/{id}/start` - Start session
- `POST /kanban/sessions/{id}/approval` - Approve/deny
- `POST /kanban/sessions/{id}/pause` - Pause session
- `POST /kanban/sessions/{id}/resume` - Resume session
- `PUT /kanban/sessions/{id}/worktree` - Attach worktree
- `WS /kanban/ws` - Real-time updates

### 10. Git Worktree Manager

Safe parallel development in isolated git worktrees for AI agents.

**Features:**
- Isolated worktrees per session
- Automatic branch management
- Safe parallel development
- Merge-back with conflict detection
- Automatic cleanup

**Endpoints:**
- `POST /worktree/` - Create worktree
- `GET /worktree/` - List worktrees
- `GET /worktree/{id}` - Get worktree
- `GET /worktree/{id}/status` - Git status
- `POST /worktree/{id}/commit` - Commit changes
- `GET /worktree/{id}/check-merge` - Check merge status
- `POST /worktree/{id}/merge` - Merge to base
- `DELETE /worktree/{id}` - Delete worktree
- `GET /worktree/{id}/diff` - Get diff
- `GET /worktree/{id}/log` - Get commit log
- `POST /worktree/cleanup` - Cleanup stale worktrees

---

## External Integrations

### MCP Server

Connect Claude Code to the hub.

**Configuration (`mcp-config.json`):**
```json
{
  "mcpServers": {
    "local-ai-hub": {
      "command": "python",
      "args": ["scripts/mcp_server.py"]
    }
  }
}
```

**Available Tools:**
- `search_backlog` - Search tasks
- `create_task` - Create new task
- `run_research` - Start research agent
- `get_system_metrics` - Get metrics
- `chat_with_llm` - Chat with AI

### Webhooks

Receive events from external services.

**Supported:**
- GitHub (push, PR, issues, releases)
- GitLab
- Slack
- Custom webhooks

**Create Webhook:**
```bash
curl -X POST http://localhost:8765/webhooks/ \
  -H "Content-Type: application/json" \
  -d '{"name": "GitHub Events", "webhook_type": "github"}'
```

### Slack Integration

**Commands:**
- `/task <title>` - Create task
- `/research <topic>` - Start research
- `/status` - Check status
- `/help` - Show help

**Setup:**
1. Create Slack App
2. Add Bot Token to secrets
3. Configure webhook URL
4. Set signing secret

---

## Configuration

### Environment Variables

```bash
# Database
DB_PATH=/path/to/database.db

# Authentication
AUTH_ENABLED=true
JWT_SECRET=your-secret-key

# Ollama
OLLAMA_URL=http://localhost:11434

# Services
N8N_URL=http://localhost:5678
OPEN_WEBUI_URL=http://localhost:3000

# Slack (optional)
SLACK_BOT_TOKEN=xoxb-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
SLACK_SIGNING_SECRET=...
```

### Secrets Management

Use the secrets manager for sensitive data:

```bash
# Set secret
curl -X POST http://localhost:8765/secrets/set \
  -H "Content-Type: application/json" \
  -d '{"key": "GITHUB_TOKEN", "value": "ghp_..."}'

# Get secret (requires auth)
curl http://localhost:8765/secrets/get/GITHUB_TOKEN
```

---

## API Reference

### Authentication

When `AUTH_ENABLED=true`, requests require a JWT token:

```bash
# Get token
curl -X POST http://localhost:8765/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# Use token
curl http://localhost:8765/backlog \
  -H "Authorization: Bearer <token>"
```

### Rate Limiting

Default limits:
- 100 requests/minute per IP
- 1000 requests/hour per IP

### Error Responses

```json
{
  "detail": "Error message",
  "status_code": 400
}
```

---

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=api --cov-report=html

# Run specific test file
pytest tests/test_api.py

# Run specific test
pytest tests/test_api.py::TestBacklogEndpoints::test_create_task
```

### Code Style

```bash
# Format code
black api/

# Check types
mypy api/

# Lint
ruff check api/
```

### Adding New Routes

1. Create route file in `api/routes/`
2. Import in `api/routes/__init__.py`
3. Include router in `api/main.py`

---

## Troubleshooting

### Common Issues

**Ollama not responding:**
```bash
# Check Ollama is running
ollama list

# Restart Ollama
ollama serve
```

**Database locked:**
```bash
# Close other connections
# Or increase timeout in database.py
```

**Docker containers not starting:**
```bash
# Check logs
docker-compose logs

# Restart
docker-compose down && docker-compose up -d
```

### Logs

Logs are stored in `logs/api.log` with rotation.

```bash
# View recent logs
tail -f logs/api.log

# Search logs
grep "ERROR" logs/api.log
```

---

## Support

- GitHub Issues: [Report bugs or request features]
- Documentation: This page
- API Docs: http://localhost:8765/docs

---

*Last updated: 2024*
