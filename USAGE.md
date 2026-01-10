# Local AI Stack - Usage Guide

## Quick Start

After installation, your local AI stack is ready to use:

1. **Hub Dashboard** (Central Management): http://localhost:8765
2. **Open WebUI** (ChatGPT-like interface): http://localhost:3000 (Default)
3. **Langflow** (Visual workflow builder): http://localhost:7860 (Default)
4. **Ollama API** (Direct API access): http://localhost:11434 (Default)

*Note: If you have port conflicts, you can change these in the `.env` file at the root of the project.*

## Starting Services

### After System Reboot

1. **Start Docker Desktop** (if not set to auto-start)
2. **Wait 60 seconds** for Docker to initialize
3. **Start Docker services:**
   ```powershell
   docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml up -d
   ```
4. **Ollama starts automatically** with Windows (or run `ollama serve`)

### Port Configuration
If you have other applications running on the same machine that use these ports, you can modify them in the `.env` file:
```env
OPEN_WEBUI_PORT=3000
N8N_PORT=5678
LANGFLOW_PORT=7860
BACKLOG_API_PORT=8765
OLLAMA_PORT=11434
```
After changing ports in `.env`, restart the services for the changes to take effect.

### Quick Start Script

Create a shortcut to this command:
```powershell
Start-Process "Docker Desktop" -ErrorAction SilentlyContinue
Start-Sleep 60
docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml up -d
Start-Process "http://localhost:3000"
```

## Using Open WebUI

### First Time Setup
1. Navigate to http://localhost:3000
2. No login required (authentication disabled for local use)
3. Select a model from the dropdown (e.g., "qwen2.5:14b")
4. Start chatting!

### Model Selection Guide

| Model | Best For | VRAM Usage |
|-------|----------|------------|
| deepseek-r1:32b | Complex reasoning, analysis | ~20GB |
| qwen3-coder:30b | Code generation, debugging | ~18GB |
| qwen2.5:14b | General chat, fast responses | ~10GB |
| qwen2.5vl:7b | Image understanding | ~8GB |
| bge-m3:latest | Embeddings (for RAG) | ~1GB |

### Tips
- Use `qwen2.5:14b` for fast general conversations
- Switch to `deepseek-r1:32b` for complex reasoning tasks
- Use `qwen2.5vl:7b` when you need to analyze images
- Use `qwen3-coder:30b` for code-related tasks

### Image Analysis
1. Select `qwen2.5vl:7b` model
2. Click the attachment icon
3. Upload an image
4. Ask questions about the image

### Document Chat
1. Click the "+" button to create a new workspace
2. Upload documents (PDF, TXT, etc.)
3. Open WebUI will create embeddings using bge-m3
4. Ask questions about your documents

## Using Langflow

### What is Langflow?
Langflow is a visual tool for building AI workflows and agents. Think of it as "Zapier for AI" - you connect blocks to create complex AI pipelines.

### Getting Started
1. Navigate to http://localhost:7860
2. Click "New Flow" to start
3. Drag components from the sidebar
4. Connect them together
5. Click "Run" to test

### Example Flows

#### Simple Chat Flow
1. Add "Chat Input" component
2. Add "Ollama" component (set model to qwen2.5:14b)
3. Add "Chat Output" component
4. Connect: Input → Ollama → Output

#### RAG (Document Q&A) Flow
1. Add "File" component (upload documents)
2. Add "Text Splitter" component
3. Add "Ollama Embeddings" (use bge-m3)
4. Add "Vector Store" component
5. Add "Retriever" component
6. Add "Ollama" for generation
7. Connect components to create the pipeline

### Langflow + Ollama Configuration
When adding an Ollama component in Langflow:
- **Base URL**: `http://host.docker.internal:11434`
- **Model**: Select from your installed models

## Using Ollama Directly

### Command Line

```powershell
# Chat with a model
ollama run qwen2.5:14b

# Run with a specific prompt
ollama run qwen2.5:14b "Explain quantum computing"

# List installed models
ollama list

# Pull a new model
ollama pull llama3.2:latest

# Remove a model
ollama rm <model-name>

# Show model info
ollama show qwen2.5:14b
```

### API Access

```powershell
# Generate completion
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5:14b",
  "prompt": "Hello, world!"
}'

# Chat completion
curl http://localhost:11434/api/chat -d '{
  "model": "qwen2.5:14b",
  "messages": [{"role": "user", "content": "Hello!"}]
}'

# List models
curl http://localhost:11434/api/tags

# Generate embeddings
curl http://localhost:11434/api/embeddings -d '{
  "model": "bge-m3:latest",
  "prompt": "Text to embed"
}'
```

### Python Integration

```python
import requests

def chat(prompt, model="qwen2.5:14b"):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False}
    )
    return response.json()["response"]

# Usage
answer = chat("What is the capital of France?")
print(answer)
```

### Using with LangChain

```python
from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings

# LLM
llm = Ollama(model="qwen2.5:14b", base_url="http://localhost:11434")
response = llm.invoke("Hello!")

# Embeddings
embeddings = OllamaEmbeddings(model="bge-m3", base_url="http://localhost:11434")
vector = embeddings.embed_query("Hello world")
```

## Using the TOOLS Scripts

### OCR: Extract Text from Images

```powershell
# Basic usage (English + Swedish)
D:\SHARED\AI_Models\TOOLS\ocr_image_to_text.ps1 -ImagePath "C:\path\to\image.png"

# Specify language
D:\SHARED\AI_Models\TOOLS\ocr_image_to_text.ps1 -ImagePath "image.png" -Lang "eng"

# Multiple languages
D:\SHARED\AI_Models\TOOLS\ocr_image_to_text.ps1 -ImagePath "image.png" -Lang "eng+fra+deu"
```

### PDF: Extract Text

```powershell
# Extract text from PDF
D:\SHARED\AI_Models\TOOLS\pdf_to_text.ps1 -PdfPath "C:\path\to\document.pdf"

# Output to file
D:\SHARED\AI_Models\TOOLS\pdf_to_text.ps1 -PdfPath "document.pdf" > output.txt
```

### PDF: Sanitize/Repair

```powershell
# Repair a corrupted PDF
D:\SHARED\AI_Models\TOOLS\pdf_sanitize.ps1 -PdfPath "C:\path\to\broken.pdf"

# Specify output path
D:\SHARED\AI_Models\TOOLS\pdf_sanitize.ps1 -PdfPath "broken.pdf" -OutputPath "fixed.pdf"
```

### PDF: Convert to Markdown

```powershell
# Using Marker (recommended)
D:\SHARED\AI_Models\TOOLS\pdf_to_md_marker.ps1 -PdfPath "C:\path\to\document.pdf"

# Specify output directory
D:\SHARED\AI_Models\TOOLS\pdf_to_md_marker.ps1 -PdfPath "document.pdf" -OutputDir "C:\output"

# Using MinerU (if installed)
D:\SHARED\AI_Models\TOOLS\pdf_to_md_mineru.ps1 -PdfPath "document.pdf"
```

## Advanced Usage

### Running Multiple Models

Ollama can run multiple models, but large models may need to be unloaded first:
```powershell
# Check what's loaded
curl http://localhost:11434/api/ps

# The 24GB RTX 4090 can typically run:
# - One 32B model, OR
# - Multiple smaller models simultaneously
```

### Custom Model Parameters

In Open WebUI, click the gear icon to adjust:
- **Temperature**: Higher = more creative (0.0-2.0)
- **Top P**: Nucleus sampling threshold
- **Context Length**: How much text to remember
- **System Prompt**: Define AI behavior

### Creating Custom Models

```powershell
# Create a Modelfile
@"
FROM qwen2.5:14b
SYSTEM You are a helpful coding assistant specializing in Python.
PARAMETER temperature 0.3
"@ | Out-File -FilePath Modelfile -Encoding utf8

# Create the model
ollama create python-helper -f Modelfile

# Use it
ollama run python-helper
```

### Backing Up Your Data

```powershell
# Models (optional - can re-download)
# Location: D:\SHARED\AI_Models\ollama\models

# Open WebUI data (conversations, settings)
Copy-Item -Recurse D:\SHARED\AI_Models\openwebui\data backup\openwebui

# Langflow flows
Copy-Item -Recurse D:\SHARED\AI_Models\langflow\data backup\langflow
```

## Troubleshooting

### Open WebUI Shows "No Models Available"

1. Check Ollama is running:
   ```powershell
   curl http://localhost:11434
   ```
2. Restart Open WebUI:
   ```powershell
   docker restart open-webui
   ```

### Langflow Won't Start

1. Check PostgreSQL is running:
   ```powershell
   docker logs langflow-db
   ```
2. Restart Langflow:
   ```powershell
   docker restart langflow
   ```

### Model Responses Are Slow

1. Check GPU is being used:
   ```powershell
   nvidia-smi
   ```
2. Try a smaller model (qwen2.5:14b instead of deepseek-r1:32b)

### Out of VRAM

1. Use a smaller model
2. Reduce context length in model settings
3. Restart Ollama to clear memory:
   ```powershell
   taskkill /f /im ollama.exe
   ollama serve
   ```

### Docker Containers Keep Restarting

1. Check logs:
   ```powershell
   docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml logs -f
   ```
2. Check disk space on D: drive
3. Restart Docker Desktop

### Services Not Accessible After Reboot

1. Ensure Docker Desktop is running
2. Wait 60 seconds for Docker to initialize
3. Start services:
   ```powershell
   docker compose -f D:\SHARED\AI_Models\SETUP\docker-compose.yml up -d
   ```

## Updating

### Update Docker Images

```powershell
cd D:\SHARED\AI_Models\SETUP
docker compose pull
docker compose up -d
```

### Update Ollama Models

```powershell
ollama pull deepseek-r1:32b
ollama pull qwen2.5:14b
# etc.
```

### Check for New Models

Visit https://ollama.com/library for available models.

## Disk Space Management

Check usage:
```powershell
# Ollama models
Get-ChildItem D:\SHARED\AI_Models\ollama\models -Recurse | Measure-Object -Property Length -Sum

# Docker volumes
docker system df

# Total AI Models directory
Get-ChildItem D:\SHARED\AI_Models -Recurse | Measure-Object -Property Length -Sum
```

Clean up:
```powershell
# Remove unused Docker images
docker image prune -a

# Remove a specific Ollama model
ollama rm <model-name>

# Clear pip cache
Remove-Item D:\SHARED\AI_Models\pip_cache\* -Recurse
```

## Security Notes

- All services bind to `127.0.0.1` only - not accessible from network
- No authentication enabled on Open WebUI (local use only)
- Langflow uses default PostgreSQL credentials (local only)
- To expose to network, update docker-compose.yml ports and enable authentication
