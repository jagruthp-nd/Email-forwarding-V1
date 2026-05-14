"""
table_store.py
--------------
Azure Table Storage layer replacing SQL for EF automation tracking.

Tables:
  UserTracking  – one row per terminated user being monitored
  AuditLog      – append-only action log per user
  EmailLog      – record of every email sent

PartitionKey / RowKey design
  UserTracking : PartitionKey="EF", RowKey=userId (Azure AD object GUID)
  AuditLog     : PartitionKey=userId, RowKey="{YYYYMMDDHHmmssSSS}_{action}"
  EmailLog     : PartitionKey=userId, RowKey="{YYYYMMDDHHmmssSSS}_{emailType}"

This means a single-user lookup is O(1) (PartitionKey + RowKey) and a
daily full-scan of all monitored users is a single partition scan (fast at
the expected scale of a few hundred users).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableServiceClient, UpdateMode
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table names
# ---------------------------------------------------------------------------
_TRACKING_TABLE = "UserTracking"
_AUDIT_TABLE    = "AuditLog"
_EMAIL_TABLE    = "EmailLog"

# Shared PartitionKey for all UserTracking rows
_TRACKING_PK = "EF"


class TableStore:
    """Thin wrapper around the three Azure Table Storage tables."""

    def __init__(self) -> None:
        account_name = os.environ["STORAGE_ACCOUNT_NAME"]
        endpoint = f"https://{account_name}.table.core.windows.net"
        credential = DefaultAzureCredential()
        self._service: TableServiceClient = TableServiceClient(
            endpoint=endpoint, credential=credential
        )
        self._tracking = self._service.get_table_client(_TRACKING_TABLE)
        self._audit    = self._service.get_table_client(_AUDIT_TABLE)
        self._email    = self._service.get_table_client(_EMAIL_TABLE)

    # ------------------------------------------------------------------
    # Table initialisation (idempotent – safe to call on every cold start)
    # ------------------------------------------------------------------

    def ensure_tables(self) -> None:
        """Create tables if they do not exist.  Called once on function startup."""
        for name in [_TRACKING_TABLE, _AUDIT_TABLE, _EMAIL_TABLE]:
            try:
                self._service.create_table_if_not_exists(name)
                logger.debug("Table ready: %s", name)
            except Exception as exc:
                logger.warning("Could not ensure table %s: %s", name, exc)

    # ------------------------------------------------------------------
    # UserTracking operations
    # ------------------------------------------------------------------

    def upsert_user(self, record: Dict[str, Any]) -> None:
        """Insert or replace a UserTracking row.

        The caller must supply at minimum 'userId'.  PartitionKey / RowKey are
        added automatically so callers never need to know the key scheme.
        """
        entity = dict(record)
        entity["PartitionKey"] = _TRACKING_PK
        entity["RowKey"]       = record["userId"]
        self._tracking.upsert_entity(entity=entity, mode=UpdateMode.REPLACE)
        logger.debug("Upserted UserTracking for userId=%s", record["userId"])

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Return the UserTracking row for *user_id*, or None if absent."""
        try:
            return dict(
                self._tracking.get_entity(
                    partition_key=_TRACKING_PK, row_key=user_id
                )
            )
        except ResourceNotFoundError:
            return None
        except Exception as exc:
            logger.error("Error fetching user %s: %s", user_id, exc)
            return None

    def list_active_users(self) -> List[Dict[str, Any]]:
        """Return all UserTracking rows that are NOT in a terminal DELETED state.

        These are the users the daily monitor still needs to check.
        """
        try:
            return [
                dict(e)
                for e in self._tracking.query_entities(
                    query_filter="PartitionKey eq 'EF' and statusCode ne 'DELETED'"
                )
            ]
        except Exception as exc:
            logger.error("Error listing active users: %s", exc)
            return []

    # ------------------------------------------------------------------
    # AuditLog operations
    # ------------------------------------------------------------------

    def append_audit(self, user_id: str, action: str, details: str) -> None:
        """Append one audit record for *user_id*.

        RowKey uses a timestamp prefix so rows sort chronologically.
        """
        ts = _ts_key()
        entity = {
            "PartitionKey": user_id,
            "RowKey":       f"{ts}_{action}",
            "action":       action,
            "details":      details,
            "executedAt":   datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._audit.create_entity(entity)
        except Exception as exc:
            logger.error("Failed to write audit log [%s / %s]: %s", user_id, action, exc)

    def get_audit_history(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all audit rows for a user, oldest-first."""
        try:
            return sorted(
                [
                    dict(e)
                    for e in self._audit.query_entities(
                        query_filter=f"PartitionKey eq '{user_id}'"
                    )
                ],
                key=lambda r: r.get("RowKey", ""),
            )
        except Exception as exc:
            logger.error("Error fetching audit for %s: %s", user_id, exc)
            return []

    # ------------------------------------------------------------------
    # EmailLog operations
    # ------------------------------------------------------------------

    def append_email_log(
        self,
        user_id: str,
        email_type: str,
        recipient: str,
        subject: str,
        status: str,
        error: str = "",
    ) -> None:
        """Record an email send attempt."""
        ts = _ts_key()
        entity = {
            "PartitionKey":   user_id,
            "RowKey":         f"{ts}_{email_type}",
            "emailType":      email_type,
            "recipientEmail": recipient,
            "subject":        subject,
            "status":         status,
            "errorMessage":   error,
            "sentDate":       datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._email.create_entity(entity)
        except Exception as exc:
            logger.error("Failed to write email log [%s / %s]: %s", user_id, email_type, exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_key() -> str:
    """Return a sortable timestamp string suitable for use as a RowKey prefix."""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
