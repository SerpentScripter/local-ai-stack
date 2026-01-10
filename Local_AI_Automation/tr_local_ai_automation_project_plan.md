# Project Plan: Local AI Automation Hub on ThreadRipper (TR)

## 1. Purpose and Goals

The goal of this project is to set up a **fully local, automated AI-driven workflow system** on a ThreadRipper (TR) workstation. The system should:

- Operate primarily **offline** (internet only for fetching emails, RSS/news, and external content).
- Use **local LLMs** for analysis, classification, extraction, and summarization.
- Automatically analyze incoming business emails, identify relevant consulting leads, and notify the user.
- Perform daily news scanning and produce compressed, role-relevant digests.
- Accept tasks/ideas from the user (via Slack or webhook) and process them autonomously.
- Deliver outputs and notifications primarily through a **private Slack workspace**.

Claude Code is expected to:
- Install and configure all components automatically.
- Create and test workflows end-to-end.
- Use the **Ralph Wiggum Loop** (iterate → observe → fix → repeat) until the system is fully operational.
- Minimize user interaction and avoid asking for input unless strictly necessary.

---

## 2. Target Environment

**Host System**
- OS: Windows 11
- Hardware:
  - CPU: AMD ThreadRipper
  - GPU: NVIDIA RTX 4090 (24GB VRAM)
  - RAM: 64GB+

**Execution Environment**
- WSL2 (Ubuntu LTS)
- Docker + Docker Compose

Claude Code should assume:
- Administrator access is available.
- Docker and WSL2 can be installed if missing.

---

## 3. Core Components

### 3.1 Orchestration
- **n8n (self-hosted, Docker)**
  - Central workflow engine
  - Handles triggers, routing, scheduling, and notifications

### 3.2 Local AI
- **Ollama or LM Studio (local API mode)**
  - Primary LLM execution
  - Models should be selected automatically based on availability and VRAM
  - Prefer strong reasoning + extraction models

Optional (if useful):
- Embeddings model for semantic matching
- Vector DB (Qdrant or Chroma) for profile/context storage

### 3.3 Communication & Notification
- **Slack (private workspace)**
  - Incoming Webhooks
  - Bot user for posting messages
  - Mobile notifications enabled

### 3.4 Storage
- Local filesystem (project directory)
- Structured outputs:
  - `/data/leads/` (JSON + Markdown)
  - `/data/tasks/`
  - `/data/digests/`
  - `/data/logs/`

---

## 4. Functional Workflows

### 4.1 Email Analysis & Lead Detection

**Trigger**
- Poll incoming business email via IMAP or Microsoft Graph (auto-detect best option).

**Processing**
- Clean email content (remove signatures, threads).
- Detect sender category:
  - Known consulting brokers / lead sources
  - Customer
  - Newsletter
  - Unknown

**LLM Tasks (Local)**
- Classify email category.
- If consulting lead:
  - Extract structured fields:
    - Role
    - Industry
    - Location / Remote
    - Duration
    - Start date
    - Required skills & certifications
    - Rate (if available)
  - Score relevance (0–100) against local profile.
  - Generate short justification.

**Output**
- High-score leads:
  - Save JSON + Markdown summary
  - Post to Slack channel `#leads-consulting`
- Low-score leads:
  - Archive and optionally post to `#leads-lowmatch`

---

### 4.2 General Email Triage

LLM-based classification into:
- Action Required
- FYI / Read Later
- Finance / Invoice
- Meetings / Calendar
- Newsletter (Relevant / Irrelevant)
- Spam

Actions:
- Apply labels/folders if supported
- Post summaries of important items to Slack

---

### 4.3 Daily News Digest

**Sources**
- RSS feeds
- Keyword-based web search

Focus Areas:
- AI tooling (Claude Code, Codex, Gemini CLI, agent frameworks)
- Information Security
- GRC, DORA, NIS2, ISO 27001
- Cloud & Azure security

**LLM Tasks**
- De-duplicate articles
- Summarize each item in 1–2 sentences
- Explain relevance to consulting work

**Output**
- Daily Slack post to:
  - `#digest-ai`
  - `#digest-grc`
- Markdown digest saved locally

---

#### 4.4 Slack Backlog Channel (Interactive Backlog / To-Do)

**Core Requirement**
- A dedicated Slack channel (recommended name: `#backlog`) acts as the single shared **backlog/to-do list**.
- The local AI agent **continuously monitors** this channel.
- The agent must:
  - Interpret each user message as a potential backlog item.
  - Ask **clarifying questions** (in-thread) whenever the intent, scope, acceptance criteria, or priority is unclear.
  - Convert the message into one or more structured backlog items.
  - Categorize each backlog item using **local LLM** classification.
  - Support dynamic reprioritization when the user explicitly indicates urgency.

**Non-Deletion / Audit Trail**
- **Nothing is ever deleted** from the backlog, including completed items.
- Completed items are retained with status updates (e.g., `Done`) and timestamps.
- The system must maintain a full historical log of edits, clarifications, and status changes.

**Scope of Backlog Items**
Backlog entries can be:
- Private or personal tasks
- Work/client assignments
- Software development tasks
- New app ideas
- Sales material, proposals, presentations
- Research, reading lists, procurement

**Input Channels**
- Primary: Slack channel `#backlog`
- Optional:
  - Slack DM to bot (treated the same as backlog input)
  - Webhook endpoint for mobile voice-to-text ingestion

**LLM Tasks (Local)**
For each candidate backlog message, the agent should produce:
- `title` (short)
- `description`
- `category` (single primary + optional secondary tags)
- `priority` (P0–P3)
- `type` (personal | work | mixed)
- `next_action` (one concrete next step)
- `estimated_effort` (S/M/L) (optional)
- `dependencies` (optional)
- `clarifying_questions[]` (if needed)

**Categories (initial taxonomy; expand as needed)**
- Consulting Lead / Sales
- Client Delivery
- Security / GRC
- AI / Automation
- Software / App Dev
- Ops / Admin / Finance
- Learning / Research
- Personal

**Priority Rules**
- Default priority: P2.
- If user says explicit urgency (e.g., “super important”, “P0”, “urgent”, “drop everything”), set P0.
- If user says low urgency (“nice to have”, “later”), set P3.
- Priorities can be changed later by explicit user instruction.

**Data Model & Persistence**
- Store backlog items in a durable local database (prefer SQLite) and also export to:
  - `/data/backlog/backlog.jsonl` (append-only)
  - `/data/backlog/backlog.md` (human-readable view)
- Maintain stable IDs for every item.
- All edits should be logged as events (event-sourcing style preferred).

**Slack UX**
- When a new item is created:
  - Reply in-thread with a short confirmation + extracted fields.
  - If clarification is needed, ask questions in-thread and mark item status as `Needs Clarification`.
- When the user answers clarification questions:
  - Update the existing backlog item (do not create duplicates).
- Provide lightweight commands (via bot message patterns if slash commands are not feasible):
  - `priority P0/P1/P2/P3 for <id>`
  - `done <id>`
  - `list top 10` / `list P0` / `list category <name>`

**Safe Automation Policy**
- The agent may auto-execute **safe** tasks (summaries, drafts, research) and post outputs.
- Any action that sends email, commits code, touches finances, or changes external systems must require explicit user approval (Slack confirmation step).

**Output Channels**
- New/updated backlog items: `#backlog`
- Status updates: `#tasks-status`
- Errors/health: `#system-alerts`

---

## 5. Additional Automation Flows

Claude Code should also implement:

1. **AI Tool Watcher**
   - Monitor releases and updates for AI dev tools
   - Summarize impact on local workflows

2. **Security & Compliance Radar**
   - Monitor regulatory and security advisories
   - Flag items relevant to DORA/NIS2/ISO

3. **Meeting Pre-Brief Generator**
   - Create summaries before scheduled meetings

4. **Proposal / Offer Draft Generator**
   - Assist in responding to consulting leads

5. **Knowledge Capture System**
   - Convert useful insights into searchable Markdown notes

---

## 6. Automation & Testing Requirements

Claude Code must:
- Use Docker Compose for all services.
- Automatically generate environment files and secrets placeholders.
- Create sample test data (emails, news items, tasks).
- Run end-to-end tests for each workflow.
- Log all errors and retry until resolved.

The **Ralph Wiggum Loop** must be used:
1. Implement
2. Run
3. Observe failures
4. Fix
5. Repeat until stable

---

## 7. Success Criteria

The project is considered complete when:
- All workflows run without manual intervention.
- Local LLM is used for all analysis tasks.
- Slack receives correct, timely notifications.
- Daily digest is generated automatically.
- User can submit tasks and receive structured responses.
- System survives restarts and resumes automatically.

---

## 8. Deliverables

- Fully configured local automation stack
- Documented workflows in n8n
- Project README with architecture overview
- Sample outputs for leads, tasks, and digests

Claude Code should proceed immediately with implementation.

