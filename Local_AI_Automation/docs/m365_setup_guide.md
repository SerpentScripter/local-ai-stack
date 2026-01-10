# Microsoft 365 Graph API Setup Guide

This guide configures Microsoft 365 email access for the Local AI Automation Hub via Microsoft Graph API.

## Prerequisites

- Microsoft 365 Business subscription
- Global Admin or Application Administrator role
- Azure AD access

## 1. Register Azure AD Application

### 1.1 Create App Registration

1. Go to https://portal.azure.com
2. Navigate to "Azure Active Directory" → "App registrations"
3. Click "New registration"
4. Configure:
   - Name: `TR Automation Hub`
   - Supported account types: "Accounts in this organizational directory only"
   - Redirect URI: Leave blank for now
5. Click "Register"
6. Copy the **Application (client) ID** → `M365_CLIENT_ID`
7. Copy the **Directory (tenant) ID** → `M365_TENANT_ID`

### 1.2 Create Client Secret

1. In your app registration, go to "Certificates & secrets"
2. Click "New client secret"
3. Description: `n8n-automation`
4. Expiry: Choose appropriate duration (recommend 24 months)
5. Click "Add"
6. **Immediately copy the Value** → `M365_CLIENT_SECRET`
   - This is shown only once!

### 1.3 Configure API Permissions

1. Go to "API permissions"
2. Click "Add a permission"
3. Select "Microsoft Graph"
4. Choose "Application permissions" (for daemon/background access)
5. Add these permissions:

```
Mail.Read              - Read mail in all mailboxes
Mail.ReadBasic.All     - Read basic mail properties
Mail.ReadWrite         - Read and write mail (for labels/folders)
User.Read.All          - Read user profiles
```

6. Click "Add permissions"
7. Click "Grant admin consent for [Your Organization]"
8. Confirm

### Permission Summary

| Permission | Type | Purpose |
|------------|------|---------|
| `Mail.Read` | Application | Read email content |
| `Mail.ReadBasic.All` | Application | List emails efficiently |
| `Mail.ReadWrite` | Application | Move/label emails |
| `User.Read.All` | Application | Resolve sender info |

## 2. Configure n8n Credentials

### 2.1 Update Environment File

Edit `Local_AI_Automation/docker/.env`:

```env
M365_TENANT_ID=your-tenant-id-here
M365_CLIENT_ID=your-client-id-here
M365_CLIENT_SECRET=your-client-secret-here
M365_USER_EMAIL=your-email@yourdomain.com
```

### 2.2 Add Credentials in n8n

1. Open n8n: http://localhost:5678
2. Go to Settings → Credentials
3. Click "Add Credential"
4. Search for "Microsoft" or "OAuth2"
5. Select "Microsoft OAuth2 API"
6. Configure:
   - Client ID: `{M365_CLIENT_ID}`
   - Client Secret: `{M365_CLIENT_SECRET}`
   - Authorization URL: `https://login.microsoftonline.com/{M365_TENANT_ID}/oauth2/v2.0/authorize`
   - Token URL: `https://login.microsoftonline.com/{M365_TENANT_ID}/oauth2/v2.0/token`
   - Scope: `https://graph.microsoft.com/.default`

## 3. Graph API Endpoints

### Read Emails

```http
GET https://graph.microsoft.com/v1.0/users/{email}/messages
?$filter=receivedDateTime ge {datetime}
&$select=id,subject,from,receivedDateTime,bodyPreview,body
&$top=50
&$orderby=receivedDateTime desc
```

### Get Email Details

```http
GET https://graph.microsoft.com/v1.0/users/{email}/messages/{message-id}
?$select=id,subject,from,toRecipients,receivedDateTime,body,importance
```

### Move Email to Folder

```http
POST https://graph.microsoft.com/v1.0/users/{email}/messages/{message-id}/move
Content-Type: application/json

{
  "destinationId": "{folder-id}"
}
```

### List Mail Folders

```http
GET https://graph.microsoft.com/v1.0/users/{email}/mailFolders
```

### Create Mail Folder

```http
POST https://graph.microsoft.com/v1.0/users/{email}/mailFolders
Content-Type: application/json

{
  "displayName": "Consulting Leads"
}
```

## 4. n8n HTTP Request Node Configuration

### Get Recent Emails

```json
{
  "method": "GET",
  "url": "https://graph.microsoft.com/v1.0/users/{{$env.M365_USER_EMAIL}}/messages",
  "qs": {
    "$filter": "receivedDateTime ge {{$today.minus(1, 'day').toISO()}}",
    "$select": "id,subject,from,receivedDateTime,bodyPreview,body",
    "$top": "50",
    "$orderby": "receivedDateTime desc"
  },
  "authentication": "oAuth2",
  "nodeCredentialType": "microsoftOAuth2Api"
}
```

### Email Polling Workflow

```
Trigger: Schedule (every 5 minutes)
    ↓
HTTP Request: Get new emails since last check
    ↓
Filter: Only unprocessed emails
    ↓
Loop: For each email
    ↓
    HTTP Request: Get full email body
    ↓
    Process with Ollama
    ↓
    Store result / Send to Slack
```

## 5. Security Considerations

### Least Privilege
- Only request permissions actually needed
- Use Application permissions (not Delegated) for background processing
- Restrict to specific mailbox if possible

### Secret Management
- Store client secret in n8n credentials (encrypted)
- Rotate secrets annually
- Monitor Azure AD sign-in logs

### Rate Limiting
- Graph API limits: ~10,000 requests per 10 minutes
- Implement exponential backoff for 429 errors
- Use `$select` to minimize data transfer

## 6. Testing

### Test Authentication

```powershell
# Get access token
$body = @{
    grant_type    = "client_credentials"
    client_id     = $env:M365_CLIENT_ID
    client_secret = $env:M365_CLIENT_SECRET
    scope         = "https://graph.microsoft.com/.default"
}

$token = Invoke-RestMethod -Uri "https://login.microsoftonline.com/$($env:M365_TENANT_ID)/oauth2/v2.0/token" -Method POST -Body $body
$accessToken = $token.access_token

# Test email access
$headers = @{ Authorization = "Bearer $accessToken" }
$emails = Invoke-RestMethod -Uri "https://graph.microsoft.com/v1.0/users/$($env:M365_USER_EMAIL)/messages?`$top=5" -Headers $headers

$emails.value | Select-Object subject, receivedDateTime
```

### Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `AADSTS700016` | App not found | Check Client ID |
| `AADSTS7000215` | Invalid secret | Regenerate secret |
| `Authorization_RequestDenied` | Missing permission | Add & consent permission |
| `ErrorAccessDenied` | Mailbox access denied | Grant admin consent |

## 7. Folder Structure Recommendation

Create these folders in your mailbox for automated organization:

```
Inbox
├── _Processed
│   ├── Consulting Leads
│   │   ├── High Match
│   │   └── Low Match
│   ├── Action Required
│   ├── Finance
│   └── Newsletters
└── _Archive
```

Create via Graph API or Outlook, then use folder IDs in automation.

## 8. Next Steps

After M365 is configured:

1. Import the email workflow template in n8n
2. Configure the trigger schedule
3. Test with a sample email
4. Enable the workflow

See: `workflows/email_lead_detection.json`
