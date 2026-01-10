import requests
import os
from dotenv import load_dotenv
import socket

load_dotenv()

def check_port(host, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0
    except:
        return False

def get_status(name, url, port):
    status = " DOWN"
    info = ""
    if check_port("127.0.0.1", port):
        status = " LISTENING"
        try:
            r = requests.get(url, timeout=1)
            if r.status_code < 400 or r.status_code == 404:
                 status = " ON"
                 if "ollama" in name.lower():
                     models = r.json().get("models", [])
                     info = f" ({len(models)} models)"
        except:
            pass
    return status, info

services = [
    { "name": "Ollama", "port": int(os.getenv("OLLAMA_PORT", 11434)), "url": f"http://localhost:{os.getenv("OLLAMA_PORT", 11434)}/api/tags" },
    { "name": "Open WebUI", "port": int(os.getenv("OPEN_WEBUI_PORT", 3000)), "url": f"http://localhost:{os.getenv("OPEN_WEBUI_PORT", 3000)}/health" },
    { "name": "n8n", "port": int(os.getenv("N8N_PORT", 5678)), "url": f"http://localhost:{os.getenv("N8N_PORT", 5678)}/healthz" },
    { "name": "Backlog API", "port": int(os.getenv("BACKLOG_API_PORT", 8765)), "url": f"http://localhost:{os.getenv("BACKLOG_API_PORT", 8765)}/health" },
    { "name": "Langflow", "port": int(os.getenv("LANGFLOW_PORT", 7860)), "url": f"http://localhost:{os.getenv("LANGFLOW_PORT", 7860)}/health" },
]

print("\n" + "="*50)
print(" LOCAL AI STACK STATUS")
print("="*50)
print(f"{'Service':<15} {'Status':<15} {'Info'}")
print("-" * 50)

for svc in services:
    status, info = get_status(svc["name"], svc["url"], svc["port"])
    print(f"{svc['name']:<15} {status:<15} {info}")

print("="*50 + "\n")
