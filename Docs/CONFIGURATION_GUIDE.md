# Email Forwarding Automation - Decision Trees & Configuration Guide

## 🌳 CONFIGURATION DECISIONS

### Decision 1: Alert Schedule

```
Question: How many alerts should we send?
├─ OPTION A: Single Alert on Day 25 ⭐ RECOMMENDED
│  ├─ Pros: Simpler, less email noise, still gives 5 days to respond
│  ├─ Cons: Only one chance to get manager's attention
│  └─ Best for: High manager response rate (> 80%)
│
├─ OPTION B: Two Alerts (Day 21 & 28)
│  ├─ Pros: More chances for manager to see alert
│  ├─ Cons: Email fatigue, more operations overhead
│  └─ Best for: Lower manager response rate (< 50%)
│
└─ OPTION C: Smart Escalation (Day 25 & Day 28 if no reply)
   ├─ Pros: Balanced - one alert normally, escalate if no reply
   ├─ Cons: More complex logic
   └─ Best for: Medium response rates (50-80%)

🎯 RECOMMENDATION: Start with OPTION A (Day 25 only)
                   Move to C if response rate < 80%
```

### Decision 2: Email Reply Method

```
Question: How should managers request email forwarding extension?
├─ METHOD A: Reply to Email with Token (Reply-To: ef-extend-{userId}) ⭐ RECOMMENDED
│  ├─ Mechanism: Parse "To" address instead of email body
│  ├─ Pros: Foolproof, works with email forwarding/delegation
│  ├─ Cons: Requires mail routing setup
│  ├─ Error Rate: ~0.1% (parsing failures only)
│  └─ Implementation: 2-3 hours
│
├─ METHOD B: Parse Email Body for Keywords
│  ├─ Mechanism: Look for "extend", "yes", "continue" in reply body
│  ├─ Pros: Works with any reply, no special email setup needed
│  ├─ Cons: Fragile (can fail with forwarding, forwarded message text)
│  ├─ Error Rate: ~5-10%
│  └─ Implementation: 1 hour
│
└─ METHOD C: Web Portal Link
   ├─ Mechanism: Email contains "Click here to extend" button
   ├─ Pros: Structured, no email parsing
   ├─ Cons: Requires users to click (lower response rate)
   ├─ Error Rate: ~0% (portal is reliable)
   └─ Implementation: 1-2 weeks (need portal)

🎯 RECOMMENDATION: Use METHOD A (token-based) for reliability
                   Fallback to METHOD B if routing not available
```

### Decision 3: Technology Stack

```
Question: Which Azure services should we use?
├─ ORCHESTRATION LAYER
│  ├─ OPTION A: Azure Logic Apps ⭐ RECOMMENDED (For MVP)
│  │  └─ Best for: Visual workflows, IT team modifications, no coding
│  └─ OPTION B: Azure Functions (Python)
│     └─ Best for: Complex logic, full programming control
│
├─ DATABASE LAYER
│  ├─ OPTION A: Azure SQL Database ⭐ RECOMMENDED
│  │  └─ Best for: Relational data, audit trails, easy querying
│  └─ OPTION B: Azure Cosmos DB
│     └─ Best for: High scale, NoSQL, multi-region
│
├─ EMAIL LAYER
│  ├─ OPTION A: SendGrid ⭐ RECOMMENDED (3rd party)
│  │  └─ Best for: Simple, reliable, good deliverability
│  └─ OPTION B: Office 365 Graph Mail API
│     └─ Best for: Native to enterprise, no extra cost
│
└─ MONITORING LAYER
   ├─ OPTION A: Application Insights ⭐ RECOMMENDED
   │  └─ Best for: Built-in to Azure, dashboards, alerting
   └─ OPTION B: Azure Monitor only
      └─ Best for: Basic logging, cost-sensitive

🎯 RECOMMENDATION: Logic Apps + SQL + SendGrid + App Insights
                   (Easiest to maintain, good cost-benefit)
```

### Decision 4: Maximum Extension Period

```
Question: What's the hard limit for email forwarding?
├─ OPTION A: 30 days total (No extensions) ❌ NOT RECOMMENDED
│  └─ Reason: Defeats purpose of having "extension" capability
│
├─ OPTION B: 60 days total (1 extension) 
│  └─ Use when: Want to limit extensions, encourage permanent solutions
│
├─ OPTION C: 90 days total (2 extensions of 30 days each) ⭐ RECOMMENDED
│  └─ Reason: Balances flexibility with policy enforcement
│     Gives: 30 days initially, 30 days extension 1, 30 days extension 2
│
└─ OPTION D: 120+ days (3+ extensions)
   └─ Use when: Want maximum flexibility (less recommended)

🎯 RECOMMENDATION: 90 days (2 extensions max)
                   Formula: 3 periods × 30 days = 90 days

SCHEDULE:
  Days 0-30:   Initial period (alert on Day 25)
  Days 30-60:  First extension (alert on Day 25 of period 2, i.e., Day 55)
  Days 60-90:  Second extension (no further extensions after this)
  Day 90:      FINAL DISABLE (hard stop)
```

### Decision 5: Alert Timing (UTC vs Local)

```
Question: When should alerts be sent?
├─ OPTION A: Fixed time in UTC ⭐ RECOMMENDED (For MVP/India only)
│  ├─ Time: 9:00 AM UTC daily
│  ├─ Pros: Simple, consistent, easier to debug
│  ├─ Cons: Different local times for different regions
│  └─ Impact: India (2:30 PM IST), US varies by timezone
│
└─ OPTION B: Local time for each user/manager
   ├─ Time: 9:00 AM in manager's local timezone
   ├─ Pros: Professional, received during business hours
   ├─ Cons: Complex logic, different function executions per region
   └─ Use when: Expanding to US/multi-region

🎯 RECOMMENDATION: Start with UTC (9 AM)
                   Move to local time when expanding to US
```

### Decision 6: Manual Override Capability

```
Question: Should IT be able to manually extend/disable?
├─ OPTION A: No manual override ❌ NOT RECOMMENDED
│  └─ Reason: Creates exceptions, audit trail complexity
│
├─ OPTION B: IT can extend (only) ⭐ RECOMMENDED
│  ├─ Use case: Manager didn't reply in time, but still needs it
│  ├─ Audit: Log who, when, why for compliance
│  └─ Limit: 1 manual extension per user, then auto-expire
│
└─ OPTION C: IT can extend or disable (full control)
   ├─ Use case: Exceptions, policy changes, emergency disable
   ├─ Audit: Mandatory reason/comment for all overrides
   └─ Best practice: Require IT Director approval for extensions

🎯 RECOMMENDATION: OPTION B (extend only, with audit logging)
                   Add emergency disable for security incidents
```

---

## 🔍 IMPLEMENTATION DECISION MATRIX

| Decision | Recommended | Alternative | Complexity | Cost | Timeline |
|----------|-------------|-------------|-----------|------|----------|
| Alert Schedule | Day 25 only | Day 21+28 | Low | $0 | 1 day |
| Reply Method | Token-based | Body parsing | Medium | $100 | 3 days |
| Orchestration | Logic Apps | Functions | Low | $10-30/mo | 1 week |
| Database | SQL | Cosmos DB | Low | $20-50/mo | 2 days |
| Email Service | SendGrid | Office 365 | Low | $20/mo | 2 days |
| Max Extension | 90 days | 60 or 120 | Low | $0 | Config |
| Timing | UTC 9 AM | Local time | High | $0 | Week 3+ |
| Manual Override | Yes (extend) | No or Yes (all) | Low | $0 | Config |

---

## 📊 CONFIGURATION BY SCENARIO

### SCENARIO 1: Startup/MVP (Fastest to Market)
```
Timeline: 2 weeks
Cost: ~$50/month
Team: 1 developer

Config:
- Alert: Day 25 only
- Reply: Token-based (email routing required)
- Stack: Logic Apps + SQL + SendGrid
- Max: 90 days (2 extensions)
- Override: IT can extend only
- Timing: 9 AM UTC

Trade-off: Less flexible, but simple and fast
```

### SCENARIO 2: Enterprise (Full Featured)
```
Timeline: 4 weeks
Cost: ~$100/month
Team: 2-3 developers

Config:
- Alert: Day 25 primary + Day 28 escalation if no reply
- Reply: Token-based + body parsing fallback
- Stack: Functions + SQL + Office 365 Graph API
- Max: 90 days with discretionary override
- Override: Manager + IT can extend, DBA can override
- Timing: Local timezone per user

Trade-off: More complex, but handles edge cases
```

### SCENARIO 3: Cost-Conscious (Minimal Spend)
```
Timeline: 3 weeks
Cost: ~$30/month
Team: 1 developer

Config:
- Alert: Day 25 only
- Reply: Email body parsing (simpler)
- Stack: Logic Apps + Table Storage + Office 365 Graph Mail
- Max: 60 days (1 extension only)
- Override: Manual database edit only
- Timing: 9 AM UTC

Trade-off: Less features, but lowest cost
```

---

## 🎯 PRE-IMPLEMENTATION DECISIONS

Before starting development, confirm these decisions:

```
1. Alert Schedule
   ☐ Day 25 only
   ☐ Day 21 & 28
   ☐ Day 25 + escalate Day 28 if no reply

2. Reply Method
   ☐ Token-based (ef-extend-{userId}@company.com)
   ☐ Email body keyword parsing
   ☐ Web portal link in email

3. Technology Stack
   ☐ Logic Apps + SQL + SendGrid
   ☐ Functions + SQL + Office 365 Graph
   ☐ Logic Apps + Cosmos DB + SendGrid

4. Maximum Extension
   ☐ 30 days total (no extensions)
   ☐ 60 days total (1 extension)
   ☐ 90 days total (2 extensions)
   ☐ 120+ days (multiple extensions)

5. Timing
   ☐ Fixed UTC time (9 AM)
   ☐ Local timezone per manager
   ☐ Business hours (9 AM in recipient's timezone)

6. Manual Override
   ☐ No override possible
   ☐ IT can extend only
   ☐ IT can extend or disable
   ☐ Full override with approval workflow

7. Notification Channels
   ☐ Email only
   ☐ Email + Teams message
   ☐ Email + SMS backup

8. Audit Requirements
   ☐ Basic logging (who, what, when)
   ☐ Detailed audit trail (why, approval chain)
   ☐ Compliance export capability
```

---

## ⚙️ CONFIGURATION FILE (config.json)

```json
{
  "version": "1.0",
  "deployment": {
    "region": "India",
    "environment": "production"
  },
  "alerts": {
    "enabled": true,
    "scheduleType": "fixed_day",
    "dayOfExpiry": 25,
    "timezoneUtc": true,
    "timeOfDay": "09:00",
    "escalationEnabled": false,
    "escalationDay": 28
  },
  "extension": {
    "maxTotalDays": 90,
    "daysPerExtension": 30,
    "maxExtensionCount": 2,
    "requiresManagerApproval": true
  },
  "replyProcessing": {
    "method": "token_based",
    "replyToFormat": "ef-extend-{userId}@company.com",
    "keywords": ["extend", "yes", "continue"],
    "caseSensitive": false,
    "validateSenderEmail": true
  },
  "manualOverride": {
    "enabled": true,
    "allowedRoles": ["ITManager", "ITDirector"],
    "requiresApproval": true,
    "auditLogging": true
  },
  "notifications": {
    "channels": ["email"],
    "emailService": "sendgrid",
    "sendTech": "cc_to_it_always",
    "itDistributionList": "it-operations@company.com"
  },
  "audit": {
    "loggingLevel": "detailed",
    "retentionDays": 365,
    "complianceExportEnabled": true
  }
}
```

---

## 🚀 QUICK DECISION GUIDE

**If you have 2 weeks and 1 developer** → Use SCENARIO 1 (MVP)
**If you have 4 weeks and 2-3 developers** → Use SCENARIO 2 (Enterprise)
**If budget is tight** → Use SCENARIO 3 (Cost-Conscious)

**Default recommendation**: SCENARIO 1 (MVP)
- Fastest to value
- Covers 95% of use cases
- Easy to enhance later

---

