"""
reply_webhook.py
----------------
HTTP-triggered Azure Function that processes manager email replies.

How replies reach this webhook
-------------------------------
Recommended: Power Automate flow on the it-automation-service@netradyne.com
mailbox.  When a reply arrives whose subject starts with "Re: Email Forwarding",
Power Automate POSTs a JSON payload to this function's URL.

Required Power Automate payload shape (you define this in the PA flow):
{
    "from_email": "<sender email address>",
    "subject":    "<full email subject>",
    "body":       "<plain-text body preview>",
    "user_email": "<optional: ex-employee email for direct lookup>"
}

Security
--------
The webhook URL is secret by default (Azure Functions key-based auth).
Optionally configure WEBHOOK_TOKEN in app settings; if set, the caller
must supply it as the X-Webhook-Token header.

Extension rules
---------------
- Manager must be the registered manager for the user
- Reply body must contain one of the EXTEND_KEYWORDS
- extensionCount must be < 2  (maximum 2 extensions allowed)
- deleteDate is recalculated: offboardDate + (extensionCount+1)*30 days
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import azure.functions as func

from .table_store  import TableStore
from .email_sender import send_extension_confirm

logger = logging.getLogger(__name__)

_EXTEND_KEYWORDS = {"extend", "yes", "continue", "approve", "approved", "ok", "okay"}
_MAX_EXTENSIONS  = 2


# ---------------------------------------------------------------------------
# Entry point (called by function_app.py HTTP trigger)
# ---------------------------------------------------------------------------

def process_reply(req: func.HttpRequest) -> func.HttpResponse:
    """
    Validate an incoming manager reply and grant a 30-day EF extension.

    Returns HTTP 200 on success, 4xx on validation failure, 500 on error.
    """
    # ── 1. Token auth check ─────────────────────────────────────────────────
    expected_token = os.environ.get("WEBHOOK_TOKEN", "")
    if expected_token:
        incoming_token = req.headers.get("X-Webhook-Token", "")
        if incoming_token != expected_token:
            logger.warning("Webhook called with invalid token")
            return _resp(403, "Forbidden")

    # ── 2. Parse request body ───────────────────────────────────────────────
    try:
        payload: Dict[str, Any] = req.get_json()
    except ValueError:
        return _resp(400, "Request body must be valid JSON.")

    from_email = (payload.get("from_email") or "").strip().lower()
    subject    = payload.get("subject", "")
    body       = payload.get("body", "")
    user_email_hint = (payload.get("user_email") or "").strip().lower()

    if not from_email:
        return _resp(400, "Missing 'from_email' in payload.")

    if not _body_contains_extend_keyword(body):
        logger.info("Reply from %s does not contain an EXTEND keyword – no action", from_email)
        return _resp(200, "No action taken: extension keyword not found in reply.")

    # ── 3. Look up tracking record ──────────────────────────────────────────
    store  = TableStore()
    record = _find_record(store, from_email, user_email_hint)

    if record is None:
        logger.warning(
            "No active tracking record found for manager=%s user_hint=%s",
            from_email, user_email_hint,
        )
        return _resp(404, "No active EF tracking record found for this manager.")

    # ── 4. Validate manager email ───────────────────────────────────────────
    registered_manager = (record.get("managerEmail") or "").strip().lower()
    if from_email != registered_manager:
        logger.warning(
            "Reply sender %s does not match registered manager %s for userId=%s",
            from_email, registered_manager, record["userId"],
        )
        return _resp(403, "Sender is not the registered manager for this account.")

    # ── 5. Validate extension count ─────────────────────────────────────────
    ext_count = int(record.get("extensionCount", 0))
    status    = record.get("statusCode", "")

    if status == "DELETED":
        return _resp(409, "Account has already been deleted. Extensions are not possible.")

    if ext_count >= _MAX_EXTENSIONS:
        logger.info(
            "userId=%s already at max extensions (%d) – rejecting", record["userId"], ext_count
        )
        return _resp(409, f"Maximum extensions ({_MAX_EXTENSIONS}) already used for this account.")

    # ── 6. Grant extension ──────────────────────────────────────────────────
    user_id       = record["userId"]
    offboard_str  = record.get("offboardDate", "")
    new_ext_count = ext_count + 1

    # Recalculate delete date from offboard date (not from today)
    # so extensions are always anchored to Day 0.
    try:
        offboard_date = datetime.fromisoformat(offboard_str).date()
    except (ValueError, TypeError):
        logger.error("userId=%s has invalid offboardDate: %s", user_id, offboard_str)
        return _resp(500, "Internal error: invalid offboard date stored for this user.")

    new_delete_date = offboard_date + timedelta(days=new_ext_count * 30)

    # Update record
    record["extensionCount"] = new_ext_count
    record["deleteDate"]     = new_delete_date.isoformat()
    record["statusCode"]     = "EXTENDED" if new_ext_count < _MAX_EXTENSIONS else "EXTENDED_MAX"
    record["lastAlertDate"]  = ""    # reset so next alert window fires

    store.upsert_user(record)
    store.append_audit(
        user_id,
        "EXTENDED",
        f"Extension {new_ext_count}/{_MAX_EXTENSIONS} granted by {from_email}. "
        f"New deleteDate={new_delete_date.isoformat()}",
    )
    store.append_email_log(
        user_id=user_id,
        email_type="EXTENSION_CONFIRM",
        recipient=registered_manager,
        subject=f"EF Extended – {record.get('displayName', '')}",
        status="PENDING",  # updated after send below
    )

    # Send confirmation email
    send_extension_confirm(record)

    logger.info(
        "Extension %d/%d granted for userId=%s by %s – new deleteDate=%s",
        new_ext_count, _MAX_EXTENSIONS, user_id, from_email, new_delete_date.isoformat(),
    )

    return _resp(200, {
        "status":           "extension_granted",
        "extension_number": new_ext_count,
        "max_extensions":   _MAX_EXTENSIONS,
        "new_delete_date":  new_delete_date.isoformat(),
        "user_id":          user_id,
        "display_name":     record.get("displayName", ""),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _body_contains_extend_keyword(body: str) -> bool:
    """Return True if the email body contains any recognised extension keyword.

    Strips punctuation from each word so replies like 'Yes, please extend.'
    are recognised correctly.
    """
    import string
    words = {w.strip(string.punctuation).lower() for w in body.split()}
    return bool(_EXTEND_KEYWORDS.intersection(words))


def _find_record(
    store: TableStore,
    manager_email: str,
    user_email_hint: str,
) -> Optional[Dict[str, Any]]:
    """
    Find the most-recently-updated active UserTracking record for this manager.

    Strategy:
      1. If user_email_hint is provided, find the record whose userEmail matches it.
      2. Otherwise, scan active users and find one(s) managed by manager_email.
         If multiple are found, return the one whose deleteDate is soonest
         (most urgent), so extensions are applied to the right user.
    """
    active_users = store.list_active_users()

    # Strategy 1: direct match by user email (most reliable)
    if user_email_hint:
        for rec in active_users:
            if rec.get("userEmail", "").lower() == user_email_hint:
                if rec.get("managerEmail", "").lower() == manager_email:
                    return rec

    # Strategy 2: match by manager email, pick soonest delete date
    candidates = [
        r for r in active_users
        if r.get("managerEmail", "").lower() == manager_email
        and r.get("statusCode") not in ("DELETED",)
    ]

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Multiple managed users pending – return the one with the earliest deleteDate
    def _delete_key(r: Dict) -> str:
        return r.get("deleteDate") or "9999-12-31"

    candidates.sort(key=_delete_key)
    logger.info(
        "Multiple active records for manager %s – returning soonest deleteDate: %s",
        manager_email, candidates[0].get("deleteDate"),
    )
    return candidates[0]


def _resp(status: int, body: Any) -> func.HttpResponse:
    """Build a JSON HTTP response."""
    if isinstance(body, str):
        payload = json.dumps({"message": body})
    else:
        payload = json.dumps(body)
    return func.HttpResponse(
        body=payload,
        status_code=status,
        mimetype="application/json",
    )
