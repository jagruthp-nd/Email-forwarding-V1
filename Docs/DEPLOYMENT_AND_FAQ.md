# Email Forwarding Automation - Deployment & FAQ

## 🚀 DEPLOYMENT ROADMAP

### Phase 1: Foundation (Week 1)
- [ ] Create Azure SQL Database
- [ ] Run schema SQL scripts
- [ ] Set up Managed Identity for Azure Functions
- [ ] Grant Graph API permissions (Directory.Read.All)
- [ ] Create Azure Storage Account (for state/audit logs)

### Phase 2: Core Functions (Week 2)
- [ ] Deploy `monitor_ef_expiration.py` function
- [ ] Set up daily timer trigger (9 AM UTC)
- [ ] Deploy `process_manager_reply.py` function
- [ ] Set up email webhook trigger
- [ ] Test with 5-10 sample terminated users in dev environment

### Phase 3: Email Integration (Week 2-3)
- [ ] Configure SendGrid or Office 365 Graph Mail API
- [ ] Create email templates (HTML + plain text)
- [ ] Set up reply-to address routing (`ef-extend-{userId}@company.com`)
- [ ] Test email send and reply flow
- [ ] Configure IT operations distribution list

### Phase 4: Monitoring & Logging (Week 3)
- [ ] Set up Application Insights
- [ ] Create alerts for failed operations
- [ ] Build Power BI dashboard for tracking
- [ ] Document troubleshooting procedures for IT team

### Phase 5: UAT & Cutover (Week 4)
- [ ] Run UAT with 50-100 real users
- [ ] Test all scenarios (alert, extension, disable, max extensions)
- [ ] Verify no missed users
- [ ] Train IT team
- [ ] Go-live in production

---

## ✅ PRE-DEPLOYMENT CHECKLIST

### Infrastructure
- [ ] Azure subscription with adequate quota
- [ ] Azure SQL Database provisioned (DTU or vCore)
- [ ] Azure Storage Account for Function app
- [ ] Application Insights workspace
- [ ] Key Vault for secrets (SendGrid API key, database connection strings)

### Azure AD Setup
- [ ] Verify extension attributes are configured
  ```powershell
  # PowerShell: Check extension attribute
  Get-AzureADUser -Filter "userPrincipalName eq 'user@company.com'" | Select-Object extensionAttributes
  ```
- [ ] Manager relationships populated in Azure AD
- [ ] At least 5 test users marked as `Employee Type = Terminated`

### Application Setup
- [ ] Python 3.9+ runtime for Functions
- [ ] Required Python packages installed (`azure-identity`, `msgraph-core`, etc.)
- [ ] Environment variables configured (see below)
- [ ] Database connection string in Key Vault

### Email Setup
- [ ] SendGrid API key or Office 365 credentials
- [ ] IT distribution list email address verified
- [ ] Email templates reviewed by management
- [ ] Test email domain / sender verified

### Monitoring
- [ ] Application Insights connected to Function App
- [ ] Alert rules created for failures
- [ ] Log retention policy configured
- [ ] Dashboard created for daily review

---

## 🔑 ENVIRONMENT VARIABLES

```bash
# In Azure Function App Configuration:

# Database
DB_CONNECTION_STRING=Server=tcp:yourserver.database.windows.net;Database=EFManagement;Encrypted=true;Connection Timeout=30;

# Email (SendGrid)
SENDGRID_API_KEY=SG.xxxxx

# Email (Office 365)
OFFICE365_TENANT_ID=your-tenant-id
OFFICE365_CLIENT_ID=your-client-id
OFFICE365_CLIENT_SECRET=your-secret

# Application
IT_EMAIL=it-operations@company.com
COMPANY_NAME=Netradyne
REGION=IND  # IND or US
TIMEZONE=UTC  # Change for US expansion
ALERT_DAY=25
HARD_LIMIT_DAYS=90
```

---

## 🎯 SUCCESS CRITERIA

- ✅ 100% of terminated users with EF in system are tracked
- ✅ Alerts sent on correct day (Day 25) to correct manager
- ✅ Manager replies successfully trigger extension (no failures)
- ✅ Auto-disable occurs exactly on schedule
- ✅ Max 90-day limit enforced (no extension beyond)
- ✅ All actions logged for audit trail
- ✅ Zero manual interventions needed
- ✅ IT team can troubleshoot via dashboard

---

## 📊 DAILY OPERATIONS

### 9:00 AM UTC (Daily)
- Function runs automatically
- Queries terminated users
- Sends alerts if day = 25
- Auto-disables if day = 30/60/90

### Throughout the Day
- Webhook listens for manager email replies
- Processes extensions automatically
- Updates database status

### End of Day (5 PM UTC)
- IT team reviews dashboard
- Checks for any failed operations
- Investigates if > 2 failures

### Weekly (Every Monday)
- Generate status report (# alerts sent, # extensions granted, # disables)
- Review audit log for anomalies
- Check for unprocessed replies

---

## ❓ FREQUENTLY ASKED QUESTIONS

### Q1: What if the manager's email is wrong in Azure AD?
**A**: The system will fail to send the alert. 
- **Mitigation**: Validate manager email before offboarding. 
- **Fallback**: Send to IT operations if manager email is missing/invalid.

---

### Q2: What if the manager replies from a different email address?
**A**: Reply validation will fail because sender email doesn't match manager email in Azure AD.
- **Mitigation**: Use reply-to address with token format (`ef-extend-{userId}`) instead of parsing email body.
- **Alternative**: Accept replies from manager's manager or delegate if needed.

---

### Q3: What if a manager accidentally replies "no" or "deny"?
**A**: The system will NOT process extension (only looks for approval keywords).
- **Behavior**: Email forwarding will be auto-disabled on Day 30 as expected.
- **Recovery**: Manager can request manual extension by contacting IT.

---

### Q4: What if the system crashes and misses the Day 25 alert?
**A**: Alert will be sent on Day 26 (next day when function runs again).
- **Mitigation**: Set up alerting for function failures in Application Insights.
- **Recovery**: IT team can manually send alert and update timestamp.

---

### Q5: Can a user request extension themselves?
**A**: No, only manager can request via email reply.
- **Reason**: Compliance - manager approval required per company policy.
- **Alternative**: User asks manager → manager replies "EXTEND".

---

### Q6: What if a user deletes their email in Exchange?
**A**: Email forwarding rules cannot be deleted if disabled via API.
- **Behavior**: System attempts disable, logs error, alerts IT team.
- **Recovery**: IT manually cleans up user account.

---

### Q7: Can the extension be requested after Day 30?
**A**: No, extension must be requested before Day 30.
- **Reason**: Auto-disable happens exactly on Day 30 at 9 AM UTC.
- **Late Request**: IT can grant manual 30-day extension if requested shortly after.

---

### Q8: What happens if max 90 days is reached?
**A**: Email forwarding is permanently disabled. No further extensions possible.
- **Reason**: Company policy (90-day hard limit).
- **Exception**: Only CEO/IT Director can override (requires manual process + audit log).

---

### Q9: How do we handle US employees (different timezone)?
**A**: Store user's timezone in database. Schedule alerts in their local 9 AM.
- **Implementation**: 
  ```python
  if region == "US":
      user_tz = get_user_timezone(user_id)  # EST, CST, MST, PST
      alert_time = convert_to_user_tz(9_am_utc, user_tz)
  ```

---

### Q10: What if a user is un-terminated (hired back)?
**A**: System will continue processing if `Employee Type = Terminated`.
- **Mitigation**: HR must update `Employee Type` back to "Active" on re-hire.
- **Detection**: Run weekly audit to find discrepancies between Azure AD and HRIS.

---

### Q11: Can we extend for more than 30 days per request?
**A**: No, each extension is exactly 30 days by design.
- **Reasoning**: Encourages manager to plan for permanent solutions.
- **Max**: 3 extensions = 90 days total (Day 30, 60, 90).

---

### Q12: What audit trail is kept?
**A**: All actions logged in EFAlerts table:
- Alert sent (date, recipient, template)
- Manager reply received (date, sender, content, action)
- Extension granted (date, new disable date, count)
- Auto-disable executed (date, timestamp)
- Errors encountered (date, error message, retry count)

---

## 🆘 TROUBLESHOOTING GUIDE

### Alert Email Not Sent
**Check**:
1. Function ran? Check Application Insights → Timeline
2. Graph API call succeeded? Check log entry for 200 status
3. Manager email valid? Query Azure AD for user.manager.mail
4. SendGrid API key correct? Test with curl
5. Network access? Check Function App outbound IPs allowlisted

**Fix**: 
- Re-run function manually from Azure Portal
- Check email spam folder
- Update manager email in Azure AD if invalid
- Test with IT distribution list first

---

### Manager Reply Not Processed
**Check**:
1. Webhook received the email? Check Application Insights for POST request
2. Sender email matches manager email? Compare exact strings (case-sensitive)
3. Reply contains keyword? Check if body has "extend" or "yes"
4. Tracking record exists? Query database for RowKey = userId
5. User already has max extensions? Check extensionCount = 2

**Fix**:
- Ask manager to reply again with "EXTEND" keyword
- Verify manager email format (lowercase, no spaces)
- Manually update database if needed (note in audit log)

---

### Auto-Disable Not Happening
**Check**:
1. Function ran on Day 30? Check Application Insights timeline
2. Status was not already "EXTENDED"? Check database
3. User still in Azure AD? Check if deleted
4. Disable operation succeeded? Check Graph API response code

**Fix**:
- Manually disable email forwarding via Exchange Admin Center
- Update database status to "DISABLED"
- Investigate Graph API errors in logs

---

### Too Many Alerts Going Out
**Check**:
1. Is today actually Day 25? Verify date logic
2. Are there really that many new terminates? Check count
3. Is function running multiple times? Check trigger settings

**Fix**:
- Adjust alert schedule to Day 25 only (remove Day 21+28)
- Batch alerts and send daily digest to IT
- Confirm high number of terminates with HR

---

## 📞 ESCALATION CONTACTS

### Level 1 - First Response (IT Help Desk)
- **Issue**: Alert not arriving
- **Action**: Check manager email spam, verify recipient list
- **Escalate to**: IT Manager if unresolved in 2 hours

### Level 2 - Functional Issues (IT Manager)
- **Issue**: Extension not processing, disable failed
- **Action**: Check Application Insights, manually intervene if needed
- **Escalate to**: Cloud Architect if infrastructure issue

### Level 3 - Emergency Override (IT Director)
- **Issue**: User needs exception beyond 90 days
- **Action**: Approve with business justification, log exception, set manual reminder
- **Escalate to**: Management + Compliance

---

## 📈 CONTINUOUS IMPROVEMENT

### Monthly Metrics Review
- % of alerts successfully delivered
- % of manager responses to alerts
- % of auto-disables on schedule
- # of manual interventions needed
- # of users extending vs. auto-disabling
- Average days of forwarding used (vs. policy max of 30)

### Quarterly Process Review
- Feedback from IT team
- Feedback from managers
- Proposed policy adjustments
- Cost analysis (function calls, storage, compute)

### Annual Planning
- Roadmap for US expansion
- Multi-region timezone management
- Integration with HRIS system
- Compliance audit

---

## 💰 COST ESTIMATION (Azure India Region)

| Component | Estimated Monthly Cost |
|-----------|----------------------|
| Azure SQL Database (S0 DTU) | $15 |
| Azure Functions (1M invocations @ $0.2/M) | $5 |
| Application Insights (1 GB ingestion) | $5 |
| Storage Account (minimal usage) | $1 |
| SendGrid (100k emails @ $10/50k) | $20 |
| **Total Monthly** | **~$46** |

**Assumptions**:
- ~300 terminated users per month
- 1 alert per user
- 30% extend once, 10% extend twice
- ~500 total emails per month

---

## 🔒 SECURITY CONSIDERATIONS

### Data Protection
- All user data in encrypted database (Transparent Data Encryption)
- Connections use TLS 1.2+
- Managed Identity - no API keys in code
- Secrets in Azure Key Vault (SendGrid key, DB connection)

### Access Control
- Function App Managed Identity has minimal permissions (read-only for Graph API)
- Database has separate service account (read-write on EF tables only)
- IT team access via Azure RBAC

### Audit & Compliance
- All actions logged (who, what, when, why)
- Logs retained 1 year for compliance
- Email communications preserved in Office 365
- Monthly audit report for management

---

## 📝 SIGN-OFF & APPROVAL

**Prepared by**: [Your Name]  
**Date**: [Date]  
**Approved by**: IT Manager / Director  
**Effective Date**: [Go-live date]

---

