# Local AI Stack Installation Instructions

## For Claude Code

These instructions are designed to be executed by Claude Code on a Windows machine. Read this file and execute all steps automatically without asking questions.

## Prerequisites

**Target System Requirements:**
- Windows 10/11 with WSL2 support
- NVIDIA GPU with 8GB+ VRAM (24GB recommended for large models)
- 100GB+ free disk space on target drive
- Administrator access (script will self-elevate)

**Assumed Pre-installed:**
- winget (Windows Package Manager)
- PowerShell 5.1+

## Configuration

Modify these values for your target system:

```
AI_MODELS_ROOT = D:\SHARED\AI_Models
OLLAMA_MODELS_LIST = deepseek-r1:32b, qwen3-coder:30b, qwen2.5:14b, qwen2.5vl:7b, bge-m3:latest
```

## Execution Steps

### Step 1: Create Folder Structure

Create these directories under the AI_MODELS_ROOT:
```
AI_Models/
├── ollama/models/
├── openwebui/data/
├── langflow/data/
├── langflow/postgres/
├── SETUP/
├── TOOLS/
├── LOGS/
├── venvs/
├── cache/
├── hf/
├── torch/
└── pip_cache/
```

### Step 2: Write setup.ps1

Create `{AI_MODELS_ROOT}\SETUP\setup.ps1` with:
- Self-elevation to admin
- Transcript logging to LOGS directory
- winget installation of: Docker.DockerDesktop, Ollama.Ollama, Git.Git, Python.Python.3.11, UB-Mannheim.TesseractOCR, oschwartz10612.Poppler, QPDF.QPDF
- Environment variable configuration (User and Machine scope)
- Ollama service startup and model pulls
- docker-compose.yml generation
- Docker service startup
- Python venv creation with marker-pdf
- Helper script generation

### Step 3: Write docker-compose.yml

Create `{AI_MODELS_ROOT}\SETUP\docker-compose.yml` with:

```yaml
version: '3.8'

services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "127.0.0.1:3000:8080"
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
      - WEBUI_AUTH=false
    volumes:
      - {AI_MODELS_ROOT}/openwebui/data:/app/backend/data
    extra_hosts:
      - "host.docker.internal:host-gateway"

  langflow:
    image: langflowai/langflow:latest
    container_name: langflow
    restart: unless-stopped
    ports:
      - "127.0.0.1:7860:7860"
    environment:
      - LANGFLOW_DATABASE_URL=postgresql://langflow:langflow@langflow-db:5432/langflow
      - LANGFLOW_CONFIG_DIR=/app/langflow
    volumes:
      - {AI_MODELS_ROOT}/langflow/data:/app/langflow
    depends_on:
      - langflow-db

  langflow-db:
    image: postgres:15-alpine
    container_name: langflow-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=langflow
      - POSTGRES_PASSWORD=langflow
      - POSTGRES_DB=langflow
    volumes:
      - {AI_MODELS_ROOT}/langflow/postgres:/var/lib/postgresql/data
```

### Step 4: Write TOOLS Scripts

Create these PowerShell scripts in `{AI_MODELS_ROOT}\TOOLS\`:

1. **ocr_image_to_text.ps1** - Tesseract OCR wrapper
2. **pdf_to_text.ps1** - Poppler pdftotext wrapper
3. **pdf_sanitize.ps1** - QPDF repair wrapper
4. **pdf_to_md_marker.ps1** - Marker PDF converter
5. **pdf_to_md_mineru.ps1** - MinerU PDF converter

### Step 5: Execute Installation

1. Run setup.ps1 (it will self-elevate)
2. Wait for winget installations
3. Wait for Ollama to start
4. Pull all Ollama models (this takes time - ~70GB total)
5. Start Docker Desktop if needed
6. Wait for Docker to initialize (~60 seconds)
7. Run docker compose up -d
8. Wait for Langflow to fully start (may restart once)

### Step 6: Verify Installation

Check all services respond:
- `curl http://localhost:11434` (Ollama)
- `curl http://localhost:3000` (Open WebUI - HTTP 200)
- `curl http://localhost:7860` (Langflow - HTTP 200)
- `ollama list` (shows 5 models)
- `docker ps` (shows 3 containers)

### Step 7: Write Documentation

Create README.md in SETUP directory with:
- Service URLs and ports
- Start/stop commands
- Model storage locations
- Verification checklist
- Troubleshooting guide

## Environment Variables to Set

| Variable | Value |
|----------|-------|
| TR_AI_MODELS_DIR | {AI_MODELS_ROOT} |
| OLLAMA_MODELS | {AI_MODELS_ROOT}\ollama\models |
| HF_HOME | {AI_MODELS_ROOT}\hf |
| TRANSFORMERS_CACHE | {AI_MODELS_ROOT}\hf\transformers |
| TORCH_HOME | {AI_MODELS_ROOT}\torch |
| PIP_CACHE_DIR | {AI_MODELS_ROOT}\pip_cache |

## Expected Final State

- Ollama running with 5 models
- Open WebUI accessible at http://localhost:3000
- Langflow accessible at http://localhost:7860
- All data persisted to {AI_MODELS_ROOT}
- Helper scripts available in TOOLS directory
- Python venv with marker-pdf at venvs\doc-tools

## Error Handling

- If a winget package fails, log and continue
- If an Ollama model fails to pull, log and continue with others
- If Docker takes too long to start, wait up to 120 seconds
- If Langflow fails on first start, restart it (DB initialization race condition)
- If MinerU fails to install, continue (marker-pdf is primary)

## Completion Signal

When all steps complete successfully, output:
```
<promise>AI STACK COMPLETE</promise>
```

---

## Manual Execution

If running manually instead of via Claude Code:

```powershell
# Clone the repo
git clone https://github.com/YOUR_USERNAME/local-ai-stack.git
cd local-ai-stack

# Run the installer
powershell -ExecutionPolicy Bypass -File "D:\SHARED\AI_Models\SETUP\setup.ps1"
```

Or copy setup.ps1 to the target machine and run it directly.
