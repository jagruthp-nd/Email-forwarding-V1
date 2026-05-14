# Email Forwarding Automation - Project Design & Implementation Plan

## 1. REQUIREMENTS SUMMARY

### Business Requirements
- **Scope**: India (IND) users initially, US expansion later
- **Trigger**: Employee offboarding with Email Forwarding (EF) request
- **Policy**: 30-day maximum email forwarding duration
- **Pain Point**: Currently manual process → high miss rate on expirations

### Key Rules
1. **Alert Schedule**:
   - Day 21 & 28: Send alert to Manager + IT (CC)
   - Alternative (if only 1 alert possible): Day 25
   - Message: "EF will be disabled on [DATE]. Reply to extend for 30 more days."

2. **Extension Logic**:
   - Each extension adds 30 days
   - Maximum 90 days total from offboarding date
   - Manager reply required to extend (no explicit acknowledgment ≠ approval)

3. **Auto-Disable**:
   - Day 30 (first): Auto-disable if no extension
   - Day 60 (if extended once): Auto-disable if no further extension
   - Day 90 (if extended twice): Final disable (hard limit)

4. **User Attributes** (Azure AD):
   - `Employee Type = "Terminated"`
   - `Extension Attribute 10 = "2026-04-23T12:28:34.084-07:00"` (offboarding date/time)

---

## 2. FEASIBILITY ANALYSIS

### ✅ Feasible Components

| Component | Feasibility | Notes |
|-----------|-------------|-------|
| Azure AD User Filtering | ✅ High | Query users with `Employee Type = Terminated` |
| Extension Attribute Query | ✅ High | Extension Attribute 10 is queryable via Graph API |
| Date Calculations | ✅ High | Day 25/30/60/90 thresholds are straightforward |
| Email Alerts | ✅ High | Office 365 SMTP or SendGrid/Graph Mail API |
| Email Parsing | ⚠️ Medium | Parsing manager replies (approval logic) needs care |
| Auto-Disable | ✅ High | Azure AD Graph API → disable mailbox forwarding |
| Status Tracking | ✅ High | Store in database (SQL/Cosmos) or Azure Table Storage |
| Workflow Orchestration | ✅ High | Azure Logic Apps, Functions, or Durable Functions |

### ⚠️ Considerations

1. **Email Reply Parsing**: Manager replies to alerts are human-generated
   - Recommendation: Use simple keywords ("extend", "yes", "continue") in reply
   - Or: Provide a reply-to address with unique identifier (e.g., `ef-extend-{userId}@company.com`)

2. **Manager Identification**: Map terminating user to manager
   - Source: Azure AD `Manager` attribute (displayName or ID)
   - Fallback: Request System/HRIS data

3. **Timezone Handling**: Dates stored as ISO 8601 in Extension Attribute 10
   - Challenge: Offset varies (-07:00 for Pacific, etc.)
   - Solution: Convert all dates to UTC for consistency

4. **IT Email**: Ensure IT distribution list is accurate and monitored

5. **Region Expansion**: US rollout will need timezone-aware alert scheduling

---

## 3. SYSTEM ARCHITECTURE

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ OFFBOARDING TRIGGER (HR System / Manual)                        │
│ Sets: Employee Type = "Terminated", Ext Attr 10 = offboard date │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ DAILY MONITORING JOB (Azure Function / Logic App - Daily 9 AM) │
│ - Query Azure AD: Terminated users with Ext Attr 10             │
│ - Filter by offboard date range                                 │
│ - Check DB for prior alerts/extensions                          │
│ - Identify users needing action TODAY                           │
└────────────────┬────────────────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
┌──────────────────┐  ┌──────────────────────┐
│ DAY 25: ALERT    │  │ DAY 30/60/90: AUTO   │
│ Send email to    │  │ DISABLE & NOTIFY     │
│ Manager + IT (CC)│  │                      │
│                  │  │ Disable forwarding   │
│ Update DB:       │  │ Log action           │
│ Status = Pending │  │ Update DB: Status =  │
│ Extension        │  │ Disabled             │
└────────┬─────────┘  └──────────┬───────────┘
         │                       │
         ▼                       │
┌──────────────────────┐         │
│ EMAIL WEBHOOK / API  │         │
│ (Reply from Manager) │         │
│                      │         │
│ Parse reply for:     │         │
│ - Extension approval │         │
│ - User ID / Reference│         │
│ - Timestamp          │         │
└────────┬─────────────┘         │
         │                       │
         ▼                       │
┌──────────────────────────────┐ │
│ EXTENSION PROCESSOR          │ │
│                              │ │
│ Validate:                    │ │
│ - Reply from Manager's email │ │
│ - Not past 90-day hard limit │ │
│ - DB record exists           │ │
│                              │ │
│ If valid:                    │ │
│ - Calculate new disable date │ │
│ - Update DB: Status =        │ │
│   Extended (30 Days, 60 Days)│ │
│ - Log extension              │ │
└──────────────────────────────┘ │
                                 │
                                 ▼
                        ┌──────────────────────┐
                        │ COMPLETED / ARCHIVED │
                        │ EF = Disabled        │
                        └──────────────────────┘
```

### Technology Stack Options

#### **Option A: Azure Logic Apps (Recommended for simplicity)**
- **Pros**: 
  - No code required (visual workflow)
  - Native Azure AD integration
  - Built-in email/Teams connectors
  - Easy to modify by non-devs
  - Recurrence trigger for daily job
- **Cons**: 
  - Cost per action
  - Limited error handling
  - Harder for complex logic

#### **Option B: Azure Functions + Service Bus**
- **Pros**:
  - Cost-effective (consumption plan)
  - Full programmatic control
  - Easier testing/CI-CD
  - Can be triggered by multiple sources
- **Cons**:
  - Requires code maintenance
  - Need to build status tracking DB

#### **Option C: Durable Functions (Hybrid)**
- **Pros**:
  - Workflow state management built-in
  - Reliable orchestration
  - Cost-effective
- **Cons**:
  - Steeper learning curve
  - More infrastructure

**Recommended: Option A (Logic Apps) for MVP → Option B (Functions) for scale**

---

## 4. DATA MODEL

### Azure AD Attributes (Existing)
```json
{
  "id": "user-guid",
  "displayName": "John Doe",
  "userPrincipalName": "john.doe@company.com",
  "mail": "john.doe@company.com",
  "employeeType": "Terminated",
  "extensionAttributes": {
    "extensionAttribute10": "2026-04-23T12:28:34.084-07:00"
  },
  "manager": {
    "id": "manager-guid",
    "displayName": "Jane Smith",
    "userPrincipalName": "jane.smith@company.com",
    "mail": "jane.smith@company.com"
  }
}
```

### Database Schema (Tracking Table)
```sql
CREATE TABLE EFTracking (
  id UNIQUEIDENTIFIER PRIMARY KEY,
  userId UNIQUEIDENTIFIER NOT NULL,
  userEmail NVARCHAR(255) NOT NULL,
  managerId UNIQUEIDENTIFIER,
  managerEmail NVARCHAR(255),
  offboardDate DATETIME2 NOT NULL,
  initialDisableDate DATETIME2 NOT NULL,  -- Day 30
  currentDisableDate DATETIME2 NOT NULL,  -- Updates on extension
  extensionCount INT DEFAULT 0,           -- 0, 1, or 2 (max)
  status NVARCHAR(50) NOT NULL,           -- ACTIVE, ALERT_SENT, EXTENSION_PENDING, EXTENDED, DISABLED
  lastAlertDate DATETIME2,
  createdAt DATETIME2 DEFAULT GETDATE(),
  updatedAt DATETIME2 DEFAULT GETDATE(),
  notes NVARCHAR(MAX)                     -- For audit trail
);

CREATE TABLE EFAlerts (
  id UNIQUEIDENTIFIER PRIMARY KEY,
  trackingId UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES EFTracking(id),
  alertDate DATETIME2 NOT NULL,
  alertType NVARCHAR(50) NOT NULL,        -- INITIAL_ALERT, FINAL_ALERT
  sentTo NVARCHAR(255) NOT NULL,
  ccTo NVARCHAR(255),
  status NVARCHAR(50) NOT NULL,           -- SENT, REPLIED, NO_REPLY
  replyDate DATETIME2,
  repliedBy NVARCHAR(255),
  replyContent NVARCHAR(MAX),
  createdAt DATETIME2 DEFAULT GETDATE()
);
```

---

## 5. IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Week 1-2)
- [ ] Set up Azure SQL Database or Cosmos DB for tracking
- [ ] Create tracking table schema
- [ ] Develop Azure Function to query Azure AD (Terminated users)
- [ ] Test filtering logic for Extension Attribute 10
- [ ] Set up managed identity for Graph API access

### Phase 2: Alerts (Week 2-3)
- [ ] Develop email template (HTML, multi-language for future US expansion)
- [ ] Create email send function (SendGrid or Graph Mail API)
- [ ] Implement Logic App / Function trigger (daily at 9 AM UTC)
- [ ] Test alert on Day 25 (or 21+28 split)
- [ ] Set up IT email distribution list

### Phase 3: Manager Reply Processing (Week 3-4)
- [ ] Set up email webhook receiver (Azure Function)
- [ ] Parse manager replies for approval keywords
- [ ] Validate manager identity
- [ ] Update DB with extension request
- [ ] Implement 30-day extension logic with 90-day hard limit

### Phase 4: Auto-Disable (Week 4)
- [ ] Create disable function (Graph API to remove mail forwarding)
- [ ] Test disable workflow
- [ ] Implement audit logging
- [ ] Error handling & retry logic

### Phase 5: Monitoring & Scale (Week 5+)
- [ ] Dashboard (Azure Monitor / Power BI)
- [ ] Alerting for failed operations
- [ ] Documentation
- [ ] US region rollout (timezone handling)

---

## 6. EMAIL TEMPLATES

### Alert Email (Day 25)
```
Subject: Email Forwarding Expiration Notice - Action Required - [Username]

To: manager@company.com
CC: it-operations@company.com

---

Dear [Manager Name],

This is to inform you that the email forwarding for the following terminated employee will expire on [DISABLE_DATE]:

👤 Employee: [Full Name] ([Email])
📅 Offboarding Date: [OFFBOARD_DATE]
⏰ Forwarding Expiration: [DISABLE_DATE]

🔄 ACTION REQUIRED:
If you require the email forwarding to continue beyond the expiration date, please reply to this email with "EXTEND" or "YES" before [DISABLE_DATE].

⚠️ If no action is taken, the email forwarding will be automatically disabled on [DISABLE_DATE], and all incoming emails will be rejected.

Maximum Extension: 90 days from offboarding date (30-day intervals). Current extension: [EXTENSION_COUNT]/2

---

Best regards,
IT Operations Team
Netradyne
```

### Auto-Disable Notification (After Day 30/60/90)
```
Subject: Email Forwarding Disabled - [Username] - [DISABLE_DATE]

To: manager@company.com
CC: it-operations@company.com

---

Dear [Manager Name],

The email forwarding for [Full Name] ([Email]) has been automatically disabled as of [DISABLE_DATE].

No further email forwarding requests will be accepted for this user.

If you believe this was done in error, please contact IT Operations immediately.

---

Best regards,
IT Operations Team
Netradyne
```

---

## 7. RISK MITIGATION

| Risk | Mitigation |
|------|-----------|
| Manager doesn't reply (no intent to extend) | Clear communication in alert. Default = auto-disable. No ambiguity. |
| Email parsing failures | Use reply-to address with unique token: `ef-extend-{userId}@company.com` instead of parsing body text. |
| Manager replies but doesn't see disable date | Include disable date in subject line and multiple places in email. |
| Timezone confusion | Always use UTC for storage. Display local time in email based on user region. |
| Hard delete of email records | Maintain audit trail in DB. Log all actions (sent, extended, disabled). |
| Integration failures (Graph API down) | Retry logic with exponential backoff. Alert IT if > 2 consecutive failures. |
| Users in US region (later) | Store timezone in user profile. Schedule alerts in their local 9 AM. |

---

## 8. SUCCESS METRICS

- **Automation Rate**: % of EF disables automated vs. manual
- **Alert Delivery Rate**: % of emails delivered successfully
- **Manager Response Rate**: % of managers responding to alerts
- **Extension Rate**: % of users requesting extensions (benchmark)
- **On-Time Disable**: % of disables happening exactly on schedule (no delays)
- **Process Efficiency**: Hours saved per month vs. manual process
- **Error Rate**: Failed operations requiring manual intervention

---

## 9. FUTURE ENHANCEMENTS

1. **Self-Service Portal**: Manager/User UI to view/extend EF status
2. **Mobile Alerts**: SMS/Teams messages as backup to email
3. **Compliance Reporting**: Export EF history for audit
4. **Integration**: HRIS system → automatic offboarding trigger
5. **Predictive Analytics**: Forecast EF demand by department
6. **Multi-Region**: Timezone-aware scheduling for global operations
7. **Policy Flexibility**: Configurable alert days & extension duration per department

---

## 10. DEPLOYMENT CHECKLIST

- [ ] Azure SQL Database provisioned
- [ ] Managed Identity configured for Graph API
- [ ] Service Principal / App Registration created
- [ ] Tracking tables created & indexed
- [ ] Logic App / Function deployed (dev environment)
- [ ] Email templates reviewed by stakeholders
- [ ] IT distribution list verified
- [ ] Manager sample list tested
- [ ] Error handling & retry logic implemented
- [ ] Monitoring & alerting configured
- [ ] Documentation completed
- [ ] UAT with IT team
- [ ] Approval from management
- [ ] Production deployment
- [ ] Cutover from manual process
- [ ] Training for IT team

---

