
import os
import time
import json
import sqlite3
import requests
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from duckduckgo_search import DDGS

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "backlog" / "backlog.db"
LOG_DIR = PROJECT_ROOT / "data" / "logs"
load_dotenv(PROJECT_ROOT.parent / ".env")

OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
# Use a faster/smaller model for the loop, or the main one
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

def log(session_id, message, log_type="info"):
    """Log to database and console."""
    print(f"[{log_type.upper()}] Session {session_id}: {message}")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO agent_logs (session_id, message, log_type) VALUES (?, ?, ?)",
            (session_id, message, log_type)
        )

def get_llm_response(prompt, json_mode=False):
    """Get response from Ollama."""
    try:
        payload = {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7}
        }
        if json_mode:
            payload["format"] = "json"
            
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["response"]
    except Exception as e:
        print(f"LLM Error: {e}")
        return None

def research_loop(session_id, goal, time_limit_minutes):
    """The Ralph Wiggum Loop."""
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=time_limit_minutes)
    
    log(session_id, f"Starting research: {goal} (Limit: {time_limit_minutes}m)")
    
    with sqlite3.connect(DB_PATH) as conn:
        # Initialize knowledge graph if empty
        row = conn.execute("SELECT knowledge_graph FROM research_sessions WHERE id=?", (session_id,)).fetchone()
        kg = row[0] if row and row[0] else "No findings yet."
        
    iteration = 0
    ddgs = DDGS()
    
    while datetime.now() < end_time:
        iteration += 1
        log(session_id, f"Iteration {iteration}")
        
        # 1. PLAN
        prompt = f"""
        You are a Deep Research Agent.
        Goal: {goal}
        Current Knowledge: {kg}
        
        Time Remaining: {(end_time - datetime.now()).total_minutes():.1f} minutes.
        
        Decide the next step. Return JSON only:
        {{
            "thought": "Reasoning about what is missing...",
            "action": "search" or "finish",
            "query": "search query if action is search, else null",
            "final_summary": "summary if action is finish, else null"
        }}
        """
        response = get_llm_response(prompt, json_mode=True)
        if not response: continue
        
        try:
            plan = json.loads(response)
        except:
            log(session_id, "Failed to parse JSON plan", "error")
            continue
            
        if plan.get("action") == "finish":
            log(session_id, "Goal met. Finishing.")
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("UPDATE research_sessions SET status='completed', end_time=?, knowledge_graph=? WHERE id=?", 
                             (datetime.now(), plan.get("final_summary"), session_id))
            break
            
        # 2. ACT
        query = plan.get("query")
        log(session_id, f"Searching: {query}")
        
        findings = []
        try:
            # DuckDuckGo Search
            results = ddgs.text(query, max_results=3)
            if results:
                for r in results:
                    findings.append(f"Title: {r['title']}\nSnippet: {r['body']}\nURL: {r['href']}")
            else:
                findings.append("No results found.")
        except Exception as e:
            findings.append(f"Search failed: {e}")
            
        # 3. ANALYZE & UPDATE
        new_info = "\n\n".join(findings)
        
        # Save raw findings
        with sqlite3.connect(DB_PATH) as conn:
            for f in findings:
                 conn.execute("INSERT INTO research_findings (session_id, finding, source) VALUES (?, ?, ?)", 
                              (session_id, f, "duckduckgo"))
        
        # Synthesize into Knowledge Graph
        synth_prompt = f"""
        Update the knowledge graph with this new info.
        Current KG: {kg}
        New Info: {new_info}
        
        Goal: {goal}
        
        Return the updated Knowledge Graph text (concise summary of facts).
        """
        kg = get_llm_response(synth_prompt)
        
        # Update Session State
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE research_sessions SET knowledge_graph=? WHERE id=?", (kg, session_id))
            
        # Sleep briefly to be polite/save cpu
        time.sleep(2)
        
    else:
        log(session_id, "Time limit reached.", "warning")
        with sqlite3.connect(DB_PATH) as conn:
             conn.execute("UPDATE research_sessions SET status='timeout', end_time=?, knowledge_graph=? WHERE id=?", 
                          (datetime.now(), kg, session_id))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", required=True)
    parser.add_argument("--limit", type=int, default=10) # minutes
    args = parser.parse_args()
    
    # Create session
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO research_sessions (goal, time_limit_minutes) VALUES (?, ?)",
            (args.goal, args.limit)
        )
        sid = cursor.lastrowid
        
    print(f"Session {sid} created. Starting loop...")
    research_loop(sid, args.goal, args.limit)
