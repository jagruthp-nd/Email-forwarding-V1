"""
function_app.py
---------------
Azure Functions v2 Python programming model entry point.

Registers two triggers:
  1. monitor_accounts  – Timer trigger, daily at 09:00 UTC
  2. reply_webhook     – HTTP trigger (POST), receives manager extension replies
"""

import json
import logging

import azure.functions as func

from utils.monitor_accounts import run_monitor
from utils.reply_webhook    import process_reply

logger = logging.getLogger(__name__)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# ---------------------------------------------------------------------------
# Trigger 1: Daily account monitoring (Timer)
# ---------------------------------------------------------------------------
# NCRONTAB format: {second} {minute} {hour} {day} {month} {weekday}
# "0 0 9 * * *"  →  every day at 09:00:00 UTC
# ---------------------------------------------------------------------------

@app.timer_trigger(
    arg_name="timer",
    schedule="0 0 9 * * *",
    run_on_startup=False,    # set True temporarily during local testing
    use_monitor=True,        # Azure Functions will track missed runs
)
def monitor_accounts(timer: func.TimerRequest) -> None:
    """
    Daily job: scan Azure AD for terminated accounts, send EF alerts,
    and delete accounts on schedule.
    """
    if timer.past_due:
        logger.warning("Timer trigger is past due – running catch-up")

    logger.info("monitor_accounts trigger fired")

    try:
        summary = run_monitor()
        logger.info("monitor_accounts completed: %s", json.dumps(summary))
    except Exception as exc:
        logger.critical("monitor_accounts failed with unhandled exception: %s", exc, exc_info=True)
        raise   # re-raise so Azure Functions marks the invocation as failed


# ---------------------------------------------------------------------------
# Trigger 2: Manager email reply webhook (HTTP POST)
# ---------------------------------------------------------------------------
# URL: https://<func-app>.azurewebsites.net/api/reply?code=<function-key>
#
# Power Automate flow setup:
#   • Trigger: "When a new email arrives" on it-automation-service@netradyne.com
#   • Filter:  Subject contains "Email Forwarding Expiration"
#   • Action:  HTTP POST to this URL with JSON body:
#       {
#         "from_email":  "@{triggerOutputs()?['body/from/emailAddress/address']}",
#         "subject":     "@{triggerOutputs()?['body/subject']}",
#         "body":        "@{triggerOutputs()?['body/bodyPreview']}",
#         "user_email":  ""   // optional – leave empty unless you can parse it
#       }
# ---------------------------------------------------------------------------

@app.route(route="reply", methods=["POST"])
def reply_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Process a manager's 'EXTEND' reply and grant a 30-day EF extension.
    """
    logger.info("reply_webhook called from %s", req.headers.get("X-Forwarded-For", "unknown"))
    return process_reply(req)
