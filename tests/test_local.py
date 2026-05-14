"""
test_local.py
-------------
Local integration test harness for the EF automation project.

Run these tests BEFORE deploying to production:

  cd Email-forwarding
  python -m pytest tests/test_local.py -v

These tests do NOT call Azure AD or send real emails.
They verify the business logic in isolation using mocked dependencies.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

def make_record(
    user_id: str = "user-001",
    offboard_days_ago: int = 0,
    ef_required: bool = True,
    extension_count: int = 0,
    status: str = "ACTIVE",
    last_alert: str = "",
) -> Dict[str, Any]:
    """Return a synthetic UserTracking dict."""
    today = date.today()
    offboard = today - timedelta(days=offboard_days_ago)
    delete_date = offboard + timedelta(days=(extension_count + 1) * 30)
    return {
        "userId":         user_id,
        "userEmail":      f"{user_id}@netradyne.com",
        "displayName":    "Test User",
        "managerId":      "mgr-001",
        "managerEmail":   "manager@netradyne.com",
        "offboardDate":   offboard.isoformat(),
        "efRequired":     ef_required,
        "statusCode":     status,
        "extensionCount": extension_count,
        "deleteDate":     delete_date.isoformat(),
        "deletedDate":    "",
        "lastAlertDate":  last_alert,
    }


def make_ad_user(offboard_days_ago: int = 0) -> Dict[str, Any]:
    """Return a minimal Azure AD user dict."""
    today = date.today()
    offboard = today - timedelta(days=offboard_days_ago)
    return {
        "id":          "user-001",
        "mail":        "exstaff@netradyne.com",
        "displayName": "Ex Staff",
        "onPremisesExtensionAttributes": {
            "extensionAttribute10": offboard.isoformat() + "T00:00:00Z"
        },
        "manager": {
            "id":    "mgr-001",
            "mail":  "manager@netradyne.com",
            "displayName": "Some Manager",
        },
    }


# ---------------------------------------------------------------------------
# Tests: monitor_accounts decision logic
# ---------------------------------------------------------------------------

class TestMonitorDecisionLogic:
    """
    Verify the _process_user routing without touching Azure or email.
    """

    def _run(self, ad_user, today, store, existing_record=None):
        from utils.monitor_accounts import _process_user
        return _process_user(ad_user, today, store, existing_record)

    # ── No EF ────────────────────────────────────────────────────────────

    def test_no_ef_before_day30_no_action(self):
        store = MagicMock()
        record = make_record(offboard_days_ago=10, ef_required=False)
        today = date.today()
        with patch("utils.monitor_accounts.delete_user") as mock_del:
            ad = make_ad_user(10)
            result = self._run(ad, today, store, record)
        assert result == "no_action"
        mock_del.assert_not_called()

    def test_no_ef_exactly_day30_deletes(self):
        store = MagicMock()
        record = make_record(offboard_days_ago=30, ef_required=False)
        today = date.today()
        with patch("utils.monitor_accounts.delete_user", return_value=True) as mock_del, \
             patch("utils.monitor_accounts.send_deletion_notice"):
            ad = make_ad_user(30)
            result = self._run(ad, today, store, record)
        assert result == "deleted"
        mock_del.assert_called_once_with(record["userId"])

    def test_no_ef_past_day30_still_deletes(self):
        """Catch-up: if function missed Day 30, delete on Day 35."""
        store = MagicMock()
        record = make_record(offboard_days_ago=35, ef_required=False)
        today = date.today()
        with patch("utils.monitor_accounts.delete_user", return_value=True), \
             patch("utils.monitor_accounts.send_deletion_notice"):
            ad = make_ad_user(35)
            result = self._run(ad, today, store, record)
        assert result == "deleted"

    # ── Has EF – alert path ───────────────────────────────────────────────

    def test_ef_day25_sends_alert(self):
        store = MagicMock()
        record = make_record(offboard_days_ago=25, ef_required=True, extension_count=0)
        today = date.today()
        with patch("utils.monitor_accounts.send_ef_alert", return_value=True) as mock_alert:
            ad = make_ad_user(25)
            result = self._run(ad, today, store, record)
        assert result == "alerted"
        mock_alert.assert_called_once()

    def test_ef_day25_alert_not_sent_twice(self):
        """If alert already sent today, do not re-send."""
        today_str = date.today().isoformat()
        offboard = date.today() - timedelta(days=25)
        store = MagicMock()
        record = make_record(
            offboard_days_ago=25, ef_required=True, extension_count=0,
            last_alert=today_str,
        )
        with patch("utils.monitor_accounts.send_ef_alert") as mock_alert:
            ad = make_ad_user(25)
            result = self._run(ad, date.today(), store, record)
        assert result == "no_action"
        mock_alert.assert_not_called()

    def test_ef_day30_no_extension_deletes(self):
        store = MagicMock()
        record = make_record(offboard_days_ago=30, ef_required=True, extension_count=0)
        today = date.today()
        with patch("utils.monitor_accounts.delete_user", return_value=True) as mock_del, \
             patch("utils.monitor_accounts.send_deletion_notice"):
            ad = make_ad_user(30)
            result = self._run(ad, today, store, record)
        assert result == "deleted"
        mock_del.assert_called_once()

    def test_ef_day30_with_extension1_no_delete(self):
        """Day 30 but extension already granted: do NOT delete."""
        store = MagicMock()
        record = make_record(offboard_days_ago=30, ef_required=True, extension_count=1, status="EXTENDED")
        today = date.today()
        with patch("utils.monitor_accounts.delete_user") as mock_del:
            ad = make_ad_user(30)
            result = self._run(ad, today, store, record)
        assert result == "no_action"
        mock_del.assert_not_called()

    def test_ef_day55_with_ext1_sends_alert(self):
        store = MagicMock()
        record = make_record(offboard_days_ago=55, ef_required=True, extension_count=1, status="EXTENDED")
        today = date.today()
        with patch("utils.monitor_accounts.send_ef_alert", return_value=True):
            ad = make_ad_user(55)
            result = self._run(ad, today, store, record)
        assert result == "alerted"

    def test_ef_day60_with_ext1_no_second_extension_deletes(self):
        store = MagicMock()
        record = make_record(offboard_days_ago=60, ef_required=True, extension_count=1, status="EXTENDED")
        today = date.today()
        with patch("utils.monitor_accounts.delete_user", return_value=True) as mock_del, \
             patch("utils.monitor_accounts.send_deletion_notice"):
            ad = make_ad_user(60)
            result = self._run(ad, today, store, record)
        assert result == "deleted"
        mock_del.assert_called_once()

    def test_ef_day60_with_ext2_no_delete(self):
        """Both extensions used – should not delete until Day 90."""
        store = MagicMock()
        record = make_record(offboard_days_ago=60, ef_required=True, extension_count=2, status="EXTENDED_MAX")
        today = date.today()
        with patch("utils.monitor_accounts.delete_user") as mock_del:
            ad = make_ad_user(60)
            result = self._run(ad, today, store, record)
        assert result == "no_action"
        mock_del.assert_not_called()

    def test_ef_day90_final_delete(self):
        store = MagicMock()
        record = make_record(offboard_days_ago=90, ef_required=True, extension_count=2, status="EXTENDED_MAX")
        today = date.today()
        with patch("utils.monitor_accounts.delete_user", return_value=True) as mock_del, \
             patch("utils.monitor_accounts.send_final_deletion_notice"):
            ad = make_ad_user(90)
            result = self._run(ad, today, store, record)
        assert result == "deleted"
        mock_del.assert_called_once()

    def test_already_deleted_is_skipped(self):
        store = MagicMock()
        record = make_record(offboard_days_ago=90, ef_required=True, status="DELETED")
        today = date.today()
        with patch("utils.monitor_accounts.delete_user") as mock_del:
            ad = make_ad_user(90)
            result = self._run(ad, today, store, record)
        assert result == "skipped"
        mock_del.assert_not_called()

    def test_missing_extensionattribute10_skips(self):
        store = MagicMock()
        ad_user_no_date = {
            "id": "user-x",
            "mail": "x@netradyne.com",
            "displayName": "No Date",
            "onPremisesExtensionAttributes": {},
        }
        result = self._run(ad_user_no_date, date.today(), store, None)
        assert result == "skipped"


# ---------------------------------------------------------------------------
# Tests: reply_webhook extension processing
# ---------------------------------------------------------------------------

class TestReplyWebhook:

    def _call(self, payload: dict, headers: dict = None):
        import azure.functions as func
        from utils.reply_webhook import process_reply

        body_bytes = json.dumps(payload).encode()
        req = func.HttpRequest(
            method="POST",
            url="https://func.example.com/api/reply",
            body=body_bytes,
            headers=headers or {},
            params={},
        )
        return process_reply(req)

    def test_extend_keyword_not_present_returns_200_no_action(self):
        store_mock = MagicMock()
        store_mock.list_active_users.return_value = []
        with patch("utils.reply_webhook.TableStore", return_value=store_mock):
            resp = self._call({"from_email": "mgr@netradyne.com", "body": "Thanks for the heads up."})
        assert resp.status_code == 200
        assert "No action" in json.loads(resp.get_body())["message"]

    def test_extend_keyword_grants_extension(self):
        record = make_record(offboard_days_ago=25, ef_required=True, extension_count=0)
        store_mock = MagicMock()
        store_mock.list_active_users.return_value = [record]
        store_mock.get_user.return_value = record
        with patch("utils.reply_webhook.TableStore", return_value=store_mock), \
             patch("utils.reply_webhook.send_extension_confirm", return_value=True):
            resp = self._call({
                "from_email": "manager@netradyne.com",
                "body":       "Yes please EXTEND this",
                "user_email": "user-001@netradyne.com",
            })
        assert resp.status_code == 200
        data = json.loads(resp.get_body())
        assert data["extension_number"] == 1

    def test_max_extensions_returns_409(self):
        record = make_record(offboard_days_ago=60, ef_required=True, extension_count=2, status="EXTENDED_MAX")
        store_mock = MagicMock()
        store_mock.list_active_users.return_value = [record]
        with patch("utils.reply_webhook.TableStore", return_value=store_mock):
            resp = self._call({
                "from_email": "manager@netradyne.com",
                "body":       "EXTEND please",
                "user_email": "user-001@netradyne.com",
            })
        assert resp.status_code == 409

    def test_wrong_manager_returns_403(self):
        record = make_record(offboard_days_ago=25, ef_required=True, extension_count=0)
        store_mock = MagicMock()
        store_mock.list_active_users.return_value = [record]
        with patch("utils.reply_webhook.TableStore", return_value=store_mock):
            resp = self._call({
                "from_email": "attacker@example.com",
                "body":       "EXTEND please",
                "user_email": "user-001@netradyne.com",
            })
        assert resp.status_code in (403, 404)

    def test_webhook_token_check(self):
        with patch.dict(os.environ, {"WEBHOOK_TOKEN": "secret-token"}):
            resp = self._call(
                {"from_email": "m@netradyne.com", "body": "extend"},
                headers={"X-Webhook-Token": "wrong-token"},
            )
        assert resp.status_code == 403

    def test_deleted_account_returns_409(self):
        record = make_record(offboard_days_ago=31, ef_required=True, status="DELETED")
        store_mock = MagicMock()
        store_mock.list_active_users.return_value = [record]
        with patch("utils.reply_webhook.TableStore", return_value=store_mock):
            resp = self._call({
                "from_email": "manager@netradyne.com",
                "body":       "EXTEND",
                "user_email": "user-001@netradyne.com",
            })
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Tests: email body keyword detection
# ---------------------------------------------------------------------------

class TestExtendKeywords:
    def _check(self, text: str) -> bool:
        from utils.reply_webhook import _body_contains_extend_keyword
        return _body_contains_extend_keyword(text)

    def test_extend_keyword(self):
        assert self._check("Please EXTEND this forwarding") is True

    def test_yes_keyword(self):
        assert self._check("Yes, go ahead") is True

    def test_no_keyword(self):
        assert self._check("Thank you for the notification") is False

    def test_reject_keyword(self):
        assert self._check("No, you can disable it") is False

    def test_case_insensitive(self):
        assert self._check("APPROVED, please extend") is True
