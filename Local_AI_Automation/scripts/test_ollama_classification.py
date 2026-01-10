#!/usr/bin/env python3
"""
Test Ollama classification locally.
Simulates email and task classification without Slack/M365.

Run: python test_ollama_classification.py
"""

import requests
import json
from datetime import datetime
from pathlib import Path

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / ".env")

OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "test_results"

# Sample emails for testing
SAMPLE_EMAILS = [
    {
        "from": "recruiter@techstaffing.com",
        "subject": "Senior Security Consultant - DORA Implementation - Remote - 6 months",
        "body": """
        Hi,

        We have an urgent requirement for a Senior Security Consultant to help our banking client
        implement DORA (Digital Operational Resilience Act) compliance framework.

        Role: Senior Security Consultant
        Location: Remote (EU timezone)
        Duration: 6 months, likely extension
        Rate: €800-900/day
        Start: ASAP (within 2 weeks)

        Requirements:
        - DORA/NIS2 regulatory experience
        - ISO 27001 implementation background
        - Financial services sector experience
        - CISM or CISSP certification preferred
        - Fluent English

        If interested, please send your CV and availability.

        Best regards,
        Sarah
        Tech Staffing Solutions
        """
    },
    {
        "from": "newsletter@techcrunch.com",
        "subject": "Your Daily Tech Digest - AI Startups Raise $5B",
        "body": """
        TechCrunch Daily Newsletter

        TOP STORIES:
        - AI startups raised $5B in Q4 2025
        - OpenAI announces new reasoning model
        - Microsoft acquires security startup for $2B

        Read more at techcrunch.com
        """
    },
    {
        "from": "finance@company.com",
        "subject": "Invoice #INV-2026-001 - Payment Reminder",
        "body": """
        Dear Consultant,

        This is a reminder that invoice #INV-2026-001 for December consulting services
        is due for payment on January 15, 2026.

        Amount: €12,500
        Due Date: 2026-01-15

        Please ensure timely payment.

        Finance Department
        """
    },
    {
        "from": "client@bigbank.com",
        "subject": "RE: ISO 27001 Audit Preparation - Meeting Request",
        "body": """
        Hi,

        Can we schedule a meeting this week to discuss the ISO 27001 audit preparation?
        We need to review the evidence collection status and address some gaps identified
        in the pre-audit assessment.

        Proposed times:
        - Tuesday 10:00-11:00
        - Wednesday 14:00-15:00

        Let me know what works.

        Thanks,
        John
        Information Security Manager
        Big Bank Corp
        """
    }
]

# Sample task inputs for backlog testing
SAMPLE_TASKS = [
    "Need to review the DORA compliance checklist for the banking client - this is urgent!",
    "Maybe look into setting up a local vector database for RAG at some point",
    "Create proposal for the new Azure security assessment project",
    "Read the new ISO 27001:2022 transition guide",
    "P0: Fix the authentication bug in the client portal before go-live tomorrow"
]

def classify_email(email: dict) -> dict:
    """Classify an email using Ollama."""
    prompt = f"""Analyze this email and determine its category.

From: {email['from']}
Subject: {email['subject']}
Body: {email['body'][:2000]}

Classify into ONE category:
- CONSULTING_LEAD (consulting/contracting opportunity)
- CUSTOMER (existing customer communication)
- NEWSLETTER (newsletter or marketing)
- INVOICE (financial/invoice related)
- MEETING (meeting request/calendar)
- ACTION_REQUIRED (needs response/action)
- SPAM (unwanted/spam)
- OTHER

If CONSULTING_LEAD, also extract:
- role, industry, location, duration, start_date, skills, rate
- relevance_score (0-100) for: IT Security, GRC, DORA, NIS2, ISO27001, Azure
- justification

Respond ONLY with valid JSON:
{{"category": "...", "is_lead": true/false, "extraction": {{...}} }}"""

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }, timeout=60)

        result = response.json()
        llm_response = result.get("response", "")

        # Extract JSON from response
        import re
        json_match = re.search(r'\{[\s\S]*\}', llm_response)
        if json_match:
            return json.loads(json_match.group())
        return {"error": "No JSON in response", "raw": llm_response[:500]}

    except Exception as e:
        return {"error": str(e)}

def parse_task(task_input: str) -> dict:
    """Parse a task input into structured backlog item."""
    prompt = f"""You are a task assistant. Convert this message into a structured backlog item.

User message: "{task_input}"

Extract:
1. title: Short title (max 10 words)
2. description: Fuller description
3. category: One of [Consulting Lead / Sales, Client Delivery, Security / GRC, AI / Automation, Software / App Dev, Ops / Admin / Finance, Learning / Research, Personal]
4. priority: P0 (urgent), P1 (high), P2 (normal), P3 (low)
5. item_type: personal, work, or mixed
6. next_action: One concrete next step
7. estimated_effort: S (<1hr), M (1-4hr), L (>4hr)

Priority rules:
- Default is P2
- 'urgent', 'ASAP', 'P0' = P0
- 'important', 'soon', 'P1' = P1
- 'eventually', 'nice to have', 'P3' = P3

Respond ONLY with valid JSON."""

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }, timeout=60)

        result = response.json()
        llm_response = result.get("response", "")

        import re
        json_match = re.search(r'\{[\s\S]*\}', llm_response)
        if json_match:
            return json.loads(json_match.group())
        return {"error": "No JSON in response", "raw": llm_response[:500]}

    except Exception as e:
        return {"error": str(e)}

def run_tests():
    """Run all classification tests."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {
        "timestamp": datetime.now().isoformat(),
        "model": MODEL,
        "email_classifications": [],
        "task_parsing": []
    }

    print("=" * 60)
    print("OLLAMA CLASSIFICATION TEST")
    print("=" * 60)

    # Test email classification
    print("\n--- EMAIL CLASSIFICATION ---\n")
    for i, email in enumerate(SAMPLE_EMAILS, 1):
        print(f"[{i}/{len(SAMPLE_EMAILS)}] Processing: {email['subject'][:50]}...")
        classification = classify_email(email)

        result = {
            "input": {
                "from": email["from"],
                "subject": email["subject"]
            },
            "classification": classification
        }
        results["email_classifications"].append(result)

        category = classification.get("category", "ERROR")
        is_lead = classification.get("is_lead", False)
        score = classification.get("extraction", {}).get("relevance_score", "N/A") if is_lead else "N/A"

        print(f"    Category: {category}")
        print(f"    Is Lead: {is_lead}")
        if is_lead:
            print(f"    Relevance Score: {score}")
        print()

    # Test task parsing
    print("\n--- TASK PARSING ---\n")
    for i, task in enumerate(SAMPLE_TASKS, 1):
        print(f"[{i}/{len(SAMPLE_TASKS)}] Processing: {task[:50]}...")
        parsed = parse_task(task)

        result = {
            "input": task,
            "parsed": parsed
        }
        results["task_parsing"].append(result)

        print(f"    Title: {parsed.get('title', 'ERROR')}")
        print(f"    Priority: {parsed.get('priority', 'N/A')}")
        print(f"    Category: {parsed.get('category', 'N/A')}")
        print()

    # Save results
    output_file = OUTPUT_DIR / f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print("=" * 60)
    print(f"Results saved to: {output_file}")
    print("=" * 60)

    # Generate markdown report
    report_file = OUTPUT_DIR / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_file, 'w') as f:
        f.write(f"# Classification Test Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Model:** {MODEL}\n\n")

        f.write("## Email Classification Results\n\n")
        f.write("| From | Subject | Category | Is Lead | Score |\n")
        f.write("|------|---------|----------|---------|-------|\n")
        for r in results["email_classifications"]:
            cls = r["classification"]
            f.write(f"| {r['input']['from'][:20]} | {r['input']['subject'][:30]} | ")
            f.write(f"{cls.get('category', 'ERROR')} | {cls.get('is_lead', False)} | ")
            f.write(f"{cls.get('extraction', {}).get('relevance_score', 'N/A')} |\n")

        f.write("\n## Task Parsing Results\n\n")
        f.write("| Input | Title | Priority | Category |\n")
        f.write("|-------|-------|----------|----------|\n")
        for r in results["task_parsing"]:
            p = r["parsed"]
            f.write(f"| {r['input'][:30]}... | {p.get('title', 'ERROR')[:25]} | ")
            f.write(f"{p.get('priority', 'N/A')} | {p.get('category', 'N/A')[:20]} |\n")

    print(f"Report saved to: {report_file}")

    return results

if __name__ == "__main__":
    # Check Ollama availability
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"Ollama available. Models: {models}")

        if not any(MODEL in m for m in models):
            print(f"Warning: {MODEL} not found. Available: {models}")

    except Exception as e:
        print(f"Error connecting to Ollama: {e}")
        print("Make sure Ollama is running: ollama serve")
        exit(1)

    run_tests()
