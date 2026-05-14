# Email Forwarding & Account Deletion Automation - Developer's Build Guide

## 🎯 OBJECTIVE (Updated)

**Automate email forwarding AND account deletion for terminated employees**

1. **Day 0**: Account disabled on last working day
2. **Day 25**: Alert manager (if EF required)
3. **Day 30**: 
   - No EF → Auto-delete account
   - Has EF → Continue monitoring
4. **Day 60**: 
   - No extension → Delete account
   - Extended → Continue to Day 90
5. **Day 90**: Final delete (max policy reached)
6. **Account Recovery**: Recoverable before final delete, but EF always disabled

---

## 💰 COST-OPTIMIZED STACK

| Component | Technology | Why | Cost/Month |
|-----------|-----------|-----|-----------|
| **Orchestration** | Azure Functions (Python) | Serverless, pay-per-invocation, your control | $2-5 |
| **Database** | Azure SQL (S0) OR Table Storage | Cheapest relational OR ultra-cheap NoSQL | $15 OR $1 |
| **Email** | SMTP (it-automation-service@netradyne.com) | Free, built into Exchange | $0 |
| **Monitoring** | Azure Monitor (basic) | Free tier available | $0 |
| **Storage** | Azure Storage Account | For Function code & logs | $1-2 |
| **Identity** | Managed Identity | Free, secure | $0 |

**Total Monthly Cost: $18-23** (vs $46+ with other options)
**One-time Dev Time: ~40-60 hours (you, solo)**

---

## 🏗️ ARCHITECTURE (Developer-Friendly)

```
┌────────────────────────────────────────────────┐
│ Azure AD (Source of Truth)                     │
│ - Employee Type = "Terminated"                 │
│ - Extension Attribute 10 = offboard date       │
│ - accountEnabled = false (disabled on Day 0)   │
└──────────────────┬─────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────┐
│ TIMER TRIGGER (Daily 9 AM UTC)                 │
│ Python Azure Function                          │
│ - Run daily job                                │
│ - No infrastructure to maintain                │
└──────────────────┬─────────────────────────────┘
                   │
        ┌──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼
      DAY30      DAY60      DAY90      CHECK
      DELETE     DELETE     DELETE     EF+ALERT
        │          │          │          │
        └──────────┴──────────┴──────────┘
                   │
                   ▼
┌────────────────────────────────────────────────┐
│ ACTIONS                                        │
│ - Query Azure AD                               │
│ - Read tracking DB                             │
│ - Send emails (SMTP)                           │
│ - Delete accounts (Graph API)                  │
│ - Update tracking DB                           │
└────────────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────┐
│ TRACKING DB (SQL or Table Storage)             │
│ - User tracking                                │
│ - Status (ACTIVE, DELETED, RECOVERED)          │
│ - Audit log                                    │
└────────────────────────────────────────────────┘
```

---

## 🚀 STEP-BY-STEP IMPLEMENTATION (For Solo Developer)

### Phase 1: Setup (2-3 hours)
```
1. Create Azure resources:
   ☐ Function App (Consumption plan, Python 3.9+)
   ☐ Storage Account (for code & logs)
   ☐ SQL Database (S0, $15/mo) OR Table Storage ($1/mo)
   ☐ Managed Identity (for Graph API)

2. Grant permissions:
   ☐ Managed Identity → Directory.Read.All (query users)
   ☐ Managed Identity → User.ReadWrite.All (delete users)
   ☐ Create app registration (if needed for Graph API)

3. Configure email:
   ☐ Set up SMTP credentials for it-automation-service@netradyne.com
   ☐ Store in Key Vault
   ☐ Test email connectivity
```

### Phase 2: Database (1-2 hours)
```
Create tracking tables in SQL:

CREATE TABLE UserTracking (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    userId NVARCHAR(255) NOT NULL,
    userEmail NVARCHAR(255) NOT NULL,
    displayName NVARCHAR(255),
    managerId NVARCHAR(255),
    managerEmail NVARCHAR(255),
    offboardDate DATETIME2 NOT NULL,
    efRequired BIT DEFAULT 0,              -- EF request?
    statusCode NVARCHAR(50) NOT NULL,      -- ACTIVE, ALERT_SENT, EXTENDED, PENDING_DELETE, DELETED, RECOVERED
    deleteDate DATETIME2,                  -- Scheduled delete date
    deletedDate DATETIME2,                 -- Actual delete date
    recoveredDate DATETIME2,
    extensionCount INT DEFAULT 0,
    lastAlertDate DATETIME2,
    createdAt DATETIME2 DEFAULT GETDATE(),
    updatedAt DATETIME2 DEFAULT GETDATE()
);

CREATE TABLE AuditLog (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    userId NVARCHAR(255),
    action NVARCHAR(100),                  -- CHECKED, ALERTED, EXTENDED, DELETED, RECOVERED
    details NVARCHAR(MAX),
    executedAt DATETIME2 DEFAULT GETDATE()
);
```

### Phase 3: Azure Function (15-20 hours)
```
Create 1 main function with 4 sub-functions:

main_monitoring_function.py
├── query_terminated_users()      [Query Azure AD]
├── check_day_30()                [Delete if no EF]
├── check_day_60()                [Delete if not extended]
├── check_day_90()                [Final delete]
└── send_alert_if_ef_needed()     [Day 25 alert]
```

### Phase 4: Email Processing (3-5 hours)
```
Create HTTP-triggered function for manager replies:

reply_webhook_function.py
├── Parse email (if using email forwarding)
├── Validate sender is manager
├── Check for "EXTEND" keyword
├── Update DB (extension granted)
└── Recalculate delete date
```

### Phase 5: Testing & Deployment (5-8 hours)
```
1. Local testing:
   ☐ Test with dummy accounts
   ☐ Test date calculations
   ☐ Test email sending
   ☐ Test Graph API calls

2. UAT:
   ☐ Test with 10 real terminated accounts
   ☐ Verify deletions
   ☐ Check audit logs
   ☐ Fix bugs

3. Production:
   ☐ Deploy to Function App
   ☐ Monitor for first week
   ☐ Weekly check for errors
```

---

## 💻 CORE CODE (Python Azure Function)

### `monitor_accounts.py` (Main Function)

```python
import azure.functions as func
import json
from datetime import datetime, timedelta
from azure.identity import ManagedIdentityCredential
from msgraph.core import GraphClient
from azure.data.tables import TableClient
import os
import logging
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)
credential = ManagedIdentityCredential()
graph_client = GraphClient(credential=credential)

def main(timer: func.TimerRequest) -> None:
    """Main monitoring function - runs daily at 9 AM UTC"""
    
    logger.info("Starting account & EF monitoring")
    today = datetime.utcnow().date()
    
    try:
        # Connect to database
        db_connection = get_db_connection()
        cursor = db_connection.cursor()
        
        # Query Azure AD for terminated disabled accounts
        terminated_users = query_azure_ad()
        
        logger.info(f"Found {len(terminated_users)} terminated accounts")
        
        for user in terminated_users:
            try:
                user_id = user['id']
                user_email = user.get('mail', user.get('userPrincipalName'))
                
                # Get tracking record
                cursor.execute(
                    "SELECT * FROM UserTracking WHERE userId = ?", 
                    (user_id,)
                )
                record = cursor.fetchone()
                
                if not record:
                    # Create new tracking record
                    offboard_date = extract_offboard_date(user)
                    ef_required = check_ef_required(user)
                    
                    cursor.execute("""
                        INSERT INTO UserTracking 
                        (userId, userEmail, offboardDate, efRequired, statusCode)
                        VALUES (?, ?, ?, ?, 'ACTIVE')
                    """, (user_id, user_email, offboard_date, ef_required))
                    db_connection.commit()
                    
                    record = cursor.fetchone()
                
                # Calculate days since offboarded
                offboard_date = record[4]  # offboardDate column
                days_elapsed = (today - offboard_date.date()).days
                
                # Determine action
                if days_elapsed == 25 and record[6] == 1:  # EF required, Day 25
                    send_ef_alert(user, record)
                    update_status(cursor, user_id, 'ALERT_SENT')
                    
                elif days_elapsed == 30 and record[6] == 0:  # NO EF, Day 30
                    delete_account(user_id, user_email)
                    update_status(cursor, user_id, 'DELETED', today)
                    log_action(cursor, user_id, 'DELETED', 'No EF required - auto delete Day 30')
                    
                elif days_elapsed == 60 and record[6] == 1 and record[8] == 0:
                    # Has EF but no extension requested
                    delete_account(user_id, user_email)
                    update_status(cursor, user_id, 'DELETED', today)
                    log_action(cursor, user_id, 'DELETED', 'EF extension not requested - delete Day 60')
                    
                elif days_elapsed == 90 and record[6] == 1 and record[8] < 2:
                    # Max policy reached
                    delete_account(user_id, user_email)
                    update_status(cursor, user_id, 'DELETED', today)
                    log_action(cursor, user_id, 'DELETED', 'Max 90-day policy reached - final delete')
                    
                    # Send final notification
                    send_final_delete_notification(user, record)
                
                db_connection.commit()
                
            except Exception as e:
                logger.error(f"Error processing user {user_id}: {str(e)}")
                continue
        
        db_connection.close()
        logger.info("Monitoring completed successfully")
        
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise


def query_azure_ad():
    """Query Azure AD for terminated disabled users"""
    query = "$filter=employeeType eq 'Terminated' and accountEnabled eq false"
    response = graph_client.get(f"/users?{query}")
    return response.get('value', [])


def extract_offboard_date(user):
    """Extract offboarding date from Extension Attribute 10"""
    ext_attr = user.get('extensionAttributes', {}).get('extensionAttribute10')
    if ext_attr:
        return datetime.fromisoformat(ext_attr.replace('Z', '+00:00'))
    return datetime.utcnow()


def check_ef_required(user):
    """Check if user requested email forwarding"""
    # TODO: Query your HRIS or email forwarding system
    # For now, we'll mark as required if user has forwarding rules
    user_id = user['id']
    try:
        forwards = graph_client.get(f"/users/{user_id}/mailFolders/inbox/messageRules")
        ef_count = len(forwards.get('value', []))
        return 1 if ef_count > 0 else 0
    except:
        return 0


def send_ef_alert(user, record):
    """Send alert email to manager on Day 25"""
    manager_email = record[7]  # managerEmail
    
    if not manager_email:
        logger.warning(f"No manager email for user {user['id']}")
        return
    
    delete_date = record[9]  # deleteDate (Day 30)
    
    subject = f"Email Forwarding Expiration - {user['displayName']} - Action Required"
    body = f"""
    <html>
    <body style="font-family: Segoe UI, Arial;">
        <h2>Email Forwarding Expiration Notice</h2>
        <p>Dear Manager,</p>
        <p>Email forwarding for <strong>{user['displayName']}</strong> ({user['mail']}) 
        will expire on <strong>{delete_date.strftime('%B %d, %Y')}</strong>.</p>
        
        <p><strong>If you need to extend email forwarding, reply to this email with "EXTEND".</strong></p>
        
        <p>Maximum policy: 90 days of email forwarding from offboarding date.</p>
        
        <p>Best regards,<br>IT Operations (it-automation-service@netradyne.com)</p>
    </body>
    </html>
    """
    
    send_email(manager_email, subject, body)


def send_final_delete_notification(user, record):
    """Send final notification before account deletion"""
    manager_email = record[7]
    
    subject = f"Account Deletion - {user['displayName']} - Max Policy Reached"
    body = f"""
    <html>
    <body style="font-family: Segoe UI, Arial;">
        <h2>Account Deletion Notification</h2>
        <p>Dear Manager,</p>
        <p>As per our maximum email forwarding policy (90 days), the account for 
        <strong>{user['displayName']}</strong> ({user['mail']}) 
        is now being deleted on this date.</p>
        
        <p><strong>Account Recovery:</strong> If this account is needed for other purposes, 
        we can recover it (with email forwarding disabled) within 30 days. 
        Please contact IT Operations immediately.</p>
        
        <p>Best regards,<br>IT Operations (it-automation-service@netradyne.com)</p>
    </body>
    </html>
    """
    
    send_email(manager_email, subject, body)


def delete_account(user_id, user_email):
    """Delete user account from Azure AD"""
    try:
        graph_client.delete(f"/users/{user_id}")
        logger.info(f"Account deleted: {user_email}")
    except Exception as e:
        logger.error(f"Failed to delete account {user_email}: {str(e)}")


def send_email(recipient, subject, body):
    """Send email via SMTP"""
    try:
        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.office365.com')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        sender_email = os.environ.get('SENDER_EMAIL', 'it-automation-service@netradyne.com')
        sender_password = os.environ.get('SENDER_PASSWORD')  # Store in Key Vault
        
        msg = MIMEText(body, 'html')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
        logger.info(f"Email sent to {recipient}")
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")


def update_status(cursor, user_id, status, date_deleted=None):
    """Update tracking record status"""
    if status == 'DELETED':
        cursor.execute(
            "UPDATE UserTracking SET statusCode = ?, deletedDate = ?, updatedAt = GETDATE() WHERE userId = ?",
            (status, date_deleted, user_id)
        )
    else:
        cursor.execute(
            "UPDATE UserTracking SET statusCode = ?, updatedAt = GETDATE() WHERE userId = ?",
            (status, user_id)
        )


def log_action(cursor, user_id, action, details):
    """Log action to audit trail"""
    cursor.execute(
        "INSERT INTO AuditLog (userId, action, details) VALUES (?, ?, ?)",
        (user_id, action, details)
    )


def get_db_connection():
    """Get database connection"""
    import pyodbc
    connection_string = os.environ.get('DB_CONNECTION_STRING')
    return pyodbc.connect(connection_string)
```

### `reply_webhook.py` (Email Reply Processor)

```python
import azure.functions as func
import json
import pyodbc
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def main(req: func.HttpRequest) -> func.HttpResponse:
    """Handle manager email replies for extension requests"""
    
    try:
        body = req.get_json()
        
        # Extract email metadata
        sender_email = body.get('from', {}).get('emailAddress', {}).get('address')
        subject = body.get('subject', '')
        email_body = body.get('bodyPreview', '')
        
        # Parse user ID from email
        # TODO: Implement your email parsing logic
        
        if 'extend' not in email_body.lower():
            return func.HttpResponse("No action taken", status_code=200)
        
        # Get database connection
        connection_string = os.environ.get('DB_CONNECTION_STRING')
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        # Find user by manager email
        cursor.execute(
            "SELECT * FROM UserTracking WHERE managerEmail = ? ORDER BY updatedAt DESC",
            (sender_email,)
        )
        record = cursor.fetchone()
        
        if not record:
            return func.HttpResponse("User not found", status_code=404)
        
        user_id = record[1]
        extension_count = record[8]
        
        # Validate max extensions
        if extension_count >= 2:
            return func.HttpResponse("Max extensions reached", status_code=400)
        
        # Add 30 days to delete date
        new_delete_date = datetime.utcnow() + timedelta(days=30)
        
        # Update database
        cursor.execute("""
            UPDATE UserTracking 
            SET deleteDate = ?, extensionCount = extensionCount + 1, statusCode = 'EXTENDED', updatedAt = GETDATE()
            WHERE userId = ?
        """, (new_delete_date, user_id))
        
        # Log action
        cursor.execute(
            "INSERT INTO AuditLog (userId, action, details) VALUES (?, ?, ?)",
            (user_id, 'EXTENDED', f"Extension granted. New delete date: {new_delete_date}")
        )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Extension granted for user {user_id}")
        return func.HttpResponse("Extension processed", status_code=200)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)
```

---

## 📋 SQL SCHEMA (Complete)

```sql
-- Tracking table
CREATE TABLE UserTracking (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    userId NVARCHAR(255) NOT NULL UNIQUE,
    userEmail NVARCHAR(255) NOT NULL,
    displayName NVARCHAR(255),
    offboardDate DATETIME2 NOT NULL,
    managerId NVARCHAR(255),
    managerEmail NVARCHAR(255),
    statusCode NVARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    -- ACTIVE: Monitoring, ALERT_SENT: Alert sent Day 25, 
    -- EXTENDED: Approved for extension, PENDING_DELETE: Waiting to delete,
    -- DELETED: Account deleted, RECOVERED: Account recovered
    extensionCount INT DEFAULT 0,
    lastAlertDate DATETIME2,
    deleteDate DATETIME2,        -- Scheduled delete date
    deletedDate DATETIME2,       -- Actual delete date
    recoveredDate DATETIME2,     -- Recovery date (if recovered)
    efRequired BIT DEFAULT 0,    -- Email forwarding required?
    createdAt DATETIME2 DEFAULT GETDATE(),
    updatedAt DATETIME2 DEFAULT GETDATE()
);

-- Audit log
CREATE TABLE AuditLog (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    userId NVARCHAR(255),
    action NVARCHAR(100),  -- CHECKED, ALERTED, EXTENDED, DELETED, RECOVERED
    details NVARCHAR(MAX),
    executedAt DATETIME2 DEFAULT GETDATE()
);

-- Account recovery log (for future recovery)
CREATE TABLE RecoveryLog (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    userId NVARCHAR(255),
    userEmail NVARCHAR(255),
    deletedDate DATETIME2,
    recoveryDeadline DATETIME2,  -- 30 days after delete
    recovered BIT DEFAULT 0,
    recoveryDate DATETIME2,
    reason NVARCHAR(MAX),
    recoveredBy NVARCHAR(255),
    createdAt DATETIME2 DEFAULT GETDATE()
);

-- Create indexes
CREATE INDEX idx_statusCode ON UserTracking(statusCode);
CREATE INDEX idx_offboardDate ON UserTracking(offboardDate);
CREATE INDEX idx_deleteDate ON UserTracking(deleteDate);
CREATE INDEX idx_userId ON AuditLog(userId);
```

---

## 🔧 CONFIGURATION (Environment Variables)

Store these in Azure Key Vault:

```
DB_CONNECTION_STRING=Server=tcp:yourserver.database.windows.net;Database=AccountManagement;Encrypted=true;Connection Timeout=30;

SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
SENDER_EMAIL=it-automation-service@netradyne.com
SENDER_PASSWORD=[your app password from Exchange]

AZURE_TENANT_ID=[your tenant]
AZURE_SUBSCRIPTION_ID=[your subscription]

IT_EMAIL=it-operations@netradyne.com
COMPANY_NAME=Netradyne
RECOVERY_GRACE_DAYS=30
```

---

## 📅 TIMELINE (Solo Developer)

**Week 1**:
- Day 1-2: Set up Azure resources (2-3 hours)
- Day 3-4: Create database & tables (1-2 hours)
- Day 5: Write & test main function (5-8 hours)

**Week 2**:
- Day 1-2: Write email logic (3-5 hours)
- Day 3-4: Test with dummy accounts (3-4 hours)
- Day 5: Deploy & monitor (2-3 hours)

**Week 3**:
- Day 1-3: UAT & bug fixes (5-8 hours)
- Day 4-5: Documentation & training (3-4 hours)

**Total**: ~35-45 hours (1 week full-time or 2-3 weeks part-time)

---

## 📊 COST BREAKDOWN (Monthly)

```
Function App (Consumption): $0-2
  ~5,000 invocations × $0.20/M = $1

SQL Database (S0): $15
  OR Azure Table Storage: $1

Storage Account: $1

SMTP (Built-in Exchange): $0

Managed Identity: $0

──────────────────────────
TOTAL: $16-18/month
```

**Comparison**: 
- Your solution: $16-18/month
- Logic Apps option: $46+/month
- **Savings**: $28/month = $336/year

---

## ✅ DEPLOYMENT CHECKLIST

```
INFRASTRUCTURE
☐ Function App created (Consumption plan, Python 3.9+)
☐ Storage Account created
☐ SQL Database S0 provisioned
☐ Managed Identity configured
☐ Role assignments granted (Directory.Read.All, User.ReadWrite.All)

DATABASE
☐ SQL schema deployed
☐ Tables created & indexed
☐ Connection string in Key Vault

APPLICATION
☐ Function code deployed
☐ Environment variables configured
☐ SMTP credentials verified
☐ Graph API permissions tested

TESTING
☐ Query terminated users works
☐ Email sending works
☐ Date calculations correct
☐ Account deletion works
☐ Audit logging works
☐ Test with 5 dummy accounts
☐ Test all delete paths (Day 30, 60, 90)

DEPLOYMENT
☐ Production function deployed
☐ Timer trigger configured (Daily 9 AM UTC)
☐ Monitoring enabled
☐ Alerts configured (errors)
☐ Documentation complete
☐ Ready for go-live
```

---

## 🚀 QUICK START (30 min)

```bash
# 1. Create Function App
az functionapp create \
  --resource-group myGroup \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.9 \
  --functions-version 4 \
  --name myAccountManagementFunc

# 2. Deploy code
func azure functionapp publish myAccountManagementFunc

# 3. Configure timer trigger (daily 9 AM UTC)
# In function_app.py:
@app.schedule_trigger(arg_name="timer", schedule="0 9 * * *")
def monitor_accounts(timer: func.TimerRequest):
    ...

# 4. Done!
```

---

## 📞 SUPPORT LINKS

- Azure Functions: https://docs.microsoft.com/en-us/azure/azure-functions/
- Python SDK: https://github.com/Azure/azure-sdk-for-python
- Graph API: https://docs.microsoft.com/en-us/graph/
- SQL Database: https://docs.microsoft.com/en-us/azure/azure-sql/

---

**Your minimalist, cost-optimized, solo-developer solution: Ready to build!** ✨

