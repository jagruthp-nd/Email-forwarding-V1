# Workflow Comparison & Recommendation

**Audience**: IT Director, HR, Infosec, Management  
**Decision**: Select Workflow A (Automated) or Workflow B (Approval-based)

---

## 1  Side-by-side comparison

| Dimension | Workflow A – Automated | Workflow B – Approval-based |
|-----------|------------------------|------------------------------|
| **How manager requests extension** | Reply to alert email with "EXTEND" | Raise a ticket with business justification |
| **Approval required** | No – manager's reply is sufficient authorisation | Yes – HR + Infosec must both approve |
| **IT involvement per extension** | Zero | Manual attribute update in Azure AD after approval |
| **Extension processed in** | Seconds (automated) | 1–5 business days (depends on approval SLAs) |
| **Risk of missing the deadline** | Low – reply processed immediately | High – approval chain may not complete before Day 30 |
| **Audit trail** | Full – every action logged in Table Storage + Azure Functions logs | Depends on ticket system; attribute change logged in Azure AD audit |
| **Business justification recorded** | Not required | Yes – ticket contains manager's justification |
| **HR/Infosec visibility** | None (they can be CC'ed) | Full – they are active approvers in the ticket |
| **Cost to run** | ~$3–4/month (Azure Functions + Table Storage) | ~$3–4/month + IT engineer time + Waiting time for Approvals |
| **Time to build** | 2-3 weeks | Requires approvals + script changes for attribute polling |
| **Maintenance burden** | Low – serverless, no ongoing manual steps | Medium – ticket workflow, approval routing, SLA monitoring |
| **On-prem AD sync dependency** | None | Yes – attribute update requires AD Connect sync if users are hybrid |
| **Works without IT being available** | Yes – fully autonomous | No – IT must act within the deletion window |

---

## 2  Where Workflow B is genuinely better

Workflow B makes sense in the following specific circumstances:

### 2a – Strict regulatory / compliance requirements
If the organisation is subject to regulations (e.g., SOX, HIPAA, ISO 27001
controls) that explicitly require a **documented, multi-party human approval**
for any extension of access rights to a terminated employee's data, then the
approval chain in Workflow B satisfies that control directly.

Workflow A can partially satisfy this by treating the manager's email reply as
the authorising document — but some auditors may require the HR/Infosec sign-off
that Workflow B provides.

### 2b – High-sensitivity roles
For terminated employees who held privileged access (Finance Director, CISO,
CTO, system administrators), requiring Infosec to explicitly sign off on
extended email forwarding adds a deliberate human checkpoint on data that may
be sensitive.

### 2c – Non-technical managers
If the manager population is not comfortable with email-based commands or is
likely to forward alert emails to assistants who then send the "EXTEND" reply,
a structured ticketing interface may be less error-prone.

---

## 3  Where Workflow A is clearly better

### 3a – Speed to process
The deletion deadline is a hard cut-off.  Workflow B introduces a multi-day
approval chain.  A manager who raises a ticket on Day 28 with a 2-day HR SLA
and a 2-day Infosec SLA will see the account deleted on Day 30 before approvals
are in place.  Either the SLAs must be extremely tight, or the deletion deadline
must be pushed back to give the process time — which defeats the policy purpose.

### 3b – IT workload
At Netradyne's size, manual attribute updates per extension request will
accumulate into recurring IT toil.  Each extension in Workflow B requires:
1. Monitor the ticket queue
2. Confirm both approvals are in place
3. Open Azure AD portal (or run a script)
4. Set the attribute value
5. Verify the daily monitor picks it up
6. Respond to the ticket

With 50 offboardings per year and a 30% EF request rate, that's ~15 manual IT
actions per year minimum.  With second extensions, the number grows.  Workflow A
eliminates all of these.

### 3c – No single point of failure
Workflow B has a critical dependency: an IT Engineer must be available and
responsive within the deletion window.  If the engineer misses updation, a deadline
is missed, and either an account is deleted prematurely (because no one updated
the attribute) or survives past policy (if someone extends the deadline
informally).  Workflow A has no such dependency — the automation acts
regardless of IT availability.

### 3d – Already built and tested
Workflow A code exists, is tested (24/24 unit tests passing), and is ready to
deploy.  Workflow B would require additional development work:
- ITSM ticket integration (ServiceNow / Jira webhook or polling)
- Approval state tracking
- Azure AD attribute-polling logic
- Handling the on-prem AD sync delay for hybrid environments
- SLA alerting if approvals are not received in time

Estimated additional development: 3–5 days of IT engineer time.

---

## 4  Hybrid option (recommended if Workflow B is required)

If stakeholders want the compliance visibility of Workflow B but the reliability
of Workflow A, the following **hybrid approach** is possible without rebuilding
the core automation:

```
Day 25 alert sent (Workflow A email)
  │
  Manager replies "EXTEND"
  │
  Webhook validates sender
  │
  Instead of immediately granting extension:
    → Creates a ticket in ServiceNow/Jira automatically
    → Sets status to "PENDING_APPROVAL"
    → HR and Infosec review the auto-created ticket
    → If approved within SLA: webhook grants extension, updates record
    → If SLA exceeded without approval: account deleted on Day 30
  │
  Confirmation email sent only after ticket approval
```

This hybrid:
- Keeps the automated detection, alerting, and deletion engine of Workflow A
- Adds the formal approval record that compliance may require
- Eliminates the risk of missing the deadline (ticket is auto-created; IT does not need to intervene manually)
- Still requires the ITSM integration to be built

---

## 5  Decision matrix

| Organisation characteristic | Recommended option |
|------------------------------|--------------------|
| Compliance-driven (SOX, HIPAA, ISO 27001) with explicit approval requirements | **Workflow B** or **Hybrid** |
| Standard IT operations, efficiency-focused | **Workflow A** |
| High turnover rate (many offboardings per month) | **Workflow A** |
| Privileged access / sensitive roles | **Hybrid** |
| Small IT team, limited bandwidth | **Workflow A** |
| Already uses ServiceNow / Jira Service Management with mature workflows | **Workflow B** or **Hybrid** |
| On-premises AD sync environment | **Workflow A** (B adds sync latency risk) |

---

## 6  Recommendation

> **Recommended: Workflow A – Fully Automated**

Reasons:
1. **It is already built** — no additional development cost
2. **It is reliable** — eliminates the approval-chain timing risk that could cause premature deletions
3. **It produces a full audit trail** — every alert, extension, and deletion is logged in Azure Table Storage with timestamps and reasons
4. **It frees up IT bandwidth** — ongoing effort is zero after initial deployment
5. **It is policy-compliant** — the manager's explicit "EXTEND" reply constitutes authorisation, with the manager's email identity as authentication
6. **It is recoverable** — all deletions land in Entra's 30-day recycle bin

The manager's "EXTEND" reply serves as a documented, timestamped authorisation
from the person accountable for the business decision — no different in
principle from clicking "Approve" in a ticketing system, but without the process
overhead.

If a compliance audit specifically requires an HR/Infosec co-approval on the
record, implement the **Hybrid option** as a Phase 2 enhancement on top of
the existing Workflow A codebase.

---

## 7  Summary of what changes if Workflow B is selected

| Item | Change required |
|------|----------------|
| `reply_webhook.py` | Replace with ticket-poll logic |
| `monitor_accounts.py` | Add `extensionAttribute11` check before delete |
| `graph_api.py` | Add `patch_user()` to clear attribute post-extension |
| `local.settings.json` | Add ITSM API credentials |
| New file: `itsm_client.py` | Ticket creation + approval status polling |
| Infrastructure | ITSM API secret in Key Vault; network access to ITSM endpoint |
| New Power Automate flow | Route approval events from ITSM to webhook |
| **Estimated effort** | **3–5 additional development days** |

None of these changes affect the infrastructure, Table Storage schema,
email templates, or core deletion logic that was already built.
