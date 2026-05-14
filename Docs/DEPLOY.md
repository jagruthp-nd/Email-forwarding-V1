# EF Automation – Deployment & Run Guide

Quick reference for deploying and operating the automation as a solo developer.

---

## 1  Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Azure CLI | ≥ 2.55 | `brew install azure-cli` |
| Azure Functions Core Tools | v4 | `brew tap azure/functions && brew install azure-functions-core-tools@4` |
| Python | 3.11 | `pyenv install 3.11` |
| AzureAD PowerShell module | any | `Install-Module AzureAD` (PS) |

Log in before running any commands:
```bash
az login
az account set --subscription "<your-subscription-id>"
```

---

## 2  One-time Infrastructure Setup

```bash
chmod +x infra/setup.sh
./infra/setup.sh
```

This creates: Resource Group → Storage Account → Table Storage tables →
Key Vault → Function App (Consumption / Python 3.11) → Managed Identity →
RBAC assignments → app settings.

Then, in PowerShell:
```powershell
./infra/assign_permissions.ps1 -PrincipalId "<principal-id-from-setup.sh>"
```

---

## 3  Local Testing

```bash
# Copy the example settings file and fill in your values
cp local.settings.json.example local.settings.json
# Set AzureWebJobsStorage to an actual storage connection string for local run:
# az storage account show-connection-string --name stefautomation ...

# Install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run unit tests (no Azure calls, fast)
python -m pytest tests/test_local.py -v

# Start the Functions host locally (triggers are registered but won't fire
# automatically until you test them explicitly)
func start
```

### Manually trigger the daily monitor locally

```bash
# Trigger via the timer (set run_on_startup=True in function_app.py temporarily)
# OR call the internal admin endpoint:
curl -X POST "http://localhost:7071/admin/functions/monitor_accounts" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Test the webhook locally

```bash
curl -X POST "http://localhost:7071/api/reply" \
  -H "Content-Type: application/json" \
  -d '{
    "from_email": "manager@netradyne.com",
    "subject": "Re: Email Forwarding Expiration – John Doe",
    "body": "Please EXTEND this",
    "user_email": "john.doe@netradyne.com"
  }'
```

---

## 4  Deploy to Production

```bash
# Deploy using Azure Functions Core Tools
func azure functionapp publish func-ef-automation --python

# Verify deployment
az functionapp show \
  --name func-ef-automation \
  --resource-group rg-ef-automation \
  --query "state" --output tsv
```

Expected output: `Running`

---

## 5  Verify Timer Fires at 9 AM UTC

Check the next scheduled run via Azure Portal:
1. Portal → Function App → `func-ef-automation`
2. Functions → `monitor_accounts` → Monitor
3. Confirm the invocation log shows a run at 09:00 UTC

Or from CLI (after first run):
```bash
az monitor app-insights query \
  --apps func-ef-automation \
  --analytics-query "traces | where message contains 'EF Monitor' | order by timestamp desc | take 5"
```

---

## 6  Power Automate – Webhook Setup

This routes manager email replies to the `reply_webhook` function.

1. Go to [make.powerautomate.com](https://make.powerautomate.com)
2. **New Flow → Automated cloud flow**
3. Trigger: **"When a new email arrives (V3)"** on `it-automation-service@netradyne.com`
   - Filter Subject: starts with `Re: Email Forwarding`
4. Action: **HTTP POST**
   - URL: `https://func-ef-automation.azurewebsites.net/api/reply?code=<function-key>`
   - Method: `POST`
   - Headers: `Content-Type: application/json`
   - Body:
     ```json
     {
       "from_email":  "@{triggerOutputs()?['body/from/emailAddress/address']}",
       "subject":     "@{triggerOutputs()?['body/subject']}",
       "body":        "@{triggerOutputs()?['body/bodyPreview']}",
       "user_email":  ""
     }
     ```

Get the function key from:
```bash
az functionapp keys list \
  --name func-ef-automation \
  --resource-group rg-ef-automation
```

---

## 7  Monitoring & Alerting

### View recent runs

```bash
# Last 10 function invocations
az monitor app-insights query \
  --apps func-ef-automation \
  --analytics-query "requests | order by timestamp desc | take 10 | project timestamp, name, success, resultCode"
```

### Set up an alert for failures

```bash
az monitor metrics alert create \
  --name "ef-function-failures" \
  --resource-group rg-ef-automation \
  --scopes "$(az functionapp show --name func-ef-automation --resource-group rg-ef-automation --query id -o tsv)" \
  --condition "count requests where success == false > 0" \
  --window-size 1h \
  --evaluation-frequency 1h \
  --action-group "<your-action-group-id>"
```

---

## 8  Rollback / Emergency Stop

To stop all automation immediately (e.g., if something goes wrong):
```bash
# Disable the Function App entirely
az functionapp stop --name func-ef-automation --resource-group rg-ef-automation

# Re-enable when ready
az functionapp start --name func-ef-automation --resource-group rg-ef-automation
```

---

## 9  Account Recovery (Manual)

If a manager requests recovery of a deleted account within 30 days:

```bash
# Find the user in the recycle bin
az ad user list --filter "displayName eq 'John Doe'"
# or use Portal: Azure AD → Deleted users

# Restore via Graph API (or Portal)
# The Managed Identity restore endpoint is:
# POST https://graph.microsoft.com/v1.0/directory/deletedItems/{userId}/restore
```

Note: Email forwarding is **permanently disabled** on recovery (by policy and by code).

---

## 10  Cost Reference

| Resource | Est. Monthly Cost |
|----------|-------------------|
| Azure Functions (Consumption) | $0–2 |
| Azure Table Storage | ~$1 |
| Storage Account (code) | ~$1 |
| Key Vault (secrets) | ~$0.03 |
| SMTP via Exchange | $0 |
| **Total** | **~$3–4/month** |
