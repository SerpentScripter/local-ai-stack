# Local AI Stack - Improvement Plan

**Created:** 2026-01-10
**Updated:** 2026-01-10
**Status:** Phase 1 & 2 COMPLETE

---

## Executive Summary

The local AI stack is **75% production-ready** with 6 of 8 components fully functional. This plan addresses identified gaps and proposes enhancements across security, reliability, performance, and usability.

---

## Phase 1: Critical Fixes (Immediate) ✅ COMPLETE

### 1.1 Create Missing Stop Script ✅
**Priority:** HIGH | **Effort:** 15 min | **Status:** DONE

**Issue:** `stop_doc_tools_api.ps1` is referenced in documentation but doesn't exist.

**Completed:**
- Enhanced `D:\SHARED\AI_Models\OPENAPI\doc-tools\stop_doc_tools_api.ps1`
- Added orphan process detection and port verification

---

### 1.2 Rotate Default API Keys ✅
**Priority:** HIGH | **Effort:** 30 min | **Status:** DONE

**Issue:** Default Pipelines API key (`0p3n-w3bu!`) is publicly known.

**Completed:**
- Generated new secure API key (64-char hex)
- Updated `D:\SHARED\AI_Models\pipelines\.env`
- Created `D:\SHARED\AI_Models\TOOLS\generate_api_key.ps1` utility
- Documented in `D:\SHARED\AI_Models\LOGS\api_key_rotation_20260110.md`

---

### 1.3 Add QPDF to System PATH ✅
**Priority:** MEDIUM | **Effort:** 10 min | **Status:** DONE

**Issue:** pdf_sanitize.ps1 searches multiple paths for QPDF.

**Completed:**
- Created `D:\SHARED\AI_Models\TOOLS\add_qpdf_to_path.ps1`
- Added QPDF to user PATH (system PATH requires admin)

---

## Phase 2: Reliability Improvements (Week 1) ✅ COMPLETE

### 2.1 Unified Service Manager ✅
**Priority:** HIGH | **Effort:** 2 hours | **Status:** DONE

**Completed:**
- Created `D:\SHARED\AI_Models\service_manager.ps1`
- Supports: start, stop, restart, status actions
- Services: all, mcp, doc-tools, pipelines, docker, ollama
- Port-based health verification

**Usage:**
```powershell
.\service_manager.ps1 -Action start -Service all
.\service_manager.ps1 -Action stop -Service mcp
.\service_manager.ps1 -Action status
.\service_manager.ps1 -Action restart -Service doc-tools
```

**Features:**
- Start/stop all services with single command
- Dependency ordering (start Ollama before Pipelines)
- Health check verification after start
- Graceful shutdown with timeout
- Status dashboard output

---

### 2.2 Automated Test Suite ✅
**Priority:** HIGH | **Effort:** 3 hours | **Status:** DONE

**Completed:**
- Created `D:\SHARED\AI_Models\TOOLS\run_tests.ps1`
- 18 automated tests covering all components
- 100% pass rate achieved
- Supports console, markdown, JSON output formats

**Test Matrix:**
| Component | Test Type | Sample Input |
|-----------|-----------|--------------|
| ocr_image_to_text | Integration | test_image.png |
| pdf_to_text | Integration | test_document.pdf |
| pdf_sanitize | Integration | corrupt_sample.pdf |
| pdf_to_md_marker | Integration | multipage.pdf |
| MCP Filesystem | API | GET /openapi.json |
| MCP Git | API | GET /openapi.json |
| Doc-Tools API | API | POST /pdf/text |
| Pipelines | API | GET /v1/models |

---

### 2.3 Health Check Monitoring ✅
**Priority:** MEDIUM | **Effort:** 2 hours | **Status:** DONE

**Completed:**
- Created `D:\SHARED\AI_Models\TOOLS\health_check.ps1`
- Checks all 8 services + 3 Docker containers + disk space + Ollama models
- Supports JSON output, log appending, Windows notifications
- Critical vs non-critical service classification

---

### 2.4 Pre-download Marker Models ✅
**Priority:** MEDIUM | **Effort:** 30 min | **Status:** DONE

**Completed:**
- Created `D:\SHARED\AI_Models\TOOLS\warmup_marker.ps1`
- Downloads ~1.35GB of ML models for offline use
- Run after initial setup to avoid first-run delays

---

## Phase 3: Performance Optimization (Week 2)

### 3.1 Async RAG Embeddings
**Priority:** HIGH | **Effort:** 4 hours

**Issue:** RAG Notes skill times out due to synchronous embedding calls.

**Current Flow:**
```
Query → Embed query → For each note: embed → compare → timeout
```

**Improved Flow:**
```
Startup: Pre-embed all notes → Store in index
Query → Embed query → Vector search (instant) → Return results
```

**Implementation:**
1. Modify skills gateway to pre-compute note embeddings on startup
2. Store embeddings in `D:\SHARED\AI_Models\cache\notes\embeddings.json`
3. Use batch embedding API for efficiency
4. Implement incremental update when notes change

---

### 3.2 Connection Pooling for Ollama
**Priority:** LOW | **Effort:** 2 hours

**Issue:** Each request creates new HTTP connection to Ollama.

**Improvement:**
- Use `httpx` with connection pooling in gateway
- Reuse connections across requests
- Reduce latency for sequential requests

---

### 3.3 Caching Layer for Skills
**Priority:** LOW | **Effort:** 3 hours

**Improvement:**
- Cache parsed SKILL.md files in memory
- Invalidate on file modification
- Reduce disk I/O on each request

---

## Phase 4: Security Enhancements (Week 2)

### 4.1 Secrets Management
**Priority:** MEDIUM | **Effort:** 2 hours

**Current State:** API keys in plaintext `.env` files.

**Options:**
1. **Windows Credential Manager** (Recommended for local)
   - Store keys in Windows Credential Manager
   - Retrieve at runtime via PowerShell

2. **Encrypted Config File**
   - Encrypt toolchain.env with DPAPI
   - Decrypt on service startup

**Implementation:**
- Create `D:\SHARED\AI_Models\TOOLS\secrets_manager.ps1`
- Commands: `set-secret`, `get-secret`, `list-secrets`
- Migrate existing keys from plaintext

---

### 4.2 Audit Logging
**Priority:** LOW | **Effort:** 2 hours

**Improvement:**
- Log all tool invocations with timestamps
- Log API access (who, when, what)
- Separate audit log from operational logs
- Retention policy (30 days default)

---

## Phase 5: New Features (Week 3+)

### 5.1 Additional Skills

**5.1.1 Code Review Skill**
- Model: qwen3-coder:30b
- Tools: fs, git
- Purpose: Automated code review with security focus

**5.1.2 Meeting Notes Skill**
- Model: qwen2.5:14b
- Tools: fs, doc
- Purpose: Transcription cleanup and action item extraction

**5.1.3 Email Drafting Skill**
- Model: qwen2.5:14b
- Tools: fs
- Purpose: Professional email composition

---

### 5.2 Web UI Dashboard
**Priority:** LOW | **Effort:** 8 hours

**Purpose:** Local web interface for service management.

**Features:**
- Service status indicators (green/red)
- Start/stop buttons for each service
- Recent logs viewer
- Skill browser and tester
- System resource monitor (CPU, RAM, GPU)

**Technology:**
- FastAPI backend (extend existing)
- Simple HTML/CSS/JS frontend
- Run on port 9000

---

### 5.3 Backup & Restore
**Priority:** MEDIUM | **Effort:** 3 hours

**Create:** `D:\SHARED\AI_Models\TOOLS\backup_restore.ps1`

**Backup includes:**
- All configuration files
- Skills and context packs
- Custom prompts
- API keys (encrypted)
- Docker volumes

**Backup location:** `D:\SHARED\AI_Models\backups\`

**Commands:**
```powershell
.\backup_restore.ps1 -Action backup -Name "pre-upgrade"
.\backup_restore.ps1 -Action restore -Name "pre-upgrade"
.\backup_restore.ps1 -Action list
```

---

### 5.4 Update Manager
**Priority:** LOW | **Effort:** 4 hours

**Create:** `D:\SHARED\AI_Models\TOOLS\update_manager.ps1`

**Features:**
- Check for new Open WebUI versions
- Check for Ollama updates
- Check for Python package updates
- Safe update with automatic backup
- Rollback capability

---

## Phase 6: Documentation (Ongoing)

### 6.1 Architecture Diagram
- Create visual diagram of all components
- Show data flow between services
- Include port numbers and protocols

### 6.2 Troubleshooting Guide
- Common errors and solutions
- Log file locations
- Diagnostic commands

### 6.3 Skill Development Guide
- How to create new skills
- SKILL.md format reference
- Testing new skills

### 6.4 API Reference
- Document all internal APIs
- Include request/response examples
- Authentication details

---

## Implementation Priority Matrix

| Task | Priority | Effort | Impact | Phase |
|------|----------|--------|--------|-------|
| Create stop_doc_tools_api.ps1 | HIGH | 15 min | Critical | 1 |
| Rotate API keys | HIGH | 30 min | Security | 1 |
| Unified service manager | HIGH | 2 hr | Usability | 2 |
| Automated test suite | HIGH | 3 hr | Reliability | 2 |
| Async RAG embeddings | HIGH | 4 hr | Performance | 3 |
| Health check monitoring | MEDIUM | 2 hr | Reliability | 2 |
| Pre-download Marker models | MEDIUM | 30 min | UX | 2 |
| Secrets management | MEDIUM | 2 hr | Security | 4 |
| Backup & restore | MEDIUM | 3 hr | Reliability | 5 |
| Add QPDF to PATH | MEDIUM | 10 min | Simplicity | 1 |
| Connection pooling | LOW | 2 hr | Performance | 3 |
| Skill caching | LOW | 3 hr | Performance | 3 |
| Web UI dashboard | LOW | 8 hr | Usability | 5 |
| Update manager | LOW | 4 hr | Maintainability | 5 |
| Audit logging | LOW | 2 hr | Security | 4 |

---

## Success Metrics

After implementing these improvements:

| Metric | Current | Target |
|--------|---------|--------|
| Components passing tests | 75% | 100% |
| Service startup time | Manual | < 30 sec (automated) |
| RAG query response | Timeout | < 5 sec |
| First PDF-to-MD call | 6 min | < 30 sec (pre-warmed) |
| API key security | Plaintext | Encrypted |
| Test automation | Manual | Fully automated |
| Service recovery | Manual | Self-healing |

---

## Next Steps

1. Review and approve this plan
2. Start with Phase 1 (Critical Fixes)
3. Execute Phase 2 during week 1
4. Continue with remaining phases as time permits

---

## Appendix: File Locations Summary

**Scripts to Create:**
- `D:\SHARED\AI_Models\OPENAPI\doc-tools\stop_doc_tools_api.ps1`
- `D:\SHARED\AI_Models\service_manager.ps1`
- `D:\SHARED\AI_Models\TOOLS\run_tests.ps1`
- `D:\SHARED\AI_Models\TOOLS\health_check.ps1`
- `D:\SHARED\AI_Models\TOOLS\warmup_marker.ps1`
- `D:\SHARED\AI_Models\TOOLS\secrets_manager.ps1`
- `D:\SHARED\AI_Models\TOOLS\backup_restore.ps1`
- `D:\SHARED\AI_Models\TOOLS\update_manager.ps1`

**Files to Modify:**
- `D:\SHARED\AI_Models\pipelines\.env` (new API key)
- `D:\SHARED\AI_Models\pipelines\pipelines\agent_skills_gateway.py` (async RAG)
- `D:\SHARED\AI_Models\SETUP\setup.ps1` (add Marker warmup)
- System PATH (add QPDF)
