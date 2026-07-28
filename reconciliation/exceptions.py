"""
Custom exceptions for the reconciliation app.

Using specific exception types instead of bare Exception means:
  - Views can catch and handle each failure mode independently.
  - Log messages carry structured context (field names, identifiers).
  - The call stack makes it immediately clear what kind of failure occurred.
"""

from __future__ import annotations


class ReconciliationError(Exception):
    """Base class for all reconciliation-domain errors."""


class ImportValidationError(ReconciliationError):
    """
    A CSV row failed validation and could not be imported.

    Example:
        raise ImportValidationError("system_a.csv", "REC-1001", "total_value", "not a number")
    """

    def __init__(self, source_file: str, row_id: str, field: str, message: str) -> None:
        self.source_file = source_file
        self.row_id = row_id
        self.field = field
        super().__init__(f"[{source_file}] row={row_id} field={field}: {message}")


class InvalidRecordReference(ReconciliationError):
    """
    A System B record_ref could not be normalised to a valid System A record_id.

    Example:
        raise InvalidRecordReference("ENT/2026/4901", "REC-1999")
    """

    def __init__(self, entry_id: str, raw_ref: str) -> None:
        self.entry_id = entry_id
        self.raw_ref = raw_ref
        super().__init__(
            f"Entry {entry_id}: cannot resolve record_ref '{raw_ref}' to any System A record"
        )


class TenantIsolationError(ReconciliationError):
    """
    An operation would have crossed a tenant boundary.

    Raised when the org derived from a record does not match the org
    the caller is authorised to access.

    Example:
        raise TenantIsolationError(expected_org="ORG-A", actual_org="ORG-B")
    """

    def __init__(self, expected_org: str, actual_org: str) -> None:
        self.expected_org = expected_org
        self.actual_org = actual_org
        super().__init__(
            f"Tenant violation: caller is authorised for {expected_org!r} "
            f"but record belongs to {actual_org!r}"
        )


class DuplicateEntryError(ReconciliationError):
    """
    A record already exists and upsert is not permitted for this operation.

    Example:
        raise DuplicateEntryError("SystemARecord", "REC-1001")
    """

    def __init__(self, model: str, identifier: str) -> None:
        self.model = model
        self.identifier = identifier
        super().__init__(f"Duplicate {model}: {identifier} already exists")


class ReconciliationDataError(ReconciliationError):
    """
    The data in the database is in an inconsistent state that prevents
    reconciliation from completing (e.g. a location_id referenced by a
    Disagreement row no longer exists).
    """
