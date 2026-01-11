# Local AI Stack

**Your data never leaves your machine. Your AI never sleeps.**

A complete, offline-capable AI infrastructure that runs entirely on your hardware. No API keys. No usage limits. No data harvesting. Just raw, local intelligence at your fingertips.

---

## Why Local AI?

> *"The best AI is the one that's always available, completely private, and entirely yours."*

| Cloud AI | Local AI Stack |
|----------|----------------|
| Monthly fees | One-time setup |
| Rate limits | Unlimited queries |
| Data sent to servers | 100% private |
| Requires internet | Works offline |
| Provider controls the model | You control everything |

---

## What Can You Build?

### For Security Professionals

**Analyze malware without exposure**
```
Drop a suspicious script into Open WebUI. Ask the AI to explain what it does.
Your analysis stays local. No sample uploaded anywhere.
```

**Process sensitive audit logs**
```
Feed thousands of log entries through Langflow.
Extract anomalies, summarize findings, generate reports.
Client data never leaves your infrastructure.
```

**Automate compliance checking**
```
n8n workflow: Watch a folder → Extract text from uploaded policies →
Compare against regulatory requirements → Generate gap analysis →
Notify via Slack
```

### For Developers

**Code review on autopilot**
```python
# In your CI/CD pipeline
curl -X POST http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:14b",
  "prompt": "Review this diff for security issues, performance problems, and code smells:\n\n'$(git diff HEAD~1)'"
}'
```

**Generate documentation from code**
```
Point Langflow at your codebase.
It reads your functions, understands the patterns,
and generates API docs, README sections, and inline comments.
```

**Refactor legacy code safely**
```
Upload that 2000-line PHP file from 2008.
Ask the AI to modernize it piece by piece.
Your proprietary code stays proprietary.
```

### For Researchers & Analysts

**Build a private research assistant**
```
1. Collect 500 PDFs on your topic
2. Convert to markdown with pdf_to_md_marker.ps1
3. Create embeddings with bge-m3
4. Query your personal knowledge base in natural language
```

**Competitive intelligence pipeline**
```
n8n workflow:
  → RSS feeds from competitors' blogs
  → Summarize with Ollama
  → Extract product announcements, pricing changes, feature updates
  → Daily digest to Slack
  → Store in searchable database
```

**Literature review automation**
```
"Summarize the methodology section of each of these 50 papers
and identify common approaches."

Run overnight. Wake up to structured insights.
```

### For Content Creators

**Never face a blank page again**
```
"I'm writing about [topic]. Give me:
- 5 unique angles no one is covering
- An outline for a 2000-word article
- 3 controversial takes to spark discussion
- SEO keywords I should include"
```

**Transcribe and repurpose**
```
Meeting recording → Whisper transcription → Ollama summary →
Blog post draft → Social media snippets → Newsletter content

One recording. Five content pieces. Zero cloud uploads.
```

**Localized content at scale**
```
Write once in English.
Adapt for Swedish, German, French markets.
Maintain brand voice. Respect cultural nuances.
```

### For Business Automation

**Email triage that actually works**
```
n8n monitors inbox → Ollama classifies priority →
Hot leads go to #sales-urgent → Support requests auto-categorize →
Newsletters archive silently → You see only what matters
```

**Contract analysis**
```
Upload vendor contracts.
"Extract all liability clauses, payment terms, and termination conditions.
Flag anything unusual compared to standard agreements."

Legal review prep in minutes, not hours.
```

**Meeting intelligence**
```
Before: "What did we decide about the API redesign?"
After: AI searches your meeting notes, finds the discussion,
       summarizes the decision, lists action items and owners.
```

---

## Real-World Examples

### Example 1: The Security Consultant's Toolkit

```
Morning routine:
1. n8n fetches overnight security advisories
2. Ollama summarizes: "3 critical, 12 high, 28 medium for your client stack"
3. Relevant CVEs auto-matched to client inventory
4. Slack alert: "Client X runs affected Apache version"
5. Draft advisory email generated, waiting for your review

Time saved: 2 hours/day
```

### Example 2: The Solo Developer's Force Multiplier

```powershell
# Your git commit hook
git diff --cached | curl -s http://localhost:11434/api/generate -d @- \
  --data-urlencode "model=qwen2.5:14b" \
  --data-urlencode "prompt=Review this code. Be harsh. Find bugs."

# Every commit gets reviewed. Every time. For free.
```

### Example 3: The Knowledge Worker's Second Brain

```
Document processing pipeline:
1. Screenshot → OCR → searchable text
2. PDF → Markdown → embedded in vector DB
3. Web article → cleaned content → personal wiki
4. Voice note → transcription → linked to project

Everything you've ever read, instantly queryable:
"What was that article about zero-trust architecture I read last month?"
```

### Example 4: The Privacy-First AI Assistant

```
Use cases that require absolute privacy:
- Medical symptom analysis (personal health data)
- Financial planning (income, investments, debts)
- Legal document review (confidential matters)
- HR decisions (employee performance data)
- Competitive strategy (business intelligence)

Cloud AI: "Trust us with your data"
Local AI: "What data? It never left your SSD."
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         YOUR MACHINE                              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                     Hub Dashboard                           │  │
│  │                  http://localhost:8765                      │  │
│  └──────────┬─────────────────┬─────────────────┬─────────────┘  │
│             │                 │                 │                 │
│    ┌────────▼────────┐ ┌──────▼──────┐ ┌───────▼───────┐        │
│    │   Open WebUI    │ │     n8n     │ │   Langflow    │        │
│    │   Chat & RAG    │ │  Automation │ │ Visual Builder│        │
│    │    :3000        │ │    :5678    │ │    :7860      │        │
│    └────────┬────────┘ └──────┬──────┘ └───────┬───────┘        │
│             │                 │                 │                 │
│             └─────────────────┼─────────────────┘                 │
│                               │                                   │
│                    ┌──────────▼──────────┐                       │
│                    │       Ollama        │                       │
│                    │  GPU-Accelerated    │                       │
│                    │   LLM Inference     │                       │
│                    │      :11434         │                       │
│                    └──────────┬──────────┘                       │
│                               │                                   │
│                    ┌──────────▼──────────┐                       │
│                    │    NVIDIA GPU       │                       │
│                    │   (Your Hardware)   │                       │
│                    └─────────────────────┘                       │
│                                                                   │
│  ════════════════════════════════════════════════════════════    │
│                    NOTHING LEAVES THIS BOX                        │
└──────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- Windows 10/11 with NVIDIA GPU (8GB+ VRAM)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com/download)

### 5-Minute Setup

```powershell
# Clone
git clone https://github.com/SerpentScripter/local-ai-stack.git
cd local-ai-stack

# Configure
copy .env.template .env

# Launch
.\hub_manager.ps1 -Action start

# Open your browser
start http://localhost:8765
```

### Access Points

| Service | URL | What It Does |
|---------|-----|--------------|
| **Hub Dashboard** | http://localhost:8765 | Command center for everything |
| **Open WebUI** | http://localhost:3000 | Chat interface (like ChatGPT) |
| **n8n** | http://localhost:5678 | Automation workflows |
| **Langflow** | http://localhost:7860 | Visual AI pipeline builder |
| **Ollama API** | http://localhost:11434 | Direct programmatic access |

---

## Models Included

| Model | VRAM | Specialty | Use When... |
|-------|------|-----------|-------------|
| `deepseek-r1:32b` | ~20GB | Deep reasoning | You need thorough analysis |
| `qwen2.5:14b` | ~10GB | Fast generalist | Quick answers, high volume |
| `qwen2.5vl:7b` | ~8GB | Vision | Analyzing images, screenshots |
| `bge-m3` | ~1GB | Embeddings | Building searchable knowledge bases |

---

## Service Management

```powershell
.\hub_manager.ps1 -Action start    # Wake everything up
.\hub_manager.ps1 -Action status   # Health check
.\hub_manager.ps1 -Action stop     # Shut down gracefully
.\hub_manager.ps1 -Action restart  # Fresh start
```

---

## Build Your First Automation

### 1. Simple: Daily News Digest

```
In n8n:
1. Schedule trigger: 7:00 AM daily
2. HTTP Request: Fetch RSS feeds
3. Ollama node: "Summarize these articles in 3 bullets each"
4. Slack node: Post to #morning-digest
```

### 2. Intermediate: Document Q&A Bot

```
In Langflow:
1. File Upload → PDF Loader
2. Text Splitter (chunk size: 1000)
3. Ollama Embeddings (bge-m3)
4. Vector Store (Chroma)
5. Retrieval Chain → Ollama (qwen2.5:14b)
6. Chat Interface

Upload your documents. Ask questions. Get answers with sources.
```

### 3. Advanced: Intelligent Email Assistant

```
In n8n:
1. IMAP trigger: New email arrives
2. Ollama: Classify (lead/support/spam/newsletter)
3. Switch node: Route by classification
4. Lead path: Extract details → CRM API → Slack #leads
5. Support path: Draft response → Human review queue
6. Spam path: Archive silently
```

---

## API Quick Reference

### Chat with AI
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:14b",
  "prompt": "Explain kubernetes to a 5-year-old",
  "stream": false
}'
```

### Analyze an Image
```bash
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5vl:7b",
  "prompt": "What is in this image?",
  "images": ["'$(base64 -w0 image.png)'"]
}'
```

### Create Embeddings
```bash
curl http://localhost:11434/api/embeddings -d '{
  "model": "bge-m3",
  "prompt": "Text to convert to vector"
}'
```

### Backlog Management
```bash
# Add a task
curl -X POST http://localhost:8765/items \
  -H "Content-Type: application/json" \
  -d '{"title": "Review Q4 reports", "priority": "P1", "category": "Finance"}'

# Get stats
curl http://localhost:8765/stats
```

---

## Document Processing Tools

```powershell
# Screenshot to searchable text
.\TOOLS\ocr_image_to_text.ps1 -ImagePath "whiteboard.jpg"

# PDF to clean text
.\TOOLS\pdf_to_text.ps1 -PdfPath "contract.pdf"

# PDF to structured markdown (tables preserved)
.\TOOLS\pdf_to_md_marker.ps1 -PdfPath "report.pdf"
```

---

## Project Structure

```
local-ai-stack/
├── hub_manager.ps1              # One script to rule them all
├── .env.template                # Configuration template
├── USAGE.md                     # Detailed usage guide
│
├── Local_AI_Automation/         # The automation brain
│   ├── docker/                  # n8n + PostgreSQL
│   ├── workflows/               # Ready-to-import automations
│   ├── scripts/                 # Python utilities
│   │   ├── backlog_api.py       # Task management API
│   │   └── slack_notify.py      # Notification helper
│   └── static/                  # Dashboard UI
│
├── SETUP/                       # Core AI services
│   └── docker-compose.yml       # Open WebUI, Langflow
│
└── TOOLS/                       # Document processing
    ├── ocr_image_to_text.ps1
    ├── pdf_to_text.ps1
    └── pdf_to_md_marker.ps1
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No models available" | Run `ollama list` to verify models are installed |
| Services won't start | Ensure Docker Desktop is running |
| Slow responses | Use smaller model or check `nvidia-smi` for GPU usage |
| Out of VRAM | Restart Ollama: `taskkill /f /im ollama.exe && ollama serve` |
| n8n database error | Reset with `docker compose down -v && docker compose up -d` |

---

## Security Model

```
✓ All services bind to 127.0.0.1 (localhost only)
✓ No external network exposure by default
✓ No telemetry or usage tracking
✓ Credentials in .env (gitignored)
✓ Your prompts stay on your disk
✓ Your documents stay on your disk
✓ Your outputs stay on your disk
```

---

## What's Next?

Once you're running:

1. **Explore Open WebUI** - Upload documents, try different models
2. **Build your first n8n workflow** - Start with the RSS digest example
3. **Create a Langflow pipeline** - Visual is easier to iterate
4. **Integrate with your tools** - Slack, email, APIs, databases
5. **Customize models** - Create Modelfiles for specific personalities

---

## Philosophy

This stack exists because:

- **Privacy is not optional** - Some data should never touch the cloud
- **Ownership matters** - Your AI should work for you, not the other way around
- **Limits are artificial** - No rate limits, no token caps, no "please try again later"
- **Local is fast** - No network latency, no server queues
- **Learning is doing** - The best way to understand AI is to run it yourself

---

## Documentation

- [USAGE.md](USAGE.md) - Complete usage guide with advanced examples
- [Local_AI_Automation/README.md](Local_AI_Automation/README.md) - Automation workflows
- [Local_AI_Automation/docs/](Local_AI_Automation/docs/) - Integration guides (Slack, M365)

---

## License

MIT - Use it, modify it, ship it, sell it. Just don't blame us if your AI becomes sentient.

---

<p align="center">
<b>Built for those who believe AI should be a tool you own, not a service you rent.</b>
</p>
