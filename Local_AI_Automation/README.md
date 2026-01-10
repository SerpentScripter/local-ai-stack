# TR Local AI Automation Hub

A fully local, automated AI-driven workflow system using n8n, Ollama, and local LLMs.

## Overview

This system provides:
- **Email Analysis**: Automatic consulting lead detection from M365 email
- **News Digests**: Daily AI/tech and Security/GRC news summaries
- **Task Backlog**: Slack-based task management with LLM classification
- **Notifications**: Slack integration for all alerts and updates

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Slack Bot     │────▶│      n8n        │────▶│     Ollama      │
│   (Webhooks)    │◀────│   (Workflows)   │◀────│   (Local LLM)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │
         │              ┌────────┴────────┐
         │              │                 │
         ▼              ▼                 ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   M365 Graph    │  │   RSS Feeds     │  │    SQLite       │
│   (Email)       │  │   (News)        │  │   (Backlog)     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Quick Start

### 1. Start n8n

```powershell
cd Local_AI_Automation\scripts
.\start_n8n.ps1
```

Access n8n at: http://localhost:5678

### 2. Configure Integrations

Follow the setup guides in `docs/`:
- `slack_setup_guide.md` - Create Slack workspace and app
- `m365_setup_guide.md` - Configure Microsoft 365 email access

### 3. Import Workflows

In n8n:
1. Go to Workflows → Import
2. Import JSON files from `workflows/`:
   - `01_email_lead_detection.json`
   - `02_daily_news_digest.json`
   - `03_backlog_channel_monitor.json`

### 4. Configure Environment

Edit `docker/.env` with your credentials.

## Directory Structure

```
Local_AI_Automation/
├── docker/
│   ├── docker-compose.yml    # n8n + PostgreSQL
│   └── .env                  # Configuration
├── docs/
│   ├── slack_setup_guide.md  # Slack configuration
│   └── m365_setup_guide.md   # Microsoft 365 setup
├── workflows/
│   ├── 01_email_lead_detection.json
│   ├── 02_daily_news_digest.json
│   └── 03_backlog_channel_monitor.json
├── data/
│   ├── leads/                # Detected leads (JSON/MD)
│   ├── digests/              # News digests
│   ├── backlog/              # Task database
│   └── logs/                 # Automation logs
├── scripts/
│   ├── start_n8n.ps1
│   ├── stop_n8n.ps1
│   └── init_backlog_db.ps1
└── README.md
```

## Workflows

### Email Lead Detection
- **Trigger**: Every 5 minutes
- **Source**: M365 mailbox via Graph API
- **Process**: Classify emails, extract lead details
- **Output**: Slack notifications to `#leads-consulting`

### Daily News Digest
- **Trigger**: Daily at 7:00 AM
- **Sources**: RSS feeds (AI, Security, GRC)
- **Process**: Fetch, dedupe, summarize with LLM
- **Output**: Slack posts to `#digest-ai` and `#digest-grc`

### Backlog Channel Monitor
- **Trigger**: Slack events webhook
- **Source**: Messages in `#backlog` channel
- **Process**: Parse tasks with LLM, ask clarifications
- **Output**: Structured backlog items with confirmations

## Slack Channels

| Channel | Purpose |
|---------|---------|
| `#leads-consulting` | High-score consulting leads |
| `#leads-lowmatch` | Low-score leads for review |
| `#digest-ai` | Daily AI/tech news |
| `#digest-grc` | Daily security/compliance news |
| `#backlog` | Task input and management |
| `#tasks-status` | Task completion updates |
| `#system-alerts` | System errors and health |

## Backlog Commands

In `#backlog` channel:
- `done <id>` - Mark task complete
- `priority P0/P1/P2/P3 for <id>` - Change priority
- `list top 10` - Show top items
- `list P0` - Show urgent items
- `help` - Show commands

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `N8N_USER` | n8n admin username |
| `N8N_PASSWORD` | n8n admin password |
| `SLACK_BOT_TOKEN` | Slack bot token (xoxb-...) |
| `SLACK_WEBHOOK_*` | Webhook URLs per channel |
| `M365_TENANT_ID` | Azure AD tenant ID |
| `M365_CLIENT_ID` | Azure app client ID |
| `M365_CLIENT_SECRET` | Azure app secret |
| `M365_USER_EMAIL` | Email address to monitor |
| `OLLAMA_API_URL` | Ollama API endpoint |

### RSS Feeds

Configured in `.env`:
- `RSS_FEEDS_AI_CODING` - AI coding tools
- `RSS_FEEDS_LOCAL_AI` - Local/offline AI
- `RSS_FEEDS_SECURITY` - Security news
- `RSS_FEEDS_GRC` - Compliance/regulatory

## Requirements

- Docker Desktop
- Ollama with models:
  - `qwen2.5:14b` (general tasks)
  - `nomic-embed-text` (embeddings)
- Slack workspace (free tier works)
- Microsoft 365 subscription (for email)

## Troubleshooting

### n8n won't start
```powershell
docker logs n8n
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml up -d
```

### Ollama connection failed
Ensure Ollama is running and accessible:
```powershell
curl http://localhost:11434/api/tags
```

### Slack webhook errors
- Verify webhook URLs in `.env`
- Test with: `curl -X POST -H 'Content-type: application/json' --data '{"text":"test"}' YOUR_WEBHOOK_URL`

## Status

| Component | Status |
|-----------|--------|
| n8n | ✅ Running on http://localhost:5678 |
| Backlog API | ✅ Running on http://localhost:8765 |
| SQLite Database | ✅ Initialized with sample data |
| Ollama Classification | ✅ Tested and working |
| Slack Integration | ⏳ Pending workspace setup |
| M365 Integration | ⏳ Pending M365 migration |

### Workflow Templates Ready

| Workflow | File | Status |
|----------|------|--------|
| Email Lead Detection | `01_email_lead_detection.json` | 📋 Ready (needs M365) |
| Daily News Digest | `02_daily_news_digest.json` | 📋 Ready (needs Slack) |
| Backlog Channel Monitor | `03_backlog_channel_monitor.json` | 📋 Ready (needs Slack) |
| AI Tool Watcher | `04_ai_tool_watcher.json` | ✅ Can run locally |
| Knowledge Capture | `05_knowledge_capture.json` | ✅ Can run locally |

## Quick Start (Local Testing)

```powershell
# Start all services
cd Local_AI_Automation\scripts
.\start_all.ps1

# Run classification test
python test_ollama_classification.py

# Check backlog stats
curl http://localhost:8765/stats

# Stop all services
.\stop_all.ps1
```

## Backlog API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/items` | GET | List backlog items |
| `/items` | POST | Create new item |
| `/items/{id}` | GET | Get single item |
| `/items/{id}` | PATCH | Update item |
| `/items/{id}/done` | POST | Mark complete |
| `/items/{id}/priority/{P0-P3}` | POST | Change priority |
| `/stats` | GET | Get statistics |
| `/categories` | GET | List categories |

## Next Steps

1. **Create Slack workspace** → Follow `docs/slack_setup_guide.md`
2. **Complete M365 migration** → Then follow `docs/m365_setup_guide.md`
3. **Import workflows** → In n8n, import JSON files from `workflows/`
4. **Configure webhooks** → Update `.env` with Slack webhook URLs
5. **Activate workflows** → Enable in n8n after configuration
