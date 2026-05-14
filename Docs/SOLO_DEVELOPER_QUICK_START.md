# 🚀 YOUR SOLO DEVELOPER BUILD PLAN

## 📌 QUICK START

You want to build this **yourself** with **minimal cost** using **Azure Functions**.

Here's your path:

---

## 📋 THE WORKFLOW (Your Version)

```
DAY 0: Account disabled in Azure AD
    ↓
Check: Does user need email forwarding?
    ├─→ NO: Delete on Day 30
    └─→ YES: Continue...
    
Day 25: Send alert to manager
    
Manager replies "EXTEND"?
    ├─→ NO: Delete on Day 30
    └─→ YES: Extend to Day 60
    
On Day 60: Delete OR extend to Day 90
    
Day 90: Final delete (no more extensions)
    
OPTIONAL: Recover within 30 days (with EF disabled)
```

---

## 💰 YOUR COSTS

**Monthly**: ~$16-18
- Azure Functions: $1-2
- SQL Database S0: $15
- Everything else: Free

**Per Year**: ~$200 (vs $840 for original design = **$640 savings**)

---

## ⏱️ YOUR TIMELINE

**Week 1** (20-25 hours):
- Set up Azure resources
- Create database
- Write main monitoring function
- Test with dummy accounts

**Week 2** (15-20 hours):
- Write email processing
- Test all deletion paths
- Deploy to production
- Monitor & fix issues

**Total**: ~35-45 hours (1 full week or 2 weeks part-time)

---

## 🛠️ WHAT YOU NEED TO BUILD

### 1. Main Monitoring Function (The Core - 30 min)
**What it does**:
- Runs daily at 9 AM
- Queries Azure AD for terminated accounts
- Checks if EF required
- Sends alerts / deletes accounts on schedule

**File**: `monitor_accounts.py`
**Code location**: DEVELOPER_BUILD_GUIDE.md → Section "CORE CODE"

### 2. Email Sender (10 min)
**What it does**:
- Sends alert emails to managers
- Uses SMTP (free with your Exchange)
- Includes email templates

**File**: `send_email.py`
**Code location**: DEVELOPER_BUILD_GUIDE.md → Function `send_email()`

### 3. Account Deleter (15 min)
**What it does**:
- Deletes account from Azure AD using Graph API
- Logs deletion for audit trail

**File**: `monitor_accounts.py`
**Code location**: Function `delete_account()`

### 4. Database Layer (15 min)
**What it does**:
- Tracks user status
- Logs all actions
- Enables audit trail

**File**: SQL Schema
**Code location**: DEVELOPER_BUILD_GUIDE.md → Section "DATABASE"

### 5. Email Reply Handler (Optional - 20 min)
**What it does**:
- Listens for manager replies
- Processes "EXTEND" requests
- Updates deletion schedule

**File**: `reply_webhook.py`
**Code location**: DEVELOPER_BUILD_GUIDE.md → Section "reply_webhook.py"

---

## 📚 YOUR BUILD CHECKLIST

```
WEEK 1:

Day 1:
☐ Create Azure Function App (Consumption plan)
☐ Create Storage Account
☐ Create SQL Database (S0)
☐ Store connection strings in Key Vault
(~1-2 hours)

Day 2:
☐ Create database schema (copy/paste SQL from DEVELOPER_BUILD_GUIDE.md)
☐ Verify tables created
☐ Test database connection from local machine
(~30-45 min)

Day 3-4:
☐ Copy monitor_accounts.py code from DEVELOPER_BUILD_GUIDE.md
☐ Customize for your environment
☐ Test locally (with dummy data)
☐ Deploy to Azure Function
☐ Test timer trigger
(~8-12 hours)

Day 5:
☐ Copy email sending code
☐ Configure SMTP settings
☐ Test email sending
☐ Test with 5 dummy accounts (various deletion paths)
(~6-8 hours)

WEEK 2:

Day 1-2:
☐ Test Day 30 deletion (create test account, set date to 30 days ago)
☐ Test Day 60 deletion (with extension)
☐ Test Day 90 deletion (with 2 extensions)
☐ Fix any bugs
(~8-10 hours)

Day 3:
☐ Set up monitoring & alerts
☐ Deploy to production
☐ Create runbook for IT team
(~4-6 hours)

Day 4-5:
☐ Monitor for errors
☐ Adjust as needed
☐ Document everything
(~4-6 hours)
```

---

## 🎯 EXACT STEPS (Copy-Paste Ready)

### Step 1: Create Azure Resources

```bash
# Create Resource Group
az group create --name EFManagement --location eastus

# Create Storage Account (for Function App)
az storage account create \
  --name efmanagementstorage \
  --resource-group EFManagement \
  --location eastus

# Create Function App
az functionapp create \
  --resource-group EFManagement \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.9 \
  --functions-version 4 \
  --name efmanagementfunc \
  --storage-account efmanagementstorage

# Create SQL Database
az sql server create \
  --name efmgmtserver \
  --resource-group EFManagement \
  --location eastus \
  --admin-user sqladmin \
  --admin-password YourComplexPassword!

az sql db create \
  --resource-group EFManagement \
  --server efmgmtserver \
  --name efmanagement \
  --edition Standard \
  --service-objective S0
```

### Step 2: Get Connection Strings

```bash
# Get Storage Connection String (for Function App)
az storage account show-connection-string \
  --name efmanagementstorage \
  --resource-group EFManagement

# Get SQL Connection String
az sql db show-connection-string \
  --client sqlserver \
  --name efmanagement \
  --server efmgmtserver
```

### Step 3: Create Database Schema

```bash
# Connect to SQL database and run this SQL:
# (Use Azure Data Studio or SQL Server Management Studio)

-- Copy entire SQL schema from DEVELOPER_BUILD_GUIDE.md
-- and run it in your database
```

### Step 4: Deploy Function Code

```bash
# Create local function project
func new --name MonitorAccounts --template "Timer trigger"

# Replace the generated code with code from DEVELOPER_BUILD_GUIDE.md
# (monitor_accounts.py section)

# Deploy to Azure
func azure functionapp publish efmanagementfunc
```

### Step 5: Configure Settings

```bash
# Set application settings
az functionapp config appsettings set \
  --name efmanagementfunc \
  --resource-group EFManagement \
  --settings \
  "DB_CONNECTION_STRING=your_sql_connection_string" \
  "SMTP_SERVER=smtp.office365.com" \
  "SMTP_PORT=587" \
  "SENDER_EMAIL=it-automation-service@netradyne.com" \
  "SENDER_PASSWORD=your_app_password"
```

### Step 6: Verify Timer Trigger

```bash
# The timer trigger should run daily at 9 AM UTC
# In your monitor_accounts.py file, the decorator should be:
# @app.schedule_trigger(arg_name="timer", schedule="0 9 * * *")

# Check logs:
az functionapp log tail --name efmanagementfunc --resource-group EFManagement
```

---

## 🔐 SECURITY SETUP

### Store Secrets in Key Vault

```bash
# Create Key Vault
az keyvault create \
  --name efmanagementvault \
  --resource-group EFManagement \
  --location eastus

# Add secrets
az keyvault secret set \
  --vault-name efmanagementvault \
  --name "DB-CONNECTION-STRING" \
  --value "your_connection_string"

az keyvault secret set \
  --vault-name efmanagementvault \
  --name "SMTP-PASSWORD" \
  --value "your_password"

# Grant Function App access to Key Vault
az functionapp identity assign \
  --name efmanagementfunc \
  --resource-group EFManagement \
  --identities [system]

az keyvault set-policy \
  --name efmanagementvault \
  --object-id <managed-identity-id> \
  --secret-permissions get list
```

### Grant Graph API Permissions

```powershell
# Run as Azure AD admin in PowerShell

# Connect to Azure AD
Connect-AzureAD

# Get your Function App's Managed Identity
$functionId = (Get-AzFunctionApp -ResourceGroupName EFManagement -Name efmanagementfunc).IdentityPrincipalId

# Grant Directory.Read.All permission
$graphSpId = (Get-AzureADServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'").ObjectId
$appRole = (Get-AzureADServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'").AppRoles | Where-Object {$_.Value -eq "Directory.Read.All"}
New-AzureADServiceAppRoleAssignment -ObjectId $functionId -PrincipalId $functionId -ResourceId $graphSpId -Id $appRole.Id

# Grant User.ReadWrite.All permission (for account deletion)
$appRole = (Get-AzureADServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'").AppRoles | Where-Object {$_.Value -eq "User.ReadWrite.All"}
New-AzureADServiceAppRoleAssignment -ObjectId $functionId -PrincipalId $functionId -ResourceId $graphSpId -Id $appRole.Id
```

---

## 🧪 TESTING CHECKLIST

```
BEFORE GOING LIVE:

☐ Can query Azure AD for terminated users?
  Command: Run monitor function manually, check logs

☐ Can send emails via SMTP?
  Command: Send test email to yourself

☐ Can create database records?
  Command: Query UserTracking table after running function

☐ Can update database records?
  Command: Check if statusCode changes after alert

☐ Can delete accounts from Azure AD?
  Command: Test with dummy account (accountEnabled = false, then delete)

☐ Does timer trigger fire at correct time?
  Command: Check Azure Monitor → Function metrics

☐ Are all dates calculated correctly?
  Test cases:
    - Account offboarded Day 0, check Day 25 (alert sent)
    - Account offboarded Day 0, check Day 30 (deleted if no EF)
    - Account offboarded Day 0, check Day 60 (deleted if extended once, no 2nd ext)
    - Account offboarded Day 0, check Day 90 (deleted if 2 extensions used)

☐ Are emails formatted correctly?
  Visual check: Open received emails

☐ Is audit log complete?
  Check: DeletionAuditLog table has all actions logged

☐ Are errors handled gracefully?
  Test: Manually trigger error (e.g., invalid SQL connection) and verify logging
```

---

## 📞 WHEN YOU GET STUCK

| Problem | Solution |
|---------|----------|
| Function won't deploy | Check Python version (3.9+), requirements.txt has all packages |
| Database connection fails | Verify connection string, firewall rules allow Azure services |
| Graph API returns 403 | Verify Managed Identity has correct permissions (run PowerShell above) |
| SMTP fails | Verify SMTP credentials, enable "Less secure apps" or use app password |
| Timer trigger not firing | Check schedule format: "0 9 * * *" means 9 AM UTC daily |
| Account deletion returns error | Verify user is in your Azure AD tenant, not a guest |
| Emails not sent | Check logs for SMTP errors, verify IT email service is working |

---

## 📊 EXAMPLE OUTPUT (What You'll See)

### Function Logs (Success)

```
2026-04-28 09:00:02 | Starting account monitoring
2026-04-28 09:00:05 | Found 15 terminated users
2026-04-28 09:00:06 | User john.doe: Day 30, NO EF → DELETE
2026-04-28 09:00:07 | Deleted account john.doe@company.com
2026-04-28 09:00:08 | User jane.smith: Day 25, HAS EF → ALERT
2026-04-28 09:00:09 | Alert sent to manager@company.com
2026-04-28 09:00:10 | User bob.wilson: Day 60, Extended once, NO 2nd ext → DELETE
2026-04-28 09:00:11 | Deleted account bob.wilson@company.com
2026-04-28 09:00:12 | Monitoring completed (3 actions taken)
```

### Database Records (Sample)

```
UserID: f47ac10b-58cc-4372-a567-0e02b2c3d479
Email: john.doe@company.com
Status: DELETED
DeletedDate: 2026-04-28
DeletionReason: NO_EF
RecoveryDeadline: 2026-05-28

UserID: a8c3f5d9-4c2a-4b5e-8f6d-9e3c2b5f4a7d
Email: jane.smith@company.com
Status: ALERT_SENT
LastAlertDate: 2026-04-28
DeleteDate: 2026-05-28
```

---

## 🎉 YOU'RE READY!

**You have**:
✅ Exact commands to run
✅ Code to copy-paste
✅ Database schema
✅ Testing checklist
✅ Cost breakdown ($16/month)
✅ Timeline (2 weeks to production)

**Next steps**:
1. Run the Azure CLI commands above
2. Copy code from DEVELOPER_BUILD_GUIDE.md
3. Deploy and test
4. Go live!

**Questions while building?** Check DEVELOPER_BUILD_GUIDE.md for detailed code explanations.

**Good luck! You've got this!** 🚀

