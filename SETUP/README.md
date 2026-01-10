# Local AI Stack - README

## Overview
This is a fully offline-capable local AI stack installed on Windows.

## Ports & Services

| Service      | URL                          | Description                    |
|--------------|------------------------------|--------------------------------|
| Ollama       | http://localhost:11434       | Local LLM API                  |
| Open WebUI   | http://localhost:3000        | ChatGPT-like web interface (v0.7.1) |
| Langflow     | http://localhost:7860        | Visual workflow builder        |
| MCP Filesystem | http://127.0.0.1:9101/docs | File read/write via MCP        |
| MCP Git      | http://127.0.0.1:9102/docs   | Git operations via MCP         |
| MCP Playwright | http://127.0.0.1:9103/docs | Browser automation (optional)  |
| Doc-Tools API | http://127.0.0.1:9201/docs  | OCR, PDF extraction, PDF-to-MD |

## Model Storage
All models and data are stored under: `D:\SHARED\AI_Models\`

- Ollama models: `D:\SHARED\AI_Models\ollama\models`
- HuggingFace cache: `D:\SHARED\AI_Models\hf`
- Torch cache: `D:\SHARED\AI_Models\torch`
- Open WebUI data: `D:\SHARED\AI_Models\openwebui\data`
- Langflow data: `D:\SHARED\AI_Models\langflow\data`

## Start/Stop Commands

### Start Docker Services
```powershell
cd D:\SHARED\AI_Models\SETUP
docker compose up -d
```

### Stop Docker Services
```powershell
cd D:\SHARED\AI_Models\SETUP
docker compose down
```

### Start Ollama (if not running)
```powershell
ollama serve
```

### Pull a new model
```powershell
ollama pull <model-name>
```

### List installed models
```powershell
ollama list
```

## Installed Ollama Models
- deepseek-r1:32b
- qwen3-coder:30b
- qwen2.5:14b
- qwen2.5vl:7b
- bge-m3:latest

## Verification Checklist

1. **Ollama running?**
   ```powershell
   curl http://localhost:11434
   # Should return "Ollama is running"
   ```

2. **Models installed?**
   ```powershell
   ollama list
   ```

3. **Open WebUI accessible?**
   Open http://localhost:3000 in browser

4. **Langflow accessible?**
   Open http://localhost:7860 in browser

5. **Docker containers running?**
   ```powershell
   docker ps
   ```

## TOOLS Directory
Helper scripts are in `D:\SHARED\AI_Models\TOOLS\`:

- `ocr_image_to_text.ps1` - OCR images with Tesseract
- `pdf_to_text.ps1` - Extract text from PDFs with Poppler
- `pdf_sanitize.ps1` - Repair/linearize PDFs with QPDF
- `pdf_to_md_marker.ps1` - Convert PDF to Markdown with Marker
- `pdf_to_md_mineru.ps1` - Convert PDF to Markdown/JSON with MinerU

## Environment Variables
These are set system-wide:
- `TR_AI_MODELS_DIR` = D:\SHARED\AI_Models
- `OLLAMA_MODELS` = D:\SHARED\AI_Models\ollama\models
- `HF_HOME` = D:\SHARED\AI_Models\hf
- `TRANSFORMERS_CACHE` = D:\SHARED\AI_Models\hf\transformers
- `TORCH_HOME` = D:\SHARED\AI_Models\torch
- `PIP_CACHE_DIR` = D:\SHARED\AI_Models\pip_cache

## MCP Toolchain

Tool servers exposing MCP (Model Context Protocol) capabilities via OpenAPI:

### Start MCP Servers
```powershell
D:\SHARED\AI_Models\MCP\start_mcp_toolchain.ps1
```

### Stop MCP Servers
```powershell
D:\SHARED\AI_Models\MCP\stop_mcp_toolchain.ps1
```

### Start Doc-Tools API
```powershell
D:\SHARED\AI_Models\OPENAPI\doc-tools\start_doc_tools_api.ps1
```

### Stop Doc-Tools API
```powershell
D:\SHARED\AI_Models\OPENAPI\doc-tools\stop_doc_tools_api.ps1
```

### Playwright Browser
Chromium v143.0.7499.4 is pre-installed for browser automation via MCP Playwright.
Location: `C:\Users\X\AppData\Local\ms-playwright\`

## SKILLS Library

Local Claude Skills-style system for AI assistants:
- Skills registry: `D:\SHARED\AI_Models\SKILLS\registry.json`
- Context packs: `D:\SHARED\AI_Models\SKILLS\packs\`
- Repo template: `D:\SHARED\AI_Models\SKILLS\repo_template\`

### Bootstrap a Repository
```powershell
D:\SHARED\AI_Models\SKILLS\scripts\bootstrap_repo.ps1 -TargetPath "C:\Projects\my-project"
```

See `D:\SHARED\AI_Models\SKILLS\README.md` for full documentation.

## Logs
Setup logs are stored in: `D:\SHARED\AI_Models\LOGS\`

## Troubleshooting

### Docker containers won't start
1. Ensure Docker Desktop is running
2. Check logs: `docker compose logs`
3. Try restarting: `docker compose down && docker compose up -d`

### Ollama models not pulling
1. Check disk space on D: drive
2. Ensure OLLAMA_MODELS env var is set
3. Try: `ollama pull <model>` manually

### Open WebUI can't connect to Ollama
1. Ensure Ollama is running: `curl http://localhost:11434`
2. Restart Open WebUI container
