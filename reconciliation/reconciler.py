"""
Core reconciliation logic.

This module is deliberately free of Django ORM calls so find_disagreements()
can be unit-tested with plain Python objects — no database required.

Disagreement detection is implemented via the Strategy pattern in rules.py.
Each disagreement type is a separate ReconciliationRule subclass. RuleEngine
runs them all; adding a new rule requires no changes here.

The ORM bridge reconcile_from_db() loads all records globally (streaming via
.iterator()) so cross-tenant record_id matches resolve correctly. Tenant
isolation is enforced when serving results through the API, not during comparison.

Disagreement types detected (see reconciliation/rules.py for implementations)
──────────────────────────────────────────────────────────────────────────────
MISSING_IN_B        A System A record has no System B entry at all.
ORPHAN_IN_B         A System B entry whose record_ref resolved to NULL.
DUPLICATE_IN_B      A System A record matched by more than one System B entry.
VALUE_MISMATCH      Both systems have a record but report different values.
UNPARSEABLE_VALUE   System B entry exists but its value could not be parsed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TypedDict


class RecordA(TypedDict):
    record_id: str
    location_id: str
    total_value: Decimal | None


class EntryB(TypedDict):
    entry_id: str
    record_ref_raw: str
    resolved_record_id: str | None  # None = ref could not be resolved
    location_id: str
    value: Decimal | None  # None = unparseable
    value_raw: str


class DisagreementResult(TypedDict):
    reason: str
    record_id_a: str
    entry_id_b: str
    record_ref_raw: str
    location_id: str
    value_a: Decimal | None
    value_b: Decimal | None
    value_b_raw: str
    detail: str


def find_disagreements(
    records_a: list[RecordA],
    entries_b: list[EntryB],
) -> list[DisagreementResult]:
    """
    Pure function: compare two lists of records and return all disagreements.

    Delegates to RuleEngine which runs each ReconciliationRule in turn.
    reconcile_from_db() passes the full global dataset so cross-tenant
    record_id matches (e.g. REC-1077) resolve correctly.
    Tenant isolation is enforced at API query time.
    """
    from reconciliation.rules import RuleEngine

    return RuleEngine().run(records_a, entries_b)


# ── ORM bridge ───────────────────────────────────────────────────────────────


def reconcile_from_db() -> int:
    """
    Run reconciliation across all orgs, persist results atomically.

    Loads all System A records and System B entries globally so cross-tenant
    record_id matches resolve correctly. Results are stored with each row's
    location; the API filters by org_id when serving tenants.

    The delete + bulk_create is wrapped in transaction.atomic() so a failure
    mid-write leaves the table in its previous state, not empty.
    """
    import logging

    from django.db import transaction

    from reconciliation.models import (
        Disagreement,
        Location,
        SystemARecord,
        SystemBEntry,
    )

    logger = logging.getLogger(__name__)
    logger.info("reconcile_from_db: loading records from database")

    records_a: list[RecordA] = [
        RecordA(
            record_id=r["record_id"],
            location_id=r["location__location_id"],
            total_value=r["total_value"],
        )
        for r in SystemARecord.objects.values(
            "record_id", "location__location_id", "total_value"
        ).iterator()
    ]

    entries_b: list[EntryB] = [
        EntryB(
            entry_id=e["entry_id"],
            record_ref_raw=e["record_ref_raw"],
            resolved_record_id=e["record_ref__record_id"],
            location_id=e["location__location_id"],
            value=e["value"],
            value_raw=e["value_raw"],
        )
        for e in SystemBEntry.objects.values(
            "entry_id",
            "record_ref_raw",
            "record_ref__record_id",
            "location__location_id",
            "value",
            "value_raw",
        ).iterator()
    ]

    logger.info(
        "reconcile_from_db: loaded %d System A records and %d System B entries",
        len(records_a),
        len(entries_b),
    )

    all_disagreements = find_disagreements(records_a, entries_b)

    logger.info("reconcile_from_db: found %d disagreements, persisting", len(all_disagreements))

    # Build FK lookup maps — only PKs needed, not full objects
    location_pk_map: dict[str, int] = {
        r["location_id"]: r["id"] for r in Location.objects.values("id", "location_id").iterator()
    }
    record_a_pk_map: dict[str, int] = {
        r["record_id"]: r["id"] for r in SystemARecord.objects.values("id", "record_id").iterator()
    }
    entry_b_pk_map: dict[str, int] = {
        e["entry_id"]: e["id"] for e in SystemBEntry.objects.values("id", "entry_id").iterator()
    }

    to_create = []
    for d in all_disagreements:
        first_entry_id = d["entry_id_b"].split(",")[0].strip() if d["entry_id_b"] else ""
        to_create.append(
            Disagreement(
                reason=d["reason"],
                record_a_id=record_a_pk_map.get(d["record_id_a"]),
                entry_b_id=entry_b_pk_map.get(first_entry_id),
                location_id=location_pk_map[d["location_id"]],
                value_a=d["value_a"],
                value_b=d["value_b"],
                value_b_raw=d["value_b_raw"],
                record_id_a=d["record_id_a"],
                entry_id_b=d["entry_id_b"],
                record_ref_raw=d["record_ref_raw"],
                detail=d["detail"],
            )
        )

    # Atomic swap: delete old results then insert new ones.
    # If bulk_create fails the delete is rolled back — table never left empty.
    with transaction.atomic():
        Disagreement.objects.all().delete()
        Disagreement.objects.bulk_create(to_create, batch_size=2000)

    logger.info("reconcile_from_db: done, %d disagreements written", len(to_create))
    return len(to_create)
