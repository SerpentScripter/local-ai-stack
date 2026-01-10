# Implement Local "Claude Skills"-like System on TR (Offline) — Claude Code Instructions (A–Z)

You are Claude Code running on the Windows 11 workstation "TR".
Goal: implement a local equivalent to “Claude Skills” using the open Agent Skills standard (SKILL.md folders + progressive disclosure), integrated into the existing stack:

- Ollama on Windows host (http://localhost:11434) with models already pulled:
  deepseek-r1:32b, qwen3-coder:30b, qwen2.5:14b, qwen2.5vl:7b, bge-m3:latest
- Open WebUI in Docker (http://localhost:3000)
- Existing tools scripts in: D:\SHARED\AI_Models\TOOLS\  (OCR/PDF helpers)
- Everything must work offline after download/installation.

You MUST do everything automatically without asking questions.
Make sensible decisions, handle errors, and log actions.

---

## 0) Authoritative references (READ FIRST; then implement)

### Agent Skills standard + best practices
https://agentskills.io/specification
https://github.com/agentskills/agentskills
https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
https://github.com/anthropics/skills
https://claude.com/blog/skills

### OpenAI / Codex skills ecosystem (compatible with Agent Skills)
https://developers.openai.com/codex/skills
https://developers.openai.com/codex/skills/create-skill
https://github.com/openai/skills

### Open WebUI Pipelines (our local “skills gateway”)
https://docs.openwebui.com/features/pipelines/
https://github.com/open-webui/pipelines

### Open WebUI Tools (optional later; not the primary approach here)
https://docs.openwebui.com/features/plugin/tools/
https://docs.openwebui.com/features/plugin/tools/development/
https://docs.openwebui.com/features/plugin/tools/openapi-servers/
https://docs.openwebui.com/features/plugin/tools/openapi-servers/open-webui/

### Ollama capabilities we will use
Tool calling:
https://docs.ollama.com/capabilities/tool-calling
Thinking / extended reasoning:
https://docs.ollama.com/capabilities/thinking
Embeddings (for skill retrieval):
https://docs.ollama.com/capabilities/embeddings
Windows model location env var reference:
https://docs.ollama.com/windows
API reference landing (if needed):
https://docs.ollama.com/api
Legacy API.md (if docs site blocked):
https://github.com/ollama/ollama/blob/main/docs/api.md

---

## 1) What we are building (architecture)

We will implement a local OpenAI-compatible “gateway” using Open WebUI Pipelines, running NATIVELY on Windows (not in Docker) so it can call:
- Ollama API (localhost:11434)
- Local PowerShell tools in D:\SHARED\AI_Models\TOOLS\*.ps1

Flow:
Open WebUI (Docker) -> Pipelines server (Windows host, port 9099) -> Ollama (Windows host, 11434)

Why this matches “Claude Skills”:
- We will store skills as folders with SKILL.md (Agent Skills standard).
- Gateway preloads name+description of all skills into system prompt.
- Gateway dynamically loads full SKILL.md (and referenced files) only when triggered (“progressive disclosure”).
- Gateway exposes local scripts as tool-calls via Ollama Tool Calling.

---

## 2) Create folders under D:\SHARED\AI_Models\

Ensure these exist:

D:\SHARED\AI_Models\SKILLS\
D:\SHARED\AI_Models\SKILLS\_index\
D:\SHARED\AI_Models\SKILLS\_logs\
D:\SHARED\AI_Models\SKILLS\_templates\
D:\SHARED\AI_Models\pipelines\
D:\SHARED\AI_Models\pipelines\pipelines\   (the directory Pipelines server loads)
D:\SHARED\AI_Models\venvs\pipelines\
D:\SHARED\AI_Models\SETUP\skills_setup.ps1
D:\SHARED\AI_Models\SETUP\skills_README.md

Also create a git mirror cache:
D:\SHARED\AI_Models\git_mirrors\

---

## 3) Download / mirror the key repos (so system can run offline later)

Mirror these with git (prefer --mirror), into D:\SHARED\AI_Models\git_mirrors\ :

- https://github.com/open-webui/pipelines
- https://github.com/agentskills/agentskills
- https://github.com/anthropics/skills
- https://github.com/openai/skills

Then clone working copies into:
D:\SHARED\AI_Models\pipelines\src\open-webui-pipelines\
D:\SHARED\AI_Models\SKILLS\_templates\anthropic_skills_repo\
D:\SHARED\AI_Models\SKILLS\_templates\openai_skills_repo\

If GitHub UI pages fail to render, use git directly.

---

## 4) Install/run Open WebUI Pipelines server on Windows host (port 9099, localhost only)

Follow the Pipelines docs/repo:
- https://docs.openwebui.com/features/pipelines/
- https://github.com/open-webui/pipelines

Implementation requirements:
- Run it as a Windows-host process bound to 127.0.0.1:9099 (NOT exposed on LAN)
- Use a venv at: D:\SHARED\AI_Models\venvs\pipelines\
- Configure it to load pipeline files from: D:\SHARED\AI_Models\pipelines\pipelines\
- Set a local API key (default in docs is "0p3n-w3bu!", you may keep or rotate; store in a local env file)

Steps:
1) Create venv: python -m venv D:\SHARED\AI_Models\venvs\pipelines
2) Activate, install Pipelines requirements (from cloned repo).
3) Start server using Pipelines’ recommended start command/scripts (repo includes scripts; prefer Windows-friendly).
4) Verify:
   - curl http://localhost:9099/v1/models (or equivalent)
   - curl http://localhost:9099 (if root returns something)

If Pipelines requires env vars:
- PIPELINES_DIR = D:\SHARED\AI_Models\pipelines\pipelines
- PIPELINES_API_KEY = <key>

(Use the repo/docs as source of truth.)

---

## 5) Connect Open WebUI (Docker) to Pipelines server

According to Pipelines docs, Open WebUI should point to the Pipelines URL and API key.
Because Open WebUI is in Docker, use host.docker.internal:

Open WebUI UI steps (do these programmatically if feasible; otherwise document them clearly in skills_README.md):
- In Open WebUI Settings → Connections → OpenAI:
  - API URL: http://host.docker.internal:9099
  - API Key: <PIPELINES_API_KEY>

Also keep existing Ollama connection.

Reference:
https://docs.openwebui.com/features/pipelines/

---

## 6) Implement the local Skills library (Agent Skills format)

### 6.1 Skill format requirements
Follow the Agent Skills spec:
https://agentskills.io/specification

Each skill is a folder:
D:\SHARED\AI_Models\SKILLS\<skill-name>\
  SKILL.md (required YAML frontmatter + markdown body)
  scripts\ (optional)
  references\ (optional)
  assets\ (optional)

You must include at least these starter skills (create them yourself; do not depend on internet later):
1) pdf-processing
2) ocr-image-to-text
3) it-audit-assistant
4) dora-nis2-control-mapper
5) rag-local-md-notes

Each SKILL.md must include:
- YAML frontmatter: name + description (and add license, metadata)
- In the body: “When to use”, “Inputs”, “Procedure”, “Tool calls”, “Outputs”, “Common pitfalls”.

Use progressive disclosure:
- Keep SKILL.md concise
- Put long checklists/templates into references/*.md and reference them from SKILL.md.

### 6.2 Bind skills to existing local tools
Map these existing PowerShell tools into skill tool-calls:
- D:\SHARED\AI_Models\TOOLS\ocr_image_to_text.ps1
- D:\SHARED\AI_Models\TOOLS\pdf_to_text.ps1
- D:\SHARED\AI_Models\TOOLS\pdf_sanitize.ps1
- D:\SHARED\AI_Models\TOOLS\pdf_to_md_marker.ps1

(If MinerU is unreliable, do not depend on it by default.)

---

## 7) Build a “Skills Gateway” pipeline for Pipelines server

Create:
D:\SHARED\AI_Models\pipelines\pipelines\agent_skills_gateway.py

This pipeline must:
A) On startup:
   - Scan D:\SHARED\AI_Models\SKILLS\ for all skill folders
   - Parse each SKILL.md frontmatter (name, description, metadata)
   - Precompute embeddings for each skill using Ollama embeddings model bge-m3:
     - POST http://localhost:11434/api/embed
     - model: "bge-m3"
     - input: text (skill name + description + tags)
     - store vectors in: D:\SHARED\AI_Models\SKILLS\_index\skills_index.json
   Reference embeddings docs:
   https://docs.ollama.com/capabilities/embeddings

B) For each chat request:
   1) Determine routing/model choice:
      - If image present => prefer qwen2.5vl:7b
      - If code-focused => prefer qwen3-coder:30b
      - Else reasoning => prefer deepseek-r1:32b (thinking enabled)
   2) Retrieve top-K relevant skills:
      - Embed user query via /api/embed (bge-m3)
      - cosine similarity with cached skill vectors
      - choose top 3 above threshold
   3) Construct system prompt:
      - Always include a “Skill Catalog” listing ALL skills by name+description (short)
      - If triggered skills found: include full SKILL.md for those skills
      - If SKILL.md references files in references/, load them only if explicitly needed (progressive disclosure)
   4) Enable Ollama “thinking” for supported models:
      - Set think=true for deepseek-r1 and qwen3
      Reference:
      https://docs.ollama.com/capabilities/thinking
   5) Enable Ollama Tool Calling:
      - Provide tool schemas for:
        - ocr_image_to_text(image_path)
        - pdf_to_text(pdf_path)
        - pdf_sanitize(pdf_path)
        - pdf_to_md_marker(pdf_path)
        - read_file(path)
        - write_file(path, content)
        - list_dir(path)
      Reference:
      https://docs.ollama.com/capabilities/tool-calling

C) Tool execution:
   - When Ollama returns tool_calls, execute them on Windows using PowerShell subprocess calls (for the TOOLS scripts).
   - Enforce path allowlist:
     - allow ONLY under D:\SHARED\AI_Models\ and a temporary working folder: D:\SHARED\AI_Models\cache\work\
   - Return tool outputs back to Ollama as tool messages.
   - Loop until no more tool calls or max 6 tool iterations.

D) Logging:
   - Log every request/skill selection/tool call to:
     D:\SHARED\AI_Models\SKILLS\_logs\gateway_YYYYMMDD.log
   - Never log sensitive document contents unless explicitly configured.

E) Offline guarantee:
   - No network calls except localhost (Ollama / local services).
   - Disable any “web search” tool. This is offline-only.

Use upstream examples for pipeline structure (if needed):
- Repo: https://github.com/open-webui/pipelines
- If you want to reference raw examples:
  https://raw.githubusercontent.com/open-webui/pipelines/main/examples/filters/function_calling_filter_pipeline.py
  https://raw.githubusercontent.com/open-webui/pipelines/main/examples/pipelines/rag/llamaindex_pipeline.py
If these paths are outdated, use the cloned repo locally and search for “class Pipeline” and examples folder.

---

## 8) Add a one-shot PowerShell installer for this skills system

Create:
D:\SHARED\AI_Models\SETUP\skills_setup.ps1

The script must:
1) Self-elevate if needed
2) Create folders (Section 2)
3) Mirror/clone repos (Section 3)
4) Create venv and install Pipelines server (Section 4)
5) Write the agent_skills_gateway.py pipeline file (Section 7)
6) Create starter skills (Section 6)
7) Build the skills embeddings index once
8) Start Pipelines server in background (new terminal or scheduled task)
9) Create a Windows Scheduled Task:
   - Name: "TR Local AI Pipelines"
   - Trigger: At logon
   - Action: start Pipelines server
   - Ensure it starts minimized and restarts on failure (best effort)
10) Verify:
   - curl http://localhost:9099 (or /v1/models)
   - run a tool-call test by sending a request through Pipelines to Ollama (can be a small internal test harness)

The script must write a clear report to:
D:\SHARED\AI_Models\SKILLS\_logs\skills_setup_report.md

---

## 9) Verification checklist (automate as much as possible)

After running skills_setup.ps1, validate:

A) Pipelines server reachable on host:
- curl http://localhost:9099
- curl http://localhost:9099/v1/models

B) From inside Open WebUI container, host gateway reachable:
- docker exec -it open-webui sh -lc "apk add --no-cache curl || true; curl -s http://host.docker.internal:9099/v1/models | head"

C) Tool calling works:
- Send a prompt that forces using pdf_to_text.ps1 on a test PDF placed in D:\SHARED\AI_Models\cache\work\
- Confirm the tool is called and result used in final answer.

D) Swedish:
- Run OCR with `eng+swe` (already configured in tool script) and ask Swedish questions about extracted text.

---

## 10) Deliverables

When complete, ensure these exist:
- D:\SHARED\AI_Models\SETUP\skills_setup.ps1
- D:\SHARED\AI_Models\pipelines\pipelines\agent_skills_gateway.py
- D:\SHARED\AI_Models\SKILLS\<starter-skill-folders>\SKILL.md
- D:\SHARED\AI_Models\SKILLS\_index\skills_index.json
- D:\SHARED\AI_Models\SKILLS\_logs\skills_setup_report.md
- D:\SHARED\AI_Models\SETUP\skills_README.md (how to use, how to add skills, troubleshooting)

Completion message:
<promise>LOCAL SKILLS SYSTEM COMPLETE</promise>
