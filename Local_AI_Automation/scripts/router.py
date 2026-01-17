
import os
import json
import requests
import sys
from dotenv import load_dotenv
from pathlib import Path

# Load environment
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT.parent / ".env")

OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
# Use a fast model for routing
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

def route_request(user_prompt):
    """Classify the user intent."""
    
    system_prompt = """
    You are an Intent Classifier.
    Classify the User Prompt into one of these categories:
    
    1. RESEARCH: Deep research, "find out everything about", "investigate", long running search.
    2. PROJECT: "Start a project", "create a new app", "build a folder structure".
    3. BACKLOG: "Add a task", "remind me to", simple todo items.
    4. CHAT: General conversation, coding help, questions that don't need agents.
    
    Return JSON only:
    {
        "intent": "RESEARCH" | "PROJECT" | "BACKLOG" | "CHAT",
        "confidence": 0.0-1.0,
        "parameters": {
            "goal": "extracted goal string",
            "time_limit": 10 (int, default minutes for research)
        }
    }
    """
    
    payload = {
        "model": MODEL,
        "prompt": f"{system_prompt}\nUser Prompt: {user_prompt}",
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1}
    }
    
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["response"])
    except Exception as e:
        return {"intent": "CHAT", "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No prompt provided"}))
        sys.exit(1)
        
    prompt = " ".join(sys.argv[1:])
    result = route_request(prompt)
    print(json.dumps(result, indent=2))
