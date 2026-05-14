# Email Forwarding Automation - Quick Implementation Guide

## 🎯 TL;DR - 30 Second Summary

**What**: Automate email forwarding expiration for terminated employees
**When**: Check daily on Day 25, then auto-disable on Day 30/60/90
**How**: 
1. Query Azure AD for terminated users with offboard date
2. Send alert to manager on Day 25
3. Parse manager reply for "extend" keyword
4. Add 30 days if approved (max 90 total)
5. Auto-disable on scheduled date

---

## 🏗️ RECOMMENDED SOLUTION: Azure Logic Apps + Azure SQL

### Why This Stack?
- ✅ No coding required (visual workflow)
- ✅ Native Azure AD + Email integration
- ✅ Easy to monitor & modify
- ✅ IT team can troubleshoot without developers

---

## 📋 QUICK START - 4 Main Components

### Component 1: Daily Monitor Function (Logic App)
**Trigger**: Recurrence (Daily @ 9 AM UTC)
**Action**: Query Azure AD → Filter terminated users → Check date thresholds

```
1. Initialize variables:
   - Today's date
   - Day 25 threshold (offboardDate + 25 days)
   - Day 30 threshold (offboardDate + 30 days)
   - Day 60, 90 thresholds

2. Query Azure AD:
   - Filter: employeeType = "Terminated"
   - Get: extensionAttribute10, manager, mail
   
3. For each user:
   - Check if offboardDate + 25 = today → Send ALERT
   - Check if offboardDate + 30/60/90 = today → DISABLE
```

### Component 2: Email Alert (Logic App Action)
**Template**: See DESIGN.md
**To**: Manager email
**CC**: it-operations@company.com
**Include**: Employee name, disable date, extension count

### Component 3: Manager Reply Webhook (Azure Function)
**Trigger**: Email webhook (set up reply-to forwarding)
**Process**:
- Parse email header for user ID (if using reply-to format)
- Check if contains "extend", "yes", "continue"
- Validate manager is real manager from AD
- Call Extension Processor

### Component 4: Extension Processor (Azure Function)
**Logic**:
```
IF reply_is_valid AND current_extension_count < 2 AND today < max_90_day_limit:
  new_disable_date = today + 30 days
  update_db(status = EXTENDED, new_disable_date)
  extension_count += 1
ELSE IF extension_count >= 2:
  send_email_to_manager("Max extensions reached")
ELSE:
  ignore_reply
```

---

## 🗄️ DATABASE SETUP (5 minutes)

```sql
-- Run in Azure SQL Database
CREATE TABLE EFTracking (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    userId NVARCHAR(255) NOT NULL,
    userEmail NVARCHAR(255) NOT NULL,
    managerId NVARCHAR(255),
    managerEmail NVARCHAR(255),
    offboardDate DATETIME2 NOT NULL,
    currentDisableDate DATETIME2 NOT NULL,
    extensionCount INT DEFAULT 0,
    status NVARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    lastAlertDate DATETIME2,
    createdAt DATETIME2 DEFAULT GETDATE(),
    updatedAt DATETIME2 DEFAULT GETDATE()
);

-- Status values: ACTIVE, ALERT_SENT, EXTENSION_PENDING, EXTENDED, DISABLED
```

---

## 🚀 ALERT SCHEDULE OPTIONS

### Option 1 (Recommended): Single Alert on Day 25
- Simpler to manage
- Still gives manager 5 days to respond
- Less email noise

### Option 2: Two Alerts (Day 21 & 28)
- More chances to catch manager attention
- Risk of alert fatigue
- More operational overhead

### Option 3 (Hybrid): Smart Escalation
- Day 25: Alert to manager
- Day 28: If no reply, alert to Manager + IT + Manager's Manager (escalation)

**Recommendation**: Start with Option 1, move to Option 3 if needed

---

## 📧 EMAIL REPLY PROCESSING

### Challenge: How to identify which user the extension is for?

### Solution A: Reply-To with Token (RECOMMENDED)
```
Reply-To: ef-extend-{userId}@company.com

// Azure Function webhook:
1. Extract userId from "To" address
2. Look up record in database
3. Validate sender = manager
4. Process extension
```

**Pros**: Foolproof, can't be confused
**Cons**: Need mail forwarding setup

### Solution B: Parse Email Subject/Body
```
Subject: Re: Email Forwarding Expiration Notice - Action Required - [john.doe@company.com]

// Parse:
1. Extract email in brackets
2. Look up user
3. Check if body contains "extend"/"yes"
```

**Pros**: Works with any reply
**Cons**: Error-prone, can fail with forwarding

---

## ⏰ TIMELINE EXAMPLE

```
Day 0 (Apr 23): 
  - User offboarded
  - Extension Attribute 10 = 2026-04-23T12:28:34.084-07:00
  - Status = ACTIVE

Day 25 (May 18):
  - Alert sent to manager
  - Status = ALERT_SENT

Day 26 (May 19):
  - Manager replies "EXTEND"
  - Extension Processor runs
  - New disable date = Day 55 (May 23)
  - Status = EXTENDED (30 Days)
  - Extension count = 1

Day 30 (May 23):
  - IF no prior extension: Auto-disable, forwarding OFF
  - IF already extended: Continue monitoring

Day 55 (June 19):
  - Second alert (if allowed second extension)
  - Manager can reply again
  - New disable date = Day 85
  - Status = EXTENDED (60 Days)
  - Extension count = 2

Day 85 (July 19):
  - IF no reply: Auto-disable (final)
  - Status = DISABLED
  - Max 90 days reached (hard stop)
```

---

## 🔐 SECURITY & PERMISSIONS

### Azure AD Graph API Permissions (Managed Identity)
```
- Directory.Read.All (query terminated users)
- User.Read.All (read manager info)
```

### App Registration (if using Service Principal)
```
- Directory.Read.All
- Mail.Send (if sending via Graph API)
```

### Database Access
```
- Read: EFTracking table
- Write: EFTracking, EFAlerts tables
- Execute: Stored procedures (optional)
```

---

## 🧪 TESTING CHECKLIST

### Manual Testing
- [ ] Query Azure AD for terminated users
- [ ] Send test alert email
- [ ] Verify manager email field accuracy
- [ ] Test with dummy user (Employee Type = Terminated, Ext Attr 10 = date)
- [ ] Parse sample manager replies
- [ ] Verify disable date calculations
- [ ] Test at Day 25, 30, 60, 90 boundaries

### Automated Testing
- [ ] Unit tests for date calculations
- [ ] Integration tests with Azure AD
- [ ] Email template rendering
- [ ] Database CRUD operations
- [ ] Edge cases (leap years, timezone boundaries)

---

## 📊 MONITORING & ALERTS

### Key Metrics to Track
```
✓ Daily: # users in ACTIVE status
✓ Daily: # alerts sent today
✓ Daily: # extensions processed today
✓ Daily: # auto-disables completed today
✓ Weekly: Manager response rate
✓ Monthly: Total users automated vs manual
```

### Set Up Alerts for:
- ❌ Failed Graph API calls (retry > 5x)
- ❌ Email send failures
- ❌ Database connection errors
- ❌ Unprocessed replies (webhook failures)

---

## 🌍 US EXPANSION PREP (Future)

When expanding to US employees:
1. **Timezone Handling**: Store user's timezone, schedule alerts in their local time
2. **Regional AD**: Separate query for US users if using different Azure AD tenant
3. **Compliance**: Check US-specific retention policies (may differ from India)
4. **Email**: May need separate IT contact list for US region

---

## 📞 HANDOFF TO IT TEAM

### What IT Team Needs to Know
1. **Daily Check**: System runs automatically at 9 AM UTC. No manual intervention needed.
2. **Alert Response**: Managers should reply to email with "EXTEND" or "YES" to extend forwarding.
3. **Monitoring**: Check dashboard weekly for failed operations.
4. **Override**: Manual disable/extend available in database if needed for exceptions.
5. **Audit Trail**: All actions logged for compliance.

### IT Team Troubleshooting
- Alert didn't send? Check recipient's spam folder, then check Logic App run history
- Manager's extension not processed? Check if manager replied from correct email
- User not in system? Verify Employee Type = "Terminated" and Extension Attribute 10 is set

---

## 💡 QUICK DECISION MATRIX

| Decision | Recommendation | Alternative |
|----------|---|---|
| **Alert Tool** | Logic Apps | Azure Functions |
| **Alert Schedule** | Day 25 only | Day 21 & 28 |
| **Manager Reply Format** | Reply-to with token | Parse email subject |
| **Database** | Azure SQL | Cosmos DB / Table Storage |
| **Execution Time** | 9 AM UTC | Trigger on offboarding event |
| **Max Extension** | 90 days (2 x 30-day) | 60 days or 120 days |

---

