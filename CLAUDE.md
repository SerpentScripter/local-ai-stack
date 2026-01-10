# Local AI Stack Installation Project

## Project Purpose
Automated installation and configuration of a fully offline-capable local AI stack on Windows, including:
- Ollama with GPU-accelerated LLM inference
- Open WebUI (ChatGPT-like interface)
- Langflow (visual workflow builder)
- OCR and PDF processing tools

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `D:\SHARED\AI_Models\` | Root directory for all AI assets |
| `D:\SHARED\AI_Models\SETUP\` | Installation scripts and Docker config |
| `D:\SHARED\AI_Models\TOOLS\` | Helper scripts for OCR/PDF processing |
| `D:\SHARED\AI_Models\ollama\models\` | Ollama model storage |
| `D:\SHARED\AI_Models\venvs\doc-tools\` | Python venv for document tools |

## Key Files

| File | Purpose |
|------|---------|
| `instructions.md` | Master installation instructions for Claude Code |
| `results.md` | Documentation of completed installation |
| `USAGE.md` | Comprehensive usage guide for end users |
| `D:\SHARED\AI_Models\SETUP\setup.ps1` | PowerShell master installer |
| `D:\SHARED\AI_Models\SETUP\docker-compose.yml` | Docker services configuration |

## Service Ports

- **Ollama**: http://localhost:11434
- **Open WebUI**: http://localhost:3000
- **Langflow**: http://localhost:7860

## Running the Installation

To repeat this installation on a new machine:
1. Copy this project to the target machine
2. Have Claude Code read `instructions.md`
3. Claude Code will execute all steps automatically

Or run manually:
```powershell
powershell -ExecutionPolicy Bypass -File "D:\SHARED\AI_Models\SETUP\setup.ps1"
```

## Important Notes

- All services bind to 127.0.0.1 only (not exposed to network)
- Ollama runs natively on Windows for GPU access
- Docker containers connect to Ollama via `host.docker.internal:11434`
- Environment variables redirect all caches to `D:\SHARED\AI_Models\`
- Total storage requirement: ~100GB (models + containers + caches)

## Maintenance Commands

```powershell
# Start services
docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml up -d

# Stop services
docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml down

# Check status
docker ps
ollama list
```
