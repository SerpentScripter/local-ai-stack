# Local AI Stack Installation Results

## Overview

This document describes the complete installation of a fully offline-capable local AI stack on Windows 11, executed via Claude Code using the Ralph Wiggum iterative technique.

**Date:** 2026-01-10
**Host System:** Windows 11 workstation ("TR")
**Hardware:**
- GPU: NVIDIA RTX 4090 (24GB VRAM)
- CPU: AMD Threadripper 7960
- RAM: 64GB
- WSL2: Ubuntu 24.04 available

## Installation Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Folder structure | Success | All directories created under `D:\SHARED\AI_Models\` |
| setup.ps1 | Success | 820-line PowerShell master installer |
| docker-compose.yml | Success | Open WebUI + Langflow + PostgreSQL |
| README.md | Success | Quick reference documentation |
| TOOLS scripts (5) | Success | OCR and PDF helper scripts |
| Tesseract OCR | Success | Installed via winget |
| Poppler | Success | Installed via winget |
| QPDF | Success | Installed via winget |
| Environment variables | Success | Set for User scope |
| Python doc-tools venv | Success | marker-pdf installed |
| Ollama models (5) | Success | All models pulled |
| Docker services | Success | All containers running |

## Directory Structure

```
D:\SHARED\AI_Models\
├── SETUP\
│   ├── setup.ps1           # Master installer script
│   ├── docker-compose.yml  # Docker services configuration
│   └── README.md           # Quick reference
├── TOOLS\
│   ├── ocr_image_to_text.ps1    # Tesseract OCR wrapper
│   ├── pdf_to_text.ps1          # Poppler pdftotext wrapper
│   ├── pdf_sanitize.ps1         # QPDF repair/linearize wrapper
│   ├── pdf_to_md_marker.ps1     # Marker PDF-to-Markdown
│   └── pdf_to_md_mineru.ps1     # MinerU PDF-to-Markdown/JSON
├── LOGS\
│   └── setup_*.log         # Installation logs
├── ollama\
│   └── models\             # Ollama model storage (~70GB)
├── openwebui\
│   └── data\               # Open WebUI persistent data
├── langflow\
│   ├── data\               # Langflow persistent data
│   └── postgres\           # PostgreSQL database files
├── venvs\
│   └── doc-tools\          # Python venv with marker-pdf
├── hf\                     # HuggingFace cache
├── torch\                  # PyTorch cache
├── pip_cache\              # pip download cache
└── cache\                  # General cache directory
```

## Installed Software

### Via winget

| Package ID | Name | Purpose |
|------------|------|---------|
| Docker.DockerDesktop | Docker Desktop | Container runtime |
| Ollama.Ollama | Ollama | Local LLM serving with GPU |
| Git.Git | Git | Version control |
| Python.Python.3.12 | Python 3.12 | Runtime for doc-tools |
| UB-Mannheim.TesseractOCR | Tesseract OCR | Image text extraction |
| oschwartz10612.Poppler | Poppler | PDF text extraction |
| QPDF.QPDF | QPDF | PDF repair/linearization |

### Ollama Models

| Model | Size | Purpose |
|-------|------|---------|
| deepseek-r1:32b | 19 GB | Reasoning/general (Q4_K_M) |
| qwen3-coder:30b | 18 GB | Code generation (Q4_K_M) |
| qwen2.5:14b | 9 GB | General purpose (Q4_K_M) |
| qwen2.5vl:7b | 6 GB | Vision-language multimodal |
| bge-m3:latest | 1.2 GB | Embeddings (F16) |

**Total model storage:** ~53 GB (plus additional models already present)

### Docker Containers

| Container | Image | Port | Purpose |
|-----------|-------|------|---------|
| open-webui | ghcr.io/open-webui/open-webui:main | 127.0.0.1:3000 | ChatGPT-like web interface |
| langflow | langflowai/langflow:latest | 127.0.0.1:7860 | Visual workflow builder |
| langflow-db | postgres:15-alpine | 5432 (internal) | Langflow database |

### Python Environment

Location: `D:\SHARED\AI_Models\venvs\doc-tools\`

Installed packages:
- marker-pdf (PDF to Markdown conversion)
- pytesseract (Python Tesseract wrapper)
- pillow (Image processing)

Note: MinerU installation was attempted but may require additional dependencies.

## Environment Variables

Set for User scope (persistent across sessions):

| Variable | Value |
|----------|-------|
| TR_AI_MODELS_DIR | D:\SHARED\AI_Models |
| OLLAMA_MODELS | D:\SHARED\AI_Models\ollama\models |
| HF_HOME | D:\SHARED\AI_Models\hf |
| TRANSFORMERS_CACHE | D:\SHARED\AI_Models\hf\transformers |
| TORCH_HOME | D:\SHARED\AI_Models\torch |
| PIP_CACHE_DIR | D:\SHARED\AI_Models\pip_cache |

## Design Decisions

### 1. Port Binding (127.0.0.1 only)
All services are bound to localhost only for security. They are not accessible from other machines on the network.

### 2. Docker Volume Mounts
Used absolute Windows paths with forward slashes (`D:/SHARED/...`) for Docker compatibility. All persistent data stored outside containers.

### 3. Ollama Configuration
- Runs natively on Windows (not in Docker) for direct GPU access
- Model storage redirected via `OLLAMA_MODELS` environment variable
- Accessible to Docker containers via `host.docker.internal:11434`

### 4. Open WebUI Authentication
Disabled (`WEBUI_AUTH=false`) for local-only use. Enable if exposing to network.

### 5. Langflow Database
Uses PostgreSQL instead of SQLite for better reliability with concurrent access.

### 6. Model Selection
- **deepseek-r1:32b**: Best reasoning model that fits in 24GB VRAM
- **qwen3-coder:30b**: Specialized for code generation
- **qwen2.5:14b**: Fast general-purpose model
- **qwen2.5vl:7b**: Multimodal (vision + language) for image understanding
- **bge-m3:latest**: Multilingual embeddings for RAG/search

### 7. OCR Language Support
Default OCR language set to `eng+swe` (English + Swedish) based on user locale.

## Service URLs

| Service | URL | Status |
|---------|-----|--------|
| Ollama API | http://localhost:11434 | Running |
| Open WebUI | http://localhost:3000 | Running (HTTP 200) |
| Langflow | http://localhost:7860 | Running (HTTP 200) |

## Files Created

### D:\SHARED\AI_Models\SETUP\setup.ps1
820-line PowerShell script that:
1. Self-elevates to admin if needed
2. Creates folder structure
3. Installs prerequisites via winget
4. Sets environment variables
5. Starts Ollama and pulls models
6. Writes docker-compose.yml
7. Starts Docker services
8. Creates Python venv with doc-tools
9. Downloads Swedish tessdata
10. Creates helper scripts
11. Writes README

### D:\SHARED\AI_Models\SETUP\docker-compose.yml
Docker Compose configuration for:
- Open WebUI (port 3000) connected to Ollama
- Langflow (port 7860) with PostgreSQL backend
- PostgreSQL 15 Alpine for Langflow

### D:\SHARED\AI_Models\TOOLS\*.ps1
Five helper scripts:
- `ocr_image_to_text.ps1` - OCR images using Tesseract
- `pdf_to_text.ps1` - Extract text from PDFs using Poppler
- `pdf_sanitize.ps1` - Repair/linearize PDFs using QPDF
- `pdf_to_md_marker.ps1` - Convert PDF to Markdown using Marker
- `pdf_to_md_mineru.ps1` - Convert PDF to Markdown/JSON using MinerU

## Known Issues / Limitations

1. **Swedish tessdata**: Download to `C:\Program Files\Tesseract-OCR\tessdata\` requires admin elevation. May need manual download.

2. **MinerU**: Installation in doc-tools venv may be incomplete. Use marker-pdf as primary PDF conversion tool.

3. **Docker Desktop**: Must be running before Docker services can start. First startup after reboot takes ~60 seconds.

4. **VRAM Usage**: Running deepseek-r1:32b uses ~20GB VRAM. Smaller models run concurrently, but large models may require unloading others.

## Verification Commands

```powershell
# Check Ollama
curl http://localhost:11434
ollama list

# Check Docker containers
docker ps

# Check Open WebUI
curl http://localhost:3000

# Check Langflow
curl http://localhost:7860

# Test OCR
D:\SHARED\AI_Models\TOOLS\ocr_image_to_text.ps1 -ImagePath "image.png"

# Test PDF extraction
D:\SHARED\AI_Models\TOOLS\pdf_to_text.ps1 -PdfPath "document.pdf"
```

## Maintenance Commands

```powershell
# Start all services
docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml up -d

# Stop all services
docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml down

# View logs
docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml logs -f

# Pull new Ollama model
ollama pull <model-name>

# Update Docker images
docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml pull
docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml up -d

# Check disk usage
du -sh D:\SHARED\AI_Models\*
```

## Ralph Wiggum Technique

This installation was executed using the Ralph Wiggum iterative technique:
- Same prompt fed repeatedly to Claude Code
- Each iteration sees previous work in files
- Iteratively improved until completion
- State tracked in `.claude/ralph-loop.local.md`
- Completion signaled via `<promise>AI STACK COMPLETE</promise>`

The technique proved effective for this complex multi-step installation task, automatically recovering from Docker startup delays and handling parallel downloads.
