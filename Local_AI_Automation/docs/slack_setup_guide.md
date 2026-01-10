# Slack Workspace Setup Guide

This guide walks you through setting up a private Slack workspace for the Local AI Automation Hub.

## 1. Create Slack Workspace

1. Go to https://slack.com/get-started#/createnew
2. Enter your email address
3. Choose "Create a new workspace"
4. Name your workspace (e.g., "TR Automation Hub")
5. Skip inviting others (private workspace)

## 2. Create Required Channels

Create these channels in your workspace:

| Channel | Purpose |
|---------|---------|
| `#leads-consulting` | High-score consulting lead notifications |
| `#leads-lowmatch` | Low-score leads for review |
| `#digest-ai` | Daily AI/tech news digest |
| `#digest-grc` | Daily security/compliance digest |
| `#backlog` | Task backlog and to-do items |
| `#tasks-status` | Task completion updates |
| `#system-alerts` | System errors and health alerts |

## 3. Create Slack App

### 3.1 Create App

1. Go to https://api.slack.com/apps
2. Click "Create New App"
3. Choose "From scratch"
4. Name: "TR Automation Bot"
5. Select your workspace
6. Click "Create App"

### 3.2 Configure Bot

1. In the left sidebar, click "OAuth & Permissions"
2. Scroll to "Scopes" → "Bot Token Scopes"
3. Add these scopes:

```
channels:history      - Read channel messages
channels:read         - View channel info
chat:write           - Send messages
chat:write.public    - Send to channels bot isn't in
files:write          - Upload files
incoming-webhook     - Post via webhooks
reactions:read       - View reactions
reactions:write      - Add reactions
users:read           - View user info
```

### 3.3 Install App

1. Scroll up to "OAuth Tokens"
2. Click "Install to Workspace"
3. Authorize the app
4. Copy the "Bot User OAuth Token" (starts with `xoxb-`)

### 3.4 Get Signing Secret

1. Go to "Basic Information" in the sidebar
2. Under "App Credentials", find "Signing Secret"
3. Click "Show" and copy it

## 4. Create Incoming Webhooks

For each channel, create a webhook:

1. Go to "Incoming Webhooks" in the sidebar
2. Toggle "Activate Incoming Webhooks" to ON
3. Click "Add New Webhook to Workspace"
4. Select the channel (e.g., `#leads-consulting`)
5. Click "Allow"
6. Copy the Webhook URL

Repeat for each channel:
- `#leads-consulting` → `SLACK_WEBHOOK_LEADS`
- `#digest-ai` → `SLACK_WEBHOOK_DIGEST_AI`
- `#digest-grc` → `SLACK_WEBHOOK_DIGEST_GRC`
- `#backlog` → `SLACK_WEBHOOK_BACKLOG`
- `#system-alerts` → `SLACK_WEBHOOK_ALERTS`

## 5. Enable Events (for Backlog monitoring)

1. Go to "Event Subscriptions" in the sidebar
2. Toggle "Enable Events" to ON
3. Request URL: `http://YOUR_PUBLIC_URL/webhook/slack/events`
   - Note: This requires a public URL. Options:
     - Use ngrok for testing: `ngrok http 5678`
     - Or set up later with a tunnel service
4. Under "Subscribe to bot events", add:
   - `message.channels` - Messages in public channels
   - `app_mention` - When bot is mentioned

## 6. Update Environment File

Edit `Local_AI_Automation/docker/.env`:

```env
# Slack Bot Token (from step 3.3)
SLACK_BOT_TOKEN=xoxb-your-token-here

# Signing Secret (from step 3.4)
SLACK_SIGNING_SECRET=your-signing-secret

# Webhook URLs (from step 4)
SLACK_WEBHOOK_LEADS=https://hooks.slack.com/services/XXX/YYY/ZZZ
SLACK_WEBHOOK_DIGEST_AI=https://hooks.slack.com/services/XXX/YYY/ZZZ
SLACK_WEBHOOK_DIGEST_GRC=https://hooks.slack.com/services/XXX/YYY/ZZZ
SLACK_WEBHOOK_BACKLOG=https://hooks.slack.com/services/XXX/YYY/ZZZ
SLACK_WEBHOOK_ALERTS=https://hooks.slack.com/services/XXX/YYY/ZZZ
```

## 7. Restart n8n

After updating the environment:

```powershell
cd Local_AI_Automation\docker
docker compose down
docker compose up -d
```

## 8. Test Webhook

Test from n8n or PowerShell:

```powershell
$webhook = "YOUR_WEBHOOK_URL"
$body = @{
    text = "Test message from TR Automation Hub"
} | ConvertTo-Json

Invoke-RestMethod -Uri $webhook -Method Post -Body $body -ContentType "application/json"
```

## 9. Mobile Notifications

1. Install Slack app on your phone
2. In Slack settings → Notifications
3. Enable notifications for the channels you want alerts from
4. Consider setting `#leads-consulting` and `#system-alerts` to "All new messages"

## Channel Configuration Summary

| Channel | Webhook Env Var | Mobile Alert |
|---------|-----------------|--------------|
| `#leads-consulting` | `SLACK_WEBHOOK_LEADS` | Yes |
| `#leads-lowmatch` | - | No |
| `#digest-ai` | `SLACK_WEBHOOK_DIGEST_AI` | Optional |
| `#digest-grc` | `SLACK_WEBHOOK_DIGEST_GRC` | Optional |
| `#backlog` | `SLACK_WEBHOOK_BACKLOG` | Yes |
| `#tasks-status` | - | No |
| `#system-alerts` | `SLACK_WEBHOOK_ALERTS` | Yes |

## Troubleshooting

### Webhook returns 404
- Ensure the webhook URL is complete and not truncated
- Regenerate the webhook if needed

### Bot can't post to channel
- Invite the bot to the channel: `/invite @TR Automation Bot`
- Or use `chat:write.public` scope

### Events not received
- Check the Request URL is accessible from internet
- Use ngrok for local testing
- Verify event subscriptions are saved
