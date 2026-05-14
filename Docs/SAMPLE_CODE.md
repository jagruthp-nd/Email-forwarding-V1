# Email Forwarding Automation - Sample Implementation (Python + Azure)

## 📌 COMPONENT 1: Daily Monitor Function

```python
# monitor_ef_expiration.py
import azure.functions as func
import json
from datetime import datetime, timedelta
from azure.identity import ManagedIdentityCredential
from azure.graphrbac import GraphRbacManagementClient
from msgraph.core import GraphClient
from azure.data.tables import TableClient
import logging

# Configure logging
logger = logging.getLogger(__name__)

def main(req: func.HttpRequest = None, timer: func.TimerRequest = None) -> func.HttpResponse:
    """
    Daily scheduled function to check for users needing email forwarding alerts/disables
    Runs at 9 AM UTC every day
    """
    
    logger.info("Starting EF expiration monitor")
    
    # Setup credentials and clients
    credential = ManagedIdentityCredential()
    graph_client = GraphClient(credential=credential)
    
    # Setup table storage for tracking
    table_client = TableClient.from_connection_string(
        conn_str=os.environ["AzureWebJobsStorage"],
        table_name="EFTracking"
    )
    
    today = datetime.utcnow().date()
    alert_count = 0
    disable_count = 0
    
    try:
        # Query Azure AD for terminated users
        query = """
        $filter=employeeType eq 'Terminated' and 
        extensionAttributes/extensionAttribute10 ne null
        """
        
        users = graph_client.get(f"/users?{query}")
        terminated_users = users.get("value", [])
        
        logger.info(f"Found {len(terminated_users)} terminated users with EF requests")
        
        for user in terminated_users:
            try:
                # Extract offboarding date from Extension Attribute 10
                ext_attr_10 = user.get("extensionAttributes", {}).get("extensionAttribute10")
                if not ext_attr_10:
                    continue
                
                # Parse ISO 8601 date
                offboard_date = parse_iso_date(ext_attr_10)
                offboard_date = offboard_date.date()
                
                # Calculate thresholds
                alert_date = offboard_date + timedelta(days=25)
                disable_date_30 = offboard_date + timedelta(days=30)
                disable_date_60 = offboard_date + timedelta(days=60)
                disable_date_90 = offboard_date + timedelta(days=90)
                
                # Get or create tracking record
                tracking_record = get_or_create_tracking(
                    table_client, 
                    user, 
                    offboard_date
                )
                
                # Determine action
                if today == alert_date and tracking_record["status"] == "ACTIVE":
                    # Send alert to manager
                    send_alert_email(user, tracking_record, disable_date_30)
                    tracking_record["status"] = "ALERT_SENT"
                    tracking_record["lastAlertDate"] = today.isoformat()
                    alert_count += 1
                    
                elif today == disable_date_30 and tracking_record["status"] in ["ALERT_SENT", "ACTIVE"]:
                    # No extension was requested - auto disable
                    disable_ef(user)
                    tracking_record["status"] = "DISABLED"
                    notify_disable(user, tracking_record)
                    disable_count += 1
                    
                elif today == disable_date_60 and tracking_record["status"] == "EXTENDED" and tracking_record["extensionCount"] == 1:
                    # Second alert or auto-disable if no further extension
                    if should_extend_again(tracking_record):
                        tracking_record["status"] = "ALERT_SENT"
                        tracking_record["lastAlertDate"] = today.isoformat()
                        alert_count += 1
                    else:
                        disable_ef(user)
                        tracking_record["status"] = "DISABLED"
                        disable_count += 1
                        
                elif today == disable_date_90 and tracking_record["extensionCount"] == 2:
                    # Hard limit - disable regardless
                    disable_ef(user)
                    tracking_record["status"] = "DISABLED"
                    notify_hard_limit(user, tracking_record)
                    disable_count += 1
                
                # Update tracking record
                tracking_record["updatedAt"] = today.isoformat()
                table_client.upsert_entity(tracking_record)
                
            except Exception as e:
                logger.error(f"Error processing user {user.get('userPrincipalName')}: {str(e)}")
                continue
        
        return func.HttpResponse(
            json.dumps({
                "status": "completed",
                "alerts_sent": alert_count,
                "auto_disables": disable_count,
                "timestamp": today.isoformat()
            }),
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"Fatal error in monitor: {str(e)}")
        return func.HttpResponse(
            json.dumps({"status": "failed", "error": str(e)}),
            status_code=500
        )


def parse_iso_date(iso_string):
    """Parse ISO 8601 date string with timezone"""
    # Example: "2026-04-23T12:28:34.084-07:00"
    return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))


def get_or_create_tracking(table_client, user, offboard_date):
    """Get existing or create new tracking record"""
    user_id = user["id"]
    
    try:
        record = table_client.get_entity(partition_key="EF", row_key=user_id)
        return record
    except:
        # Create new record
        record = {
            "PartitionKey": "EF",
            "RowKey": user_id,
            "userId": user_id,
            "userEmail": user.get("mail", user.get("userPrincipalName")),
            "managerId": user.get("manager", {}).get("id"),
            "managerEmail": user.get("manager", {}).get("mail"),
            "offboardDate": offboard_date.isoformat(),
            "currentDisableDate": (offboard_date + timedelta(days=30)).isoformat(),
            "extensionCount": 0,
            "status": "ACTIVE",
            "createdAt": datetime.utcnow().isoformat()
        }
        return record


def send_alert_email(user, tracking_record, disable_date):
    """Send alert email to manager"""
    # Implementation would call SendGrid or Office 365 Graph API
    logger.info(f"Sending alert email to manager for {user.get('displayName')}")
    # TODO: Implement email sending
    pass


def disable_ef(user):
    """Disable email forwarding for user"""
    # Implementation would call Graph API to remove mailbox forwarding rules
    logger.info(f"Disabling EF for {user.get('displayName')}")
    # TODO: Implement EF disable via Graph API
    pass


def notify_disable(user, tracking_record):
    """Notify manager that EF has been disabled"""
    logger.info(f"Notifying manager of disable for {user.get('displayName')}")
    # TODO: Send disable notification email
    pass


def should_extend_again(tracking_record):
    """Check if user has requested extension for round 2"""
    return tracking_record.get("status") == "EXTENDED" and tracking_record.get("extensionCount") == 1
```

---

## 📌 COMPONENT 2: Manager Reply Webhook

```python
# process_manager_reply.py
import azure.functions as func
import json
import re
from datetime import datetime, timedelta
from azure.data.tables import TableClient
import logging

logger = logging.getLogger(__name__)

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook to process manager replies for EF extensions
    Triggered when email arrives at ef-extend-{userId}@company.com
    """
    
    try:
        # Parse incoming email via Graph API webhook or SMTP capture
        body = req.get_json()
        
        # Extract email metadata
        reply_to = body.get("from", {}).get("emailAddress", {}).get("address")
        reply_subject = body.get("subject", "")
        reply_body = body.get("bodyPreview", "")
        received_time = body.get("receivedDateTime")
        
        # Extract userId from "To" address
        # Example: ef-extend-{userId}@company.com
        to_address = body.get("toRecipients", [{}])[0].get("emailAddress", {}).get("address", "")
        user_id = extract_user_id_from_reply_to(to_address)
        
        if not user_id:
            logger.warning(f"Could not extract user_id from {to_address}")
            return func.HttpResponse("Invalid format", status_code=400)
        
        # Setup table storage
        table_client = TableClient.from_connection_string(
            conn_str=os.environ["AzureWebJobsStorage"],
            table_name="EFTracking"
        )
        
        # Get tracking record
        try:
            tracking = table_client.get_entity(partition_key="EF", row_key=user_id)
        except:
            logger.warning(f"Tracking record not found for user {user_id}")
            return func.HttpResponse("User not found", status_code=404)
        
        # Validate sender is the manager
        if reply_to.lower() != tracking.get("managerEmail", "").lower():
            logger.warning(f"Reply from unauthorized sender {reply_to}")
            return func.HttpResponse("Unauthorized", status_code=403)
        
        # Check if reply contains extension keyword
        if not contains_extension_keyword(reply_body):
            logger.info(f"Reply does not contain extension keyword")
            # Still update with NO_ACTION status
            log_reply(table_client, tracking, reply_to, reply_body, "NO_ACTION")
            return func.HttpResponse("No action taken", status_code=200)
        
        # Validate extension count (max 2)
        extension_count = tracking.get("extensionCount", 0)
        if extension_count >= 2:
            logger.info(f"Max extensions already used for {user_id}")
            log_reply(table_client, tracking, reply_to, reply_body, "MAX_REACHED")
            return func.HttpResponse("Max extensions reached", status_code=400)
        
        # Calculate new disable date
        offboard_date = datetime.fromisoformat(tracking["offboardDate"])
        days_extended = (extension_count + 1) * 30
        new_disable_date = offboard_date + timedelta(days=days_extended)
        
        # Validate not past 90-day hard limit
        if days_extended > 90:
            logger.warning(f"Extension would exceed 90-day limit for {user_id}")
            log_reply(table_client, tracking, reply_to, reply_body, "LIMIT_EXCEEDED")
            return func.HttpResponse("Would exceed 90-day limit", status_code=400)
        
        # Update tracking record
        tracking["extensionCount"] = extension_count + 1
        tracking["currentDisableDate"] = new_disable_date.isoformat()
        tracking["status"] = "EXTENDED"
        tracking["updatedAt"] = datetime.utcnow().isoformat()
        
        table_client.upsert_entity(tracking)
        
        # Log the reply
        log_reply(table_client, tracking, reply_to, reply_body, "EXTENDED")
        
        logger.info(f"Extension processed for user {user_id}. New disable date: {new_disable_date}")
        
        return func.HttpResponse(
            json.dumps({
                "status": "extended",
                "new_disable_date": new_disable_date.isoformat(),
                "extension_count": tracking["extensionCount"]
            }),
            status_code=200
        )
        
    except Exception as e:
        logger.error(f"Error processing reply: {str(e)}")
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)


def extract_user_id_from_reply_to(to_address):
    """Extract user ID from ef-extend-{userId}@company.com format"""
    match = re.search(r'ef-extend-([a-f0-9\-]+)@', to_address, re.IGNORECASE)
    return match.group(1) if match else None


def contains_extension_keyword(text):
    """Check if reply contains extension keyword"""
    keywords = ["extend", "yes", "continue", "approved", "ok", "okay", "accept"]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)


def log_reply(table_client, tracking, reply_from, reply_body, action):
    """Log manager reply to audit trail"""
    # TODO: Create entry in EFAlerts table
    logger.info(f"Logged reply: {action} from {reply_from}")
```

---

## 📌 COMPONENT 3: Email Alert Template

```html
<!-- alert_template.html -->
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Segoe UI, Arial; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #0078d4; color: white; padding: 20px; border-radius: 8px 8px 0 0; }
        .content { background: #f3f3f3; padding: 20px; border-radius: 0 0 8px 8px; }
        .alert-box { background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }
        .key-date { font-size: 18px; font-weight: bold; color: #d9534f; }
        .action-box { background: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .footer { font-size: 12px; color: #666; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px; }
        table { width: 100%; }
        td { padding: 10px 0; }
        td:first-child { font-weight: bold; color: #0078d4; width: 150px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>Email Forwarding Expiration Notice</h2>
            <p style="margin: 0;">Action Required</p>
        </div>
        
        <div class="content">
            <p>Dear {{MANAGER_NAME}},</p>
            
            <p>This is to inform you that the email forwarding for the following terminated employee will <strong>expire automatically on {{DISABLE_DATE}}</strong>:</p>
            
            <table>
                <tr><td>Employee Name:</td><td>{{EMPLOYEE_NAME}}</td></tr>
                <tr><td>Email Address:</td><td>{{EMPLOYEE_EMAIL}}</td></tr>
                <tr><td>Offboarding Date:</td><td>{{OFFBOARD_DATE}}</td></tr>
                <tr><td>Forwarding Expires:</td><td class="key-date">{{DISABLE_DATE}}</td></tr>
                <tr><td>Days Remaining:</td><td>{{DAYS_REMAINING}} days</td></tr>
            </table>
            
            <div class="alert-box">
                ⚠️ <strong>Important:</strong> If no action is taken, email forwarding will be <strong>automatically disabled</strong> on {{DISABLE_DATE}}, and all incoming emails will be rejected.
            </div>
            
            <div class="action-box">
                <h3>✓ To Extend Email Forwarding:</h3>
                <p>Reply to this email with <strong>"EXTEND"</strong> or <strong>"YES"</strong> before {{DISABLE_DATE}}.</p>
                <p><strong>Maximum Extensions:</strong> {{EXTENSION_STATUS}} ({{EXTENSION_COUNT}}/2 used)</p>
                <p><strong>Hard Limit:</strong> Email forwarding will not be available beyond 90 days from offboarding date.</p>
            </div>
            
            <p><strong>Questions?</strong> Contact IT Operations at {{IT_EMAIL}}</p>
            
            <div class="footer">
                <p>This is an automated message. Please do not reply with sensitive information.</p>
                <p>© {{YEAR}} Netradyne IT Operations</p>
            </div>
        </div>
    </div>
</body>
</html>
```

---

## 📌 COMPONENT 4: SQL Schema Setup

```sql
-- Create EFTracking table
CREATE TABLE [dbo].[EFTracking] (
    [id] [uniqueidentifier] NOT NULL DEFAULT NEWID() PRIMARY KEY,
    [userId] [nvarchar](255) NOT NULL,
    [userEmail] [nvarchar](255) NOT NULL,
    [userDisplayName] [nvarchar](255),
    [managerId] [nvarchar](255),
    [managerEmail] [nvarchar](255),
    [managerDisplayName] [nvarchar](255),
    [offboardDate] [datetime2] NOT NULL,
    [initialDisableDate] [datetime2] NOT NULL,
    [currentDisableDate] [datetime2] NOT NULL,
    [extensionCount] [int] DEFAULT 0,
    [status] [nvarchar](50) NOT NULL DEFAULT 'ACTIVE',
    [lastAlertDate] [datetime2],
    [lastExtensionDate] [datetime2],
    [createdAt] [datetime2] DEFAULT GETDATE(),
    [updatedAt] [datetime2] DEFAULT GETDATE(),
    [notes] [nvarchar](max)
);

-- Create EFAlerts table
CREATE TABLE [dbo].[EFAlerts] (
    [id] [uniqueidentifier] NOT NULL DEFAULT NEWID() PRIMARY KEY,
    [trackingId] [uniqueidentifier] NOT NULL FOREIGN KEY REFERENCES [EFTracking]([id]),
    [alertDate] [datetime2] NOT NULL,
    [alertType] [nvarchar](50) NOT NULL,
    [sentTo] [nvarchar](255) NOT NULL,
    [ccTo] [nvarchar](255),
    [status] [nvarchar](50) NOT NULL,
    [replyDate] [datetime2],
    [repliedBy] [nvarchar](255),
    [replyAction] [nvarchar](50),
    [replyContent] [nvarchar](max),
    [createdAt] [datetime2] DEFAULT GETDATE()
);

-- Create indexes
CREATE INDEX idx_status ON [EFTracking]([status]);
CREATE INDEX idx_offboardDate ON [EFTracking]([offboardDate]);
CREATE INDEX idx_currentDisableDate ON [EFTracking]([currentDisableDate]);
```

---

## 🧪 LOCAL TESTING (Using Azure Functions Core Tools)

```bash
# Install Azure Functions Core Tools
brew tap azure/tap
brew install azure-functions-core-tools@4

# Create local.settings.json for local testing
cat > local.settings.json << 'EOF'
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
    "ManagedIdentityClientId": "your-client-id"
  }
}
EOF

# Run function locally
func start

# Test the monitor function
curl http://localhost:7071/api/monitor_ef_expiration

# Test the webhook
curl -X POST http://localhost:7071/api/process_manager_reply \
  -H "Content-Type: application/json" \
  -d @test_reply.json
```

---

