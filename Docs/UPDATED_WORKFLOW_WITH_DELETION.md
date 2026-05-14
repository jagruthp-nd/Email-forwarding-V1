# UPDATED WORKFLOW - Account Deletion & Cost Optimization

## 📋 KEY CHANGES FROM ORIGINAL DESIGN

### 1. ACCOUNT DELETION PHASES (NEW)

#### Day 0: Account Disabled on Last Working Day
- IT disables account (accountEnabled = false) on last working day
- Account still exists in Azure AD
- User can no longer sign in
- Email forwarding (if any) still active

#### Day 30: First Deletion Decision
**Path A: NO Email Forwarding Required**
- ✅ Account AUTO-DELETED immediately
- ✅ User marked as DELETED in tracking DB
- ✅ End of process

**Path B: Email Forwarding Required**
- ⏱️ Continue to alert phase
- 📧 Day 25: Alert sent to manager
- Proceed to Day 30 decision (extension or delete)

#### Day 60: Second Deletion Decision (If EF & Extended Once)
**No Extension Requested**
- ✅ Account AUTO-DELETED
- 📧 Notification sent to manager
- ✅ End of process

**Extension Requested**
- ⏱️ Continue to Day 90

#### Day 90: Final Deletion (Max Policy Reached)
- ✅ Account AUTO-DELETED (no exceptions)
- 📧 Final notification: "Max 90-day policy reached"
- ✅ Recovery note: "Account recoverable within 30 days if needed for other purposes"
- ✅ End of process

### 2. TRACKING DATABASE UPDATES

**Old Status Values**:
- ACTIVE, ALERT_SENT, EXTENSION_PENDING, EXTENDED, DISABLED

**New Status Values**:
- ACTIVE: Monitoring (account disabled, checking EF requirement)
- ALERT_SENT: EF alert sent on Day 25
- EXTENDED: Manager approved extension
- EXTENDED_MAX: Max extensions (2) reached, in final 30 days
- PENDING_DELETE: Scheduled for deletion
- DELETED: Account deleted from Azure AD
- RECOVERED: Account recovered before 30-day grace period

### 3. TECHNOLOGY STACK (COST-OPTIMIZED)

| Component | Original | Updated | Cost Savings |
|-----------|----------|---------|--------------|
| Orchestration | Logic Apps | Azure Functions | -$40/month |
| Email Service | SendGrid | SMTP (built-in) | -$20/month |
| Monitoring | App Insights | Basic Azure Monitor | -$5/month |
| **Total Monthly** | **$46+** | **$16-18** | **$28-30/month = $336/year** |

---

## 📊 UPDATED WORKFLOW

### Decision Tree

```
EMPLOYEE OFFBOARDED
    ↓
DAY 0: Account Disabled (accountEnabled = false)
    ↓
DAILY MONITORING (9 AM UTC)
    ├─→ Check: Is EF required?
    │
    ├─→ NO EF
    │  └─→ Day 30: DELETE ACCOUNT (immediately)
    │      └─→ Status: DELETED | End
    │
    └─→ YES EF (proceed with monitoring)
       └─→ Day 25: SEND ALERT
           "Forwarding expires Day 30. Reply to extend."
           └─→ Status: ALERT_SENT
           │
           └─→ Manager Replies?
               ├─→ NO REPLY
               │  └─→ Day 30: DELETE ACCOUNT
               │      └─→ Status: DELETED | End
               │
               └─→ YES (Extension Approved)
                  └─→ Add 30 days to schedule
                  └─→ Status: EXTENDED
                  └─→ Extension Count: 1 of 2
                  │
                  └─→ Day 60: Check Again
                      ├─→ NO 2ND EXTENSION
                      │  └─→ Day 60: DELETE ACCOUNT
                      │      └─→ Status: DELETED | End
                      │
                      └─→ YES 2ND EXTENSION
                         └─→ Add 30 days to schedule
                         └─→ Status: EXTENDED_MAX
                         └─→ Extension Count: 2 of 2
                         │
                         └─→ Day 90: FINAL CHECK
                             └─→ No further extensions allowed
                             └─→ Day 90: DELETE ACCOUNT (FINAL)
                                 └─→ Status: DELETED | End
                                 └─→ Recovery Note: "Recoverable within 30 days"

RECOVERY (Optional):
    └─→ Within 30 days of deletion?
        └─→ Can recover account (with EF disabled)
        └─→ Status: RECOVERED
        └─→ Note: "Account recovered, EF permanently disabled"
```

---

## 🔄 EMAIL TEMPLATES (UPDATED)

### Alert Email (Day 25 - If EF Required)

```
Subject: Email Forwarding Expiration - [Username] - Action Required

To: [Manager Email]
From: it-automation-service@netradyne.com

---

Dear [Manager Name],

Email forwarding for [Employee Name] ([Employee Email]) 
will expire on [Day 30 Date].

⚠️ AFTER THIS DATE:
- If NO action: Account will be DELETED
- If extension needed: Reply to this email with "EXTEND"

IMPORTANT: 
- Maximum policy: 90 days of email forwarding (2 x 30-day extensions)
- You have until [Day 30 Date] to respond

Reply Instructions:
Simply reply to this email with "EXTEND" to add 30 more days.

---

Best regards,
IT Operations
it-automation-service@netradyne.com
```

### Final Deletion Notification (Day 90)

```
Subject: Account Deleted - [Username] - Max Policy Reached

To: [Manager Email]
From: it-automation-service@netradyne.com

---

Dear [Manager Name],

The account for [Employee Name] ([Employee Email]) 
has been deleted as per our maximum email forwarding policy (90 days).

📌 ACCOUNT RECOVERY:
If this account is needed for other business purposes, 
it CAN be recovered within 30 days with the following conditions:
- Email forwarding will be PERMANENTLY DISABLED
- Account will be restored to archived state
- Recovery request must be submitted to IT Operations

To request recovery: it-operations@netradyne.com
Subject: Account Recovery Request - [Employee Name]

Recovery deadline: [Date + 30 days]

---

Best regards,
IT Operations
it-automation-service@netradyne.com
```

### Day 60 Deletion Notification (If Not Extended)

```
Subject: Account Deletion - [Username] - Extension Not Requested

To: [Manager Email]
From: it-automation-service@netradyne.com

---

Dear [Manager Name],

Since no extension was requested for [Employee Name]'s email forwarding,
the account has been deleted today ([Date]).

---

Best regards,
IT Operations
it-automation-service@netradyne.com
```

---

## 🗄️ DATABASE SCHEMA (UPDATED)

```sql
-- Main tracking table
CREATE TABLE UserTracking (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    userId NVARCHAR(255) NOT NULL UNIQUE,
    userEmail NVARCHAR(255) NOT NULL,
    displayName NVARCHAR(255),
    offboardDate DATETIME2 NOT NULL,
    managerId NVARCHAR(255),
    managerEmail NVARCHAR(255),
    
    -- EF and deletion tracking
    efRequired BIT DEFAULT 0,           -- Email forwarding required?
    deleteDate DATETIME2,               -- Scheduled delete date (Day 30, 60, or 90)
    deletedDate DATETIME2,              -- Actual deletion date
    recoveredDate DATETIME2,            -- Recovery date (if recovered)
    
    -- Status tracking
    statusCode NVARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    -- Values: ACTIVE, ALERT_SENT, EXTENDED, EXTENDED_MAX, 
    --         PENDING_DELETE, DELETED, RECOVERED
    
    extensionCount INT DEFAULT 0,       -- 0, 1, or 2 (max)
    lastAlertDate DATETIME2,
    lastExtensionDate DATETIME2,
    
    -- Audit
    createdAt DATETIME2 DEFAULT GETDATE(),
    updatedAt DATETIME2 DEFAULT GETDATE(),
    notes NVARCHAR(MAX)
);

-- Deletion audit log
CREATE TABLE DeletionAuditLog (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    userId NVARCHAR(255) NOT NULL,
    userEmail NVARCHAR(255),
    displayName NVARCHAR(255),
    deletionReason NVARCHAR(255),       -- 'NO_EF', 'NO_EXTENSION_DAY60', 'MAX_POLICY_DAY90'
    deletedDate DATETIME2 DEFAULT GETDATE(),
    deletedBy NVARCHAR(255),            -- SYSTEM or specific user
    recoveryDeadline DATETIME2,         -- 30 days after deletion
    recoveryAttempted BIT DEFAULT 0,
    recoveryDate DATETIME2,
    recoveredBy NVARCHAR(255),
    recoveryReason NVARCHAR(MAX)
);

-- Email activity log
CREATE TABLE EmailActivityLog (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    userId NVARCHAR(255),
    recipientEmail NVARCHAR(255),
    emailType NVARCHAR(50),             -- ALERT, EXTENSION_NOTICE, DELETION_NOTICE
    subject NVARCHAR(255),
    sentDate DATETIME2 DEFAULT GETDATE(),
    deliveryStatus NVARCHAR(50),        -- SENT, FAILED
    errorMessage NVARCHAR(MAX)
);

-- Indexes for performance
CREATE INDEX idx_statusCode ON UserTracking(statusCode);
CREATE INDEX idx_efRequired ON UserTracking(efRequired);
CREATE INDEX idx_deleteDate ON UserTracking(deleteDate);
CREATE INDEX idx_offboardDate ON UserTracking(offboardDate);
CREATE INDEX idx_userId ON DeletionAuditLog(userId);
CREATE INDEX idx_deletionReason ON DeletionAuditLog(deletionReason);
```

---

## 💻 CODE LOGIC (Key Functions)

### Check for Deletion

```python
def check_for_deletion(user_id, days_elapsed, ef_required, extension_count, delete_date):
    """
    Determine if account should be deleted
    
    Returns: (should_delete: bool, reason: str, status: str)
    """
    
    # Day 30: NO EF → Delete
    if days_elapsed == 30 and not ef_required:
        return (True, "NO_EF", "DELETED")
    
    # Day 30: Has EF but no alert sent yet → Send alert, don't delete yet
    if days_elapsed == 25 and ef_required:
        return (False, "SEND_ALERT", "ALERT_SENT")
    
    # Day 30: Has EF → Wait for manager response, delete if no extension
    if days_elapsed == 30 and ef_required and extension_count == 0:
        return (True, "NO_EXTENSION_DAY30", "DELETED")
    
    # Day 60: Extended once but no second extension → Delete
    if days_elapsed == 60 and extension_count == 1:
        return (True, "NO_EXTENSION_DAY60", "DELETED")
    
    # Day 90: Max reached → Final delete
    if days_elapsed == 90 and extension_count == 2:
        return (True, "MAX_POLICY_DAY90", "DELETED")
    
    return (False, "", "ACTIVE")


def delete_account_and_log(user_id, user_email, reason):
    """
    Delete account from Azure AD and log deletion
    """
    try:
        # Delete from Azure AD
        graph_client.delete(f"/users/{user_id}")
        
        # Log deletion with recovery deadline
        recovery_deadline = datetime.utcnow() + timedelta(days=30)
        
        cursor.execute("""
            INSERT INTO DeletionAuditLog 
            (userId, userEmail, deletionReason, deletedBy, recoveryDeadline)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, user_email, reason, 'SYSTEM', recovery_deadline))
        
        # Update tracking
        cursor.execute("""
            UPDATE UserTracking 
            SET statusCode = 'DELETED', deletedDate = GETDATE()
            WHERE userId = ?
        """, (user_id,))
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete account {user_email}: {str(e)}")
        return False
```

### Account Recovery

```python
def recover_account(user_id, recovery_reason):
    """
    Recover deleted account within 30-day grace period
    """
    
    # Check if within recovery window
    cursor.execute("""
        SELECT recoveryDeadline FROM DeletionAuditLog 
        WHERE userId = ? AND recoveryAttempted = 0
        ORDER BY deletedDate DESC
    """, (user_id,))
    
    result = cursor.fetchone()
    if not result:
        return False, "Account not found or already recovered"
    
    recovery_deadline = result[0]
    if datetime.utcnow() > recovery_deadline:
        return False, "Recovery window expired (30 days after deletion)"
    
    try:
        # Restore account (depends on your backup system)
        # This is pseudo-code - implement based on your environment
        restore_account_from_backup(user_id)
        
        # Disable email forwarding
        disable_email_forwarding(user_id)
        
        # Update logs
        cursor.execute("""
            UPDATE DeletionAuditLog 
            SET recoveryDate = GETDATE(), recoveredBy = ?, recoveryReason = ?, recoveryAttempted = 1
            WHERE userId = ? AND recoveryAttempted = 0
        """, (current_user, recovery_reason, user_id))
        
        cursor.execute("""
            UPDATE UserTracking 
            SET statusCode = 'RECOVERED', recoveredDate = GETDATE()
            WHERE userId = ?
        """, (user_id,))
        
        return True, "Account recovered successfully"
        
    except Exception as e:
        return False, str(e)
```

---

## 🎯 COST COMPARISON

### Original Design
- Logic Apps: $30/month
- SQL Database: $15/month
- SendGrid: $20/month
- App Insights: $5/month
- **Total: $70/month = $840/year**

### Your Cost-Optimized Design
- Azure Functions: $1-2/month
- SQL Database (S0): $15/month (or Table Storage: $1)
- SMTP (built-in): $0/month
- Basic Monitoring: $0/month
- **Total: $16-17/month = $192-204/year**

### **Annual Savings: $636-648**

---

## 🚀 DEPLOYMENT CHECKLIST (UPDATED)

```
INFRASTRUCTURE
☐ Azure subscription ready
☐ Function App created (Consumption plan)
☐ SQL Database S0 provisioned (or Table Storage)
☐ Storage Account for Function code
☐ Managed Identity configured

DATABASE
☐ UserTracking table created
☐ DeletionAuditLog table created
☐ EmailActivityLog table created
☐ Indexes created
☐ Connection string in Key Vault

AZURE AD SETUP
☐ Graph API permissions: User.ReadWrite.All
☐ Directory.Read.All for reading users
☐ Managed Identity assigned these roles

EMAIL SETUP
☐ SMTP credentials configured (it-automation-service@netradyne.com)
☐ Credentials stored in Key Vault
☐ SMTP connectivity verified
☐ Email templates reviewed

FUNCTION CODE
☐ Main monitoring function deployed
☐ Email reply webhook deployed (if using)
☐ Timer trigger configured (Daily 9 AM UTC)
☐ Error handling implemented
☐ Logging configured

TESTING
☐ Query Azure AD for terminated users
☐ Check EF requirement detection
☐ Test email sending via SMTP
☐ Test account deletion (non-prod account)
☐ Test audit logging
☐ Test all deletion paths (Day 30, 60, 90)
☐ Test manager reply processing
☐ Test account recovery (if applicable)

PRODUCTION
☐ All tests passed
☐ Code reviewed
☐ Monitoring alerts configured
☐ Error notifications to IT
☐ Documentation complete
☐ Go-live approval obtained
☐ Runbook created for exceptions
```

---

## 📞 SUPPORT & DOCUMENTATION

### Runbook for IT Team

**Daily Operations**:
- Function runs automatically at 9 AM UTC
- No manual intervention needed
- Check dashboard for errors (weekly)

**Manager Requests for Account Recovery**:
1. Verify within 30-day window
2. Confirm business justification
3. Run recovery script (see code above)
4. Note: EF permanently disabled

**Troubleshooting**:
- Alert email not sent? Check SMTP credentials
- Account not deleted? Check graph API permissions
- Audit log not updated? Check database connection

---

## ✨ FINAL SUMMARY

**What's New**:
✅ Account deletion automation (Day 30/60/90)
✅ Cost reduced from $840/year to $192/year ($648 savings)
✅ Solo developer build (40-60 hours estimated)
✅ Account recovery option (30-day grace period)
✅ Full audit trail for compliance
✅ Uses SMTP instead of SendGrid

**Your Next Steps**:
1. Read DEVELOPER_BUILD_GUIDE.md for implementation
2. Set up Azure resources
3. Deploy code
4. Test thoroughly
5. Go live in 1-2 weeks

