#!/usr/bin/env python3
"""Create Slack channels for automation hub."""

import requests
import os

# Load token from environment or .env file
TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
if not TOKEN:
    env_path = os.path.join(os.path.dirname(__file__), "..", "docker", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("SLACK_BOT_TOKEN="):
                    TOKEN = line.split("=", 1)[1].strip()
                    break

if not TOKEN:
    print("Error: SLACK_BOT_TOKEN not found. Set environment variable or configure docker/.env")
    exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

CHANNELS = [
    "leads-consulting",
    "digest-ai",
    "digest-grc",
    "backlog",
    "system-alerts"
]

def create_channel(name):
    """Create a Slack channel."""
    r = requests.post(
        "https://slack.com/api/conversations.create",
        headers=HEADERS,
        json={"name": name}
    )
    data = r.json()
    if data.get("ok"):
        return data["channel"]["id"]
    elif data.get("error") == "name_taken":
        # Channel exists, find it
        r = requests.get(
            "https://slack.com/api/conversations.list?types=public_channel&limit=200",
            headers=HEADERS
        )
        channels = r.json().get("channels", [])
        for ch in channels:
            if ch["name"] == name:
                return ch["id"]
    return None

def main():
    print("Setting up Slack channels...")
    print()

    results = {}
    for name in CHANNELS:
        channel_id = create_channel(name)
        if channel_id:
            print(f"  #{name}: {channel_id}")
            results[name] = channel_id
        else:
            print(f"  #{name}: FAILED")

    print()
    print("Channel IDs for .env:")
    for name, cid in results.items():
        print(f"  {name}: {cid}")

    return results

if __name__ == "__main__":
    main()
