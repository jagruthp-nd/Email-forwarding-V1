"""
monitor_accounts.py
-------------------
Daily monitoring logic – runs via the Azure Functions timer trigger at 9 AM UTC.

Decision matrix (days elapsed from offboard date):

  EF Required = NO
  ┌─────────┬──────────────────────────────────────────┐
  │ Day ≥30 │ DELETE account (reason: NO_EF)           │
  └─────────┴──────────────────────────────────────────┘

  EF Required = YES
  ┌────────────────────┬──────────────────────────────────────────────────┐
  │ Day 25–29          │ ALERT if not already alerted (extension 0)       │
  │ Day ≥30, ext=0     │ DELETE (reason: NO_EXTENSION_DAY30)              │
  │ Day 55–59, ext=1   │ ALERT if not already alerted (before Day 60)     │
  │ Day ≥60, ext=1     │ DELETE (reason: NO_EXTENSION_DAY60)              │
  │ Day 85–89, ext=2   │ ALERT if not already alerted (FINAL, before D90) │
  │ Day ≥90            │ DELETE (reason: MAX_POLICY_DAY90)                │
  └────────────────────┴──────────────────────────────────────────────────┘

Alert windows (25–29, 55–59, 85–89) catch up on missed runs:
  If the daily function was down on Day 25, the alert fires on Day 26, 27 …
  as long as the deletion hasn't happened yet.

Idempotency:
  Each user record carries a `lastAlertDate` field.  The monitor will not
  send a second alert for the same period even if re-run within the window.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from .table_store  import TableStore
from .graph_api    import (
    get_terminated_users,
    extract_offboard_date,
    has_email_forwarding,
    delete_user,
    get_manager,
)
from .email_sender import (
    send_ef_alert,
    send_deletion_notice,
    send_final_deletion_notice,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alert / delete thresholds (in days from offboard date)
# ---------------------------------------------------------------------------
_ALERT_WINDOW_1  = (25, 29)   # alert before Day-30 delete
_DELETE_1        = 30
_ALERT_WINDOW_2  = (55, 59)   # alert before Day-60 delete
_DELETE_2        = 60
_ALERT_WINDOW_3  = (85, 89)   # final alert before Day-90 delete
_DELETE_3        = 90


# ---------------------------------------------------------------------------
# Entry point (called by function_app.py timer trigger)
# ---------------------------------------------------------------------------

def run_monitor() -> Dict[str, int]:
    """
    Main entry point for the daily monitoring run.

    Returns a summary dict with counts of each action taken, which the
    timer function logs for visibility.
    """
    store = TableStore()
    store.ensure_tables()

    today = datetime.now(timezone.utc).date()
    logger.info("=== EF Monitor starting – %s ===", today.isoformat())

    # Fetch all terminated+disabled accounts from Azure AD
    ad_users = get_terminated_users()

    # Also fetch currently monitored users from Table Storage so we can
    # skip users whose accounts were already deleted (statusCode=DELETED)
    # and carry forward their existing records.
    tracked = {r["userId"]: r for r in store.list_active_users()}

    summary = {"checked": 0, "alerted": 0, "deleted": 0, "errors": 0, "skipped": 0}

    for user in ad_users:
        user_id = user.get("id", "")
        if not user_id:
            continue

        try:
            summary["checked"] += 1
            action = _process_user(user, today, store, tracked.get(user_id))
            if action == "alerted":
                summary["alerted"] += 1
            elif action == "deleted":
                summary["deleted"] += 1
            elif action == "skipped":
                summary["skipped"] += 1
        except Exception as exc:
            summary["errors"] += 1
            logger.error("Unhandled error for userId=%s: %s", user_id, exc, exc_info=True)

    logger.info(
        "=== EF Monitor complete – checked=%d alerted=%d deleted=%d errors=%d skipped=%d ===",
        summary["checked"], summary["alerted"], summary["deleted"],
        summary["errors"],  summary["skipped"],
    )
    return summary


# ---------------------------------------------------------------------------
# Per-user processing
# ---------------------------------------------------------------------------

def _process_user(
    user: Dict[str, Any],
    today: date,
    store: TableStore,
    existing_record: Optional[Dict[str, Any]],
) -> str:
    """
    Evaluate and act on one terminated user.

    Returns one of: 'alerted', 'deleted', 'skipped', 'no_action'.
    """
    user_id = user["id"]

    # ── 1. Parse offboard date ──────────────────────────────────────────────
    raw_date = extract_offboard_date(user)
    if not raw_date:
        logger.debug("userId=%s has no extensionAttribute10 – skipping", user_id)
        return "skipped"

    try:
        # Normalise the 'Z' suffix (UTC) so Python 3.8 fromisoformat() accepts it.
        # Python 3.11+ accepts Z natively; earlier versions require '+00:00'.
        normalised = raw_date.replace("Z", "+00:00")
        offboard_dt = datetime.fromisoformat(normalised)
        offboard_date = offboard_dt.date()
    except ValueError:
        logger.warning("userId=%s invalid extensionAttribute10 value: %s", user_id, raw_date)
        return "skipped"

    days_elapsed = (today - offboard_date).days
    if days_elapsed < 0:
        logger.debug("userId=%s offboard date is in the future (%s) – skipping", user_id, offboard_date)
        return "skipped"

    # ── 2. Get or create tracking record ───────────────────────────────────
    record = existing_record or _create_record(user, offboard_date, store)
    if record is None:
        return "skipped"

    # ── 3. Skip already-deleted ─────────────────────────────────────────────
    if record.get("statusCode") == "DELETED":
        return "skipped"

    ef_required  = _bool(record.get("efRequired", False))
    ext_count    = int(record.get("extensionCount", 0))
    status       = record.get("statusCode", "ACTIVE")
    last_alert   = record.get("lastAlertDate", "")

    logger.debug(
        "userId=%s days=%d ef=%s ext=%d status=%s",
        user_id, days_elapsed, ef_required, ext_count, status,
    )

    # ── 4. NO EF PATH ───────────────────────────────────────────────────────
    if not ef_required:
        if days_elapsed >= _DELETE_1:
            return _do_delete(user_id, record, "NO_EF", store)
        return "no_action"

    # ── 5. HAS EF – alert / delete decision ────────────────────────────────

    # ---- 5a. WINDOW 1: Day 25–29, extension 0 → first alert ---------------
    if _ALERT_WINDOW_1[0] <= days_elapsed <= _ALERT_WINDOW_1[1]:
        if ext_count == 0 and not _already_alerted(last_alert, offboard_date, 25):
            return _do_alert(record, store, days_remaining=_DELETE_1 - days_elapsed, is_final=False)
        return "no_action"

    # ---- 5b. Day ≥ 30, no extension → delete ------------------------------
    if days_elapsed >= _DELETE_1 and ext_count == 0:
        return _do_delete(user_id, record, "NO_EXTENSION_DAY30", store)

    # ---- 5c. WINDOW 2: Day 55–59, extension 1 → second alert --------------
    if _ALERT_WINDOW_2[0] <= days_elapsed <= _ALERT_WINDOW_2[1]:
        if ext_count == 1 and not _already_alerted(last_alert, offboard_date, 55):
            return _do_alert(record, store, days_remaining=_DELETE_2 - days_elapsed, is_final=False)
        return "no_action"

    # ---- 5d. Day ≥ 60, only 1 extension used → delete ---------------------
    if days_elapsed >= _DELETE_2 and ext_count == 1:
        return _do_delete(user_id, record, "NO_EXTENSION_DAY60", store)

    # ---- 5e. WINDOW 3: Day 85–89, extension 2 → final alert ---------------
    if _ALERT_WINDOW_3[0] <= days_elapsed <= _ALERT_WINDOW_3[1]:
        if ext_count == 2 and not _already_alerted(last_alert, offboard_date, 85):
            return _do_alert(record, store, days_remaining=_DELETE_3 - days_elapsed, is_final=True)
        return "no_action"

    # ---- 5f. Day ≥ 90 → final delete -------------------------------------
    if days_elapsed >= _DELETE_3:
        return _do_delete(user_id, record, "MAX_POLICY_DAY90", store, is_final=True)

    return "no_action"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _do_alert(
    record: Dict[str, Any],
    store: TableStore,
    days_remaining: int,
    is_final: bool,
) -> str:
    user_id = record["userId"]
    today_str = datetime.now(timezone.utc).date().isoformat()

    ok = send_ef_alert(record, days_remaining=max(days_remaining, 1), is_final=is_final)

    status = "ALERT_SENT"
    store.append_email_log(
        user_id=user_id,
        email_type="ALERT",
        recipient=record.get("managerEmail", ""),
        subject=f"EF Expiration Alert – {record.get('displayName', '')}",
        status="SENT" if ok else "FAILED",
    )

    record["statusCode"]    = status
    record["lastAlertDate"] = today_str
    store.upsert_user(record)

    action_label = "FINAL_ALERT" if is_final else "ALERTED"
    store.append_audit(user_id, action_label, f"Alert sent. days_remaining={days_remaining}")
    logger.info("Alert sent for userId=%s (days_remaining=%d final=%s)", user_id, days_remaining, is_final)
    return "alerted"


def _do_delete(
    user_id: str,
    record: Dict[str, Any],
    reason: str,
    store: TableStore,
    is_final: bool = False,
) -> str:
    today_str = datetime.now(timezone.utc).date().isoformat()

    # Perform the Azure AD soft-delete
    ok = delete_user(user_id)
    if not ok:
        store.append_audit(user_id, "DELETE_FAILED", f"reason={reason} – Graph API delete call failed")
        logger.error("Delete failed for userId=%s reason=%s", user_id, reason)
        return "errors"

    # Send appropriate notification email
    if is_final or reason == "MAX_POLICY_DAY90":
        send_final_deletion_notice(record)
        email_type = "FINAL_DELETION"
    else:
        send_deletion_notice(record, reason=reason)
        email_type = "DELETION_NOTICE"

    store.append_email_log(
        user_id=user_id,
        email_type=email_type,
        recipient=record.get("managerEmail", ""),
        subject=f"Account Deleted – {record.get('displayName', '')}",
        status="SENT",
    )

    # Update tracking record
    record["statusCode"]  = "DELETED"
    record["deletedDate"] = today_str
    store.upsert_user(record)

    store.append_audit(user_id, "DELETED", f"reason={reason}")
    logger.info("Deleted userId=%s reason=%s", user_id, reason)
    return "deleted"


# ---------------------------------------------------------------------------
# Record initialisation
# ---------------------------------------------------------------------------

def _create_record(
    user: Dict[str, Any],
    offboard_date: date,
    store: TableStore,
) -> Optional[Dict[str, Any]]:
    """
    Build and persist a new UserTracking record for a user seen for the first time.
    """
    user_id    = user["id"]
    user_email = user.get("mail") or user.get("userPrincipalName", "")

    # Resolve manager – may already be in the $expand response
    manager_obj = user.get("manager") or {}
    if not manager_obj.get("mail"):
        # Fallback: dedicated manager call
        manager_obj = get_manager(user_id) or {}

    manager_email = manager_obj.get("mail", "")
    manager_id    = manager_obj.get("id", "")

    if not manager_email:
        logger.warning("userId=%s has no manager email – will be tracked but alerts may not send", user_id)

    # Check email forwarding (live Graph API call)
    ef_required = has_email_forwarding(user_id)

    delete_date = (offboard_date + timedelta(days=30)).isoformat()

    record: Dict[str, Any] = {
        "userId":          user_id,
        "userEmail":       user_email,
        "displayName":     user.get("displayName", ""),
        "managerId":       manager_id,
        "managerEmail":    manager_email,
        "offboardDate":    offboard_date.isoformat(),
        "efRequired":      ef_required,
        "statusCode":      "ACTIVE",
        "extensionCount":  0,
        "deleteDate":      delete_date,
        "deletedDate":     "",
        "lastAlertDate":   "",
    }

    store.upsert_user(record)
    store.append_audit(
        user_id,
        "REGISTERED",
        f"First seen. ef={ef_required} offboard={offboard_date} deleteDate={delete_date}",
    )
    logger.info(
        "Registered new user userId=%s ef=%s offboard=%s", user_id, ef_required, offboard_date
    )
    return record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bool(value: Any) -> bool:
    """Coerce various truthy representations from Table Storage to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _already_alerted(last_alert_date: str, offboard_date: date, expected_day: int) -> bool:
    """
    Return True if an alert was already sent during the current alert window.

    We consider an alert 'already sent' if lastAlertDate falls within
    5 days before the expected deletion day (i.e., the same window).
    """
    if not last_alert_date:
        return False
    try:
        alerted = date.fromisoformat(last_alert_date)
        window_start = offboard_date + timedelta(days=expected_day)
        window_end   = offboard_date + timedelta(days=expected_day + 4)
        return window_start <= alerted <= window_end
    except ValueError:
        return False
