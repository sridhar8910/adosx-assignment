"""
Tests for the pure reconciliation logic in reconciler.py.

Each test covers exactly one disagreement type.
find_disagreements() takes plain dicts so no database is needed.
"""

from decimal import Decimal

import pytest

from reconciliation.reconciler import find_disagreements, RecordA, EntryB


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_record(record_id='REC-0001', location_id='LOC-101', total_value='100.00') -> RecordA:
    return RecordA(
        record_id=record_id,
        location_id=location_id,
        total_value=Decimal(total_value) if total_value is not None else None,
    )


def make_entry(
    entry_id='ENT-0001',
    resolved_record_id='REC-0001',
    record_ref_raw='REC-0001',
    location_id='LOC-101',
    value='100.00',
    value_raw=None,
) -> EntryB:
    v = Decimal(value) if value is not None else None
    return EntryB(
        entry_id=entry_id,
        record_ref_raw=record_ref_raw,
        resolved_record_id=resolved_record_id,
        location_id=location_id,
        value=v,
        value_raw=value_raw if value_raw is not None else (value or ''),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMissingInB:
    """A System A record with no matching System B entry."""

    def test_missing_record_flagged(self):
        records = [make_record('REC-0001')]
        entries = []  # nothing in B

        results = find_disagreements(records, entries)

        assert len(results) == 1
        assert results[0]['reason'] == 'MISSING_IN_B'
        assert results[0]['record_id_a'] == 'REC-0001'

    def test_present_record_not_flagged(self):
        records = [make_record('REC-0001')]
        entries = [make_entry('ENT-0001', resolved_record_id='REC-0001', value='100.00')]

        results = find_disagreements(records, entries)

        missing = [r for r in results if r['reason'] == 'MISSING_IN_B']
        assert missing == []


class TestOrphanInB:
    """A System B entry whose record_ref resolved to nothing."""

    def test_orphan_entry_flagged(self):
        records = []  # nothing in A
        entries = [make_entry('ENT-9001', resolved_record_id=None, record_ref_raw='REC-1999')]

        results = find_disagreements(records, entries)

        assert len(results) == 1
        assert results[0]['reason'] == 'ORPHAN_IN_B'
        assert results[0]['entry_id_b'] == 'ENT-9001'
        assert results[0]['record_ref_raw'] == 'REC-1999'

    def test_resolved_entry_not_orphan(self):
        records = [make_record('REC-0001')]
        entries = [make_entry('ENT-0001', resolved_record_id='REC-0001')]

        results = find_disagreements(records, entries)

        orphans = [r for r in results if r['reason'] == 'ORPHAN_IN_B']
        assert orphans == []


class TestDuplicateInB:
    """Two System B entries point at the same System A record."""

    def test_duplicate_flagged(self):
        records = [make_record('REC-0001')]
        entries = [
            make_entry('ENT-0001', resolved_record_id='REC-0001'),
            make_entry('ENT-0002', resolved_record_id='REC-0001'),
        ]

        results = find_disagreements(records, entries)

        dups = [r for r in results if r['reason'] == 'DUPLICATE_IN_B']
        assert len(dups) == 1
        assert 'ENT-0001' in dups[0]['entry_id_b']
        assert 'ENT-0002' in dups[0]['entry_id_b']
        assert dups[0]['record_id_a'] == 'REC-0001'

    def test_single_entry_not_duplicate(self):
        records = [make_record('REC-0001')]
        entries = [make_entry('ENT-0001', resolved_record_id='REC-0001')]

        results = find_disagreements(records, entries)

        dups = [r for r in results if r['reason'] == 'DUPLICATE_IN_B']
        assert dups == []


class TestValueMismatch:
    """System B value differs from System A total_value."""

    def test_mismatch_flagged(self):
        records = [make_record('REC-0001', total_value='100.00')]
        entries = [make_entry('ENT-0001', resolved_record_id='REC-0001', value='99.00')]

        results = find_disagreements(records, entries)

        mismatches = [r for r in results if r['reason'] == 'VALUE_MISMATCH']
        assert len(mismatches) == 1
        assert mismatches[0]['value_a'] == Decimal('100.00')
        assert mismatches[0]['value_b'] == Decimal('99.00')

    def test_matching_value_not_flagged(self):
        records = [make_record('REC-0001', total_value='100.00')]
        entries = [make_entry('ENT-0001', resolved_record_id='REC-0001', value='100.00')]

        results = find_disagreements(records, entries)

        mismatches = [r for r in results if r['reason'] == 'VALUE_MISMATCH']
        assert mismatches == []


class TestUnparseableValue:
    """System B entry exists but its value field could not be parsed."""

    def test_unparseable_flagged(self):
        records = [make_record('REC-0001', total_value='183244.16')]
        entries = [
            make_entry(
                'ENT-0001',
                resolved_record_id='REC-0001',
                value=None,          # importer could not parse — stored as NULL
                value_raw='1,25,400.00',
            )
        ]

        results = find_disagreements(records, entries)

        unparseable = [r for r in results if r['reason'] == 'UNPARSEABLE_VALUE']
        assert len(unparseable) == 1
        assert unparseable[0]['value_b_raw'] == '1,25,400.00'
        assert unparseable[0]['entry_id_b'] == 'ENT-0001'

    def test_parseable_value_not_flagged_as_unparseable(self):
        records = [make_record('REC-0001', total_value='100.00')]
        entries = [make_entry('ENT-0001', resolved_record_id='REC-0001', value='100.00')]

        results = find_disagreements(records, entries)

        unparseable = [r for r in results if r['reason'] == 'UNPARSEABLE_VALUE']
        assert unparseable == []


class TestMultipleDisagreementsCoexist:
    """Smoke test: several different disagreement types in one call."""

    def test_all_types_detected(self):
        records = [
            make_record('REC-0001', total_value='100.00'),  # will be missing
            make_record('REC-0002', total_value='200.00'),  # will mismatch
            make_record('REC-0003', total_value='300.00'),  # will be duplicate
        ]
        entries = [
            # REC-0001 has no entry → MISSING_IN_B
            # REC-0002 mismatch
            make_entry('ENT-0002', resolved_record_id='REC-0002', value='999.00'),
            # REC-0003 duplicate
            make_entry('ENT-0003a', resolved_record_id='REC-0003', value='300.00'),
            make_entry('ENT-0003b', resolved_record_id='REC-0003', value='300.00'),
            # Orphan
            make_entry('ENT-9999', resolved_record_id=None, record_ref_raw='REC-9999'),
        ]

        results = find_disagreements(records, entries)
        reasons = {r['reason'] for r in results}

        assert 'MISSING_IN_B' in reasons
        assert 'VALUE_MISMATCH' in reasons
        assert 'DUPLICATE_IN_B' in reasons
        assert 'ORPHAN_IN_B' in reasons


class TestNormalisedRefResolution:
    """
    The reconciler itself doesn't normalise refs — that is done by the importer.
    This test confirms that once a dirty ref is resolved to a canonical record_id,
    the comparison works correctly.
    """

    def test_dirty_ref_resolved_matches_correctly(self):
        # Importer normalised "rec1034" → resolved_record_id='REC-1034'
        records = [make_record('REC-1034', total_value='84939.99')]
        entries = [
            make_entry(
                'ENT/2026/4034',
                resolved_record_id='REC-1034',
                record_ref_raw='rec1034',
                value='84939.99',
            )
        ]

        results = find_disagreements(records, entries)
        # Values match → no disagreements
        assert results == []


class TestCrossTenantMatching:
    """
    Tests for records where System A and System B have mismatched locations/orgs
    (e.g., REC-1077 in LOC-102 matched to ENT/2026/4077 in LOC-201).
    """

    def test_cross_tenant_record_matches_by_id(self):
        records = [make_record('REC-1077', location_id='LOC-102', total_value='83361.40')]
        entries = [
            make_entry(
                'ENT/2026/4077',
                resolved_record_id='REC-1077',
                location_id='LOC-201',
                value='83361.40',
            )
        ]

        results = find_disagreements(records, entries)
        # Record matches by ID and value → not marked as missing in B
        missing = [r for r in results if r['reason'] == 'MISSING_IN_B']
        assert missing == []
