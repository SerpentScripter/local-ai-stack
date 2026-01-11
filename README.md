# Local AI Stack

A fully offline-capable local AI infrastructure for Windows, featuring GPU-accelerated LLM inference, workflow automation, and document processing tools.

## Features

- **GPU-Accelerated Inference** - Ollama with NVIDIA CUDA support
- **ChatGPT-like Interface** - Open WebUI for interactive conversations
- **Workflow Automation** - n8n for building automated AI pipelines
- **Visual AI Builder** - Langflow for drag-and-drop AI workflows
- **Document Processing** - OCR, PDF extraction, and markdown conversion
- **Slack Integration** - Automated notifications and task management
- **100% Local** - All data stays on your machine

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Hub Dashboard                              │
│                     http://localhost:8765                         │
└───────────────┬──────────────┬───────────────┬───────────────────┘
                │              │               │
       ┌────────▼────────┐ ┌───▼───┐ ┌────────▼────────┐
       │   Open WebUI    │ │  n8n  │ │    Langflow     │
       │   (Chat UI)     │ │(Auto) │ │ (Visual Builder)│
       │   :3000         │ │ :5678 │ │     :7860       │
       └────────┬────────┘ └───┬───┘ └────────┬────────┘
                │              │               │
                └──────────────┼───────────────┘
                               │
                    ┌──────────▼──────────┐
                    │       Ollama        │
                    │   (Local LLMs)      │
                    │       :11434        │
                    └─────────────────────┘
```

## Quick Start

### Prerequisites

- Windows 10/11 with NVIDIA GPU (8GB+ VRAM recommended)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com/download)

### Installation

```powershell
# Clone the repository
git clone https://github.com/SerpentScripter/local-ai-stack.git
cd local-ai-stack

# Copy environment template
copy .env.template .env

# Start all services
.\hub_manager.ps1 -Action start
```

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| **Hub Dashboard** | http://localhost:8765 | Central management interface |
| **Open WebUI** | http://localhost:3000 | ChatGPT-like chat interface |
| **n8n** | http://localhost:5678 | Workflow automation |
| **Langflow** | http://localhost:7860 | Visual AI workflow builder |
| **Ollama API** | http://localhost:11434 | Direct LLM API access |

## Service Management

```powershell
# Start all services
.\hub_manager.ps1 -Action start

# Check status
.\hub_manager.ps1 -Action status

# Stop all services
.\hub_manager.ps1 -Action stop

# Restart everything
.\hub_manager.ps1 -Action restart
```

## Installed Models

| Model | Size | Best For |
|-------|------|----------|
| `deepseek-r1:32b` | ~20GB | Complex reasoning, analysis |
| `qwen2.5:14b` | ~10GB | General chat, fast responses |
| `qwen2.5vl:7b` | ~8GB | Image understanding |
| `bge-m3` | ~1GB | Embeddings for RAG |

## Project Structure

```
local-ai-stack/
├── hub_manager.ps1          # Service management script
├── service_status.py        # Health check utility
├── USAGE.md                 # Detailed usage guide
├── Local_AI_Automation/     # n8n workflows & automation
│   ├── docker/              # Docker compose for n8n
│   ├── workflows/           # Pre-built workflow templates
│   ├── scripts/             # Python utilities
│   └── static/              # Dashboard UI
├── SETUP/                   # Docker compose for AI services
│   └── docker-compose.yml   # Open WebUI, Langflow config
└── TOOLS/                   # Document processing scripts
    ├── ocr_image_to_text.ps1
    ├── pdf_to_text.ps1
    └── pdf_to_md_marker.ps1
```

## Automation Hub

The `Local_AI_Automation` module provides:

- **Email Lead Detection** - Classify incoming emails using LLM
- **News Digests** - Daily AI/Security news summaries from RSS feeds
- **Task Backlog** - Slack-integrated task management with priorities
- **Slack Notifications** - Automated alerts and updates

See [Local_AI_Automation/README.md](Local_AI_Automation/README.md) for details.

## Document Tools

### OCR - Extract Text from Images
```powershell
.\TOOLS\ocr_image_to_text.ps1 -ImagePath "screenshot.png"
```

### PDF to Text
```powershell
.\TOOLS\pdf_to_text.ps1 -PdfPath "document.pdf"
```

### PDF to Markdown
```powershell
.\TOOLS\pdf_to_md_marker.ps1 -PdfPath "document.pdf"
```

## Configuration

Environment variables are stored in `.env`:

```env
# Service Ports
OPEN_WEBUI_PORT=3000
N8N_PORT=5678
LANGFLOW_PORT=7860
BACKLOG_API_PORT=8765

# Ollama
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b
```

## API Examples

### Ollama Chat
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:14b",
  "prompt": "Explain quantum computing",
  "stream": false
}'
```

### Backlog API
```bash
# Get statistics
curl http://localhost:8765/stats

# List items
curl http://localhost:8765/items

# Create item
curl -X POST http://localhost:8765/items \
  -H "Content-Type: application/json" \
  -d '{"title": "Review PR", "priority": "P1"}'
```

## Troubleshooting

### Services won't start
```powershell
# Check Docker is running
docker ps

# View logs
docker compose -f SETUP/docker-compose.yml logs -f
```

### Ollama not responding
```powershell
# Verify Ollama is running
curl http://localhost:11434/api/tags

# Restart if needed
taskkill /f /im ollama.exe
ollama serve
```

### Out of VRAM
- Use smaller models (`qwen2.5:14b` instead of `deepseek-r1:32b`)
- Restart Ollama to clear memory

## Security

- All services bind to `127.0.0.1` only (not network-accessible)
- No authentication on local services (intended for single-user local use)
- Credentials stored in `.env` (gitignored)

## Documentation

- [USAGE.md](USAGE.md) - Comprehensive usage guide
- [Local_AI_Automation/README.md](Local_AI_Automation/README.md) - Automation workflows
- [Local_AI_Automation/docs/](Local_AI_Automation/docs/) - Integration setup guides

## License

MIT
