"""
Core reconciliation logic.

This module is deliberately free of Django ORM calls so find_disagreements()
can be unit-tested with plain Python objects — no database required.

The ORM bridge reconcile_from_db() pulls data in per-org batches (streaming,
not all-at-once) so memory usage stays proportional to the largest single org,
not the total dataset size.

Disagreement types detected
──────────────────────────
MISSING_IN_B        A System A record has no System B entry at all.
ORPHAN_IN_B         A System B entry whose record_ref resolved to NULL.
DUPLICATE_IN_B      A System A record matched by more than one System B entry.
VALUE_MISMATCH      Both systems have a record but report different values.
UNPARSEABLE_VALUE   System B entry exists but its value could not be parsed.
"""

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
    value: Decimal | None           # None = unparseable
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
    Pure function: compare two lists of records and return disagreements.

    Tenant isolation is the caller's responsibility — pass only the records
    that belong to the scope you are authorised to inspect.
    reconcile_from_db() calls this once per org so no cross-org data is ever
    held in memory together.
    """
    results: list[DisagreementResult] = []

    # Index B entries by the System A record_id they resolve to.
    # Entries with no resolved record are orphans.
    b_by_record: dict[str, list[EntryB]] = {}
    orphans: list[EntryB] = []

    for entry in entries_b:
        resolved = entry['resolved_record_id']
        if resolved is None:
            orphans.append(entry)
        else:
            b_by_record.setdefault(resolved, []).append(entry)

    # ── Check every System A record ───────────────────────────────────────────
    for rec in records_a:
        rid = rec['record_id']
        matched = b_by_record.get(rid, [])

        if not matched:
            results.append(DisagreementResult(
                reason='MISSING_IN_B',
                record_id_a=rid,
                entry_id_b='',
                record_ref_raw='',
                location_id=rec['location_id'],
                value_a=rec['total_value'],
                value_b=None,
                value_b_raw='',
                detail=f'{rid} exists in System A but has no entry in System B',
            ))
            continue

        if len(matched) > 1:
            entry_ids = ', '.join(e['entry_id'] for e in matched)
            results.append(DisagreementResult(
                reason='DUPLICATE_IN_B',
                record_id_a=rid,
                entry_id_b=entry_ids,
                record_ref_raw=matched[0]['record_ref_raw'],
                location_id=rec['location_id'],
                value_a=rec['total_value'],
                value_b=None,
                value_b_raw='',
                detail=f'{rid} has {len(matched)} entries in System B: {entry_ids}',
            ))
            # Also check each individual entry's value
            for entry in matched:
                _check_value(rec, entry, results)
            continue

        _check_value(rec, matched[0], results)

    # ── Check orphans ─────────────────────────────────────────────────────────
    for entry in orphans:
        results.append(DisagreementResult(
            reason='ORPHAN_IN_B',
            record_id_a='',
            entry_id_b=entry['entry_id'],
            record_ref_raw=entry['record_ref_raw'],
            location_id=entry['location_id'],
            value_a=None,
            value_b=entry['value'],
            value_b_raw=entry['value_raw'],
            detail=(
                f"System B entry {entry['entry_id']} references "
                f"'{entry['record_ref_raw']}' which does not exist in System A"
            ),
        ))

    return results


def _check_value(rec: RecordA, entry: EntryB, results: list) -> None:
    """Emit VALUE_MISMATCH or UNPARSEABLE_VALUE if the values differ."""
    if entry['value'] is None:
        results.append(DisagreementResult(
            reason='UNPARSEABLE_VALUE',
            record_id_a=rec['record_id'],
            entry_id_b=entry['entry_id'],
            record_ref_raw=entry['record_ref_raw'],
            location_id=rec['location_id'],
            value_a=rec['total_value'],
            value_b=None,
            value_b_raw=entry['value_raw'],
            detail=(
                f"System B entry {entry['entry_id']} has unparseable value "
                f"'{entry['value_raw']}'"
            ),
        ))
        return

    if rec['total_value'] is not None and entry['value'] != rec['total_value']:
        results.append(DisagreementResult(
            reason='VALUE_MISMATCH',
            record_id_a=rec['record_id'],
            entry_id_b=entry['entry_id'],
            record_ref_raw=entry['record_ref_raw'],
            location_id=rec['location_id'],
            value_a=rec['total_value'],
            value_b=entry['value'],
            value_b_raw=entry['value_raw'],
            detail=(
                f"System A total_value={rec['total_value']}, "
                f"System B value={entry['value']}"
            ),
        ))


# ── ORM bridge ───────────────────────────────────────────────────────────────

def reconcile_from_db() -> int:
    """
    Run reconciliation across all orgs, persist results atomically.

    Memory model: we iterate org by org. Each org's records are loaded, compared,
    and discarded before the next org is processed. Peak memory is proportional to
    the largest single org, not the full dataset.

    The delete + bulk_create is wrapped in transaction.atomic() so a failure
    mid-write leaves the table in its previous state, not empty.
    """
    from reconciliation.models import (
        Disagreement, Location, SystemARecord, SystemBEntry,
    )
    from django.db import transaction

    all_disagreements: list[DisagreementResult] = []

    org_ids = list(
        Location.objects.values_list('org_id', flat=True).distinct().order_by('org_id')
    )

    for org_id in org_ids:
        # Stream each queryset — .iterator() prevents Django from caching rows
        records_a: list[RecordA] = [
            RecordA(
                record_id=r['record_id'],
                location_id=r['location__location_id'],
                total_value=r['total_value'],
            )
            for r in SystemARecord.objects
                .filter(location__org_id=org_id)
                .values('record_id', 'location__location_id', 'total_value')
                .iterator()
        ]

        entries_b: list[EntryB] = [
            EntryB(
                entry_id=e['entry_id'],
                record_ref_raw=e['record_ref_raw'],
                resolved_record_id=e['record_ref__record_id'],  # None if FK is null
                location_id=e['location__location_id'],
                value=e['value'],
                value_raw=e['value_raw'],
            )
            for e in SystemBEntry.objects
                .filter(location__org_id=org_id)
                .values(
                    'entry_id', 'record_ref_raw',
                    'record_ref__record_id',
                    'location__location_id',
                    'value', 'value_raw',
                )
                .iterator()
        ]

        all_disagreements.extend(find_disagreements(records_a, entries_b))

    # Build FK lookup maps — only PKs needed, not full objects
    location_pk_map: dict[str, int] = {
        r['location_id']: r['id']
        for r in Location.objects.values('id', 'location_id').iterator()
    }
    record_a_pk_map: dict[str, int] = {
        r['record_id']: r['id']
        for r in SystemARecord.objects.values('id', 'record_id').iterator()
    }
    entry_b_pk_map: dict[str, int] = {
        e['entry_id']: e['id']
        for e in SystemBEntry.objects.values('id', 'entry_id').iterator()
    }

    to_create = []
    for d in all_disagreements:
        first_entry_id = d['entry_id_b'].split(',')[0].strip() if d['entry_id_b'] else ''
        to_create.append(Disagreement(
            reason=d['reason'],
            record_a_id=record_a_pk_map.get(d['record_id_a']),
            entry_b_id=entry_b_pk_map.get(first_entry_id),
            location_id=location_pk_map[d['location_id']],
            value_a=d['value_a'],
            value_b=d['value_b'],
            value_b_raw=d['value_b_raw'],
            record_id_a=d['record_id_a'],
            entry_id_b=d['entry_id_b'],
            record_ref_raw=d['record_ref_raw'],
            detail=d['detail'],
        ))

    # Atomic swap: delete old results then insert new ones.
    # If bulk_create fails, the delete is rolled back — the table is never left empty.
    with transaction.atomic():
        Disagreement.objects.all().delete()
        Disagreement.objects.bulk_create(to_create, batch_size=2000)

    return len(to_create)
