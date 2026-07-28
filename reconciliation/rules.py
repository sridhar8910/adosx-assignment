"""
Reconciliation rules — Strategy pattern.

Each disagreement type is an independent ReconciliationRule subclass.
RuleEngine owns the list of registered rules and runs them in order.

Open/Closed Principle: adding a new disagreement type means adding one new
class and registering it in RuleEngine.__init__. No existing rule is touched.

Usage (handled internally by find_disagreements in reconciler.py):
    engine = RuleEngine()
    results = engine.run(records_a, entries_b)
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reconciliation.reconciler import DisagreementResult, EntryB, RecordA


class ReconciliationRule(abc.ABC):
    """Abstract base for all reconciliation rules."""

    @abc.abstractmethod
    def check(
        self,
        record: RecordA,
        matched_entries: list[EntryB],
        results: list[DisagreementResult],
    ) -> None:
        """
        Inspect one System A record and its matched System B entries.
        Append any disagreements found to *results*.
        """


# ── Concrete rules ────────────────────────────────────────────────────────────


class MissingInBRule(ReconciliationRule):
    """A System A record that has no corresponding System B entry at all."""

    def check(
        self,
        record: RecordA,
        matched_entries: list[EntryB],
        results: list[DisagreementResult],
    ) -> None:
        if not matched_entries:
            from reconciliation.reconciler import DisagreementResult as DR

            results.append(
                DR(
                    reason="MISSING_IN_B",
                    record_id_a=record["record_id"],
                    entry_id_b="",
                    record_ref_raw="",
                    location_id=record["location_id"],
                    value_a=record["total_value"],
                    value_b=None,
                    value_b_raw="",
                    detail=(
                        f"{record['record_id']} exists in System A but has no entry in System B"
                    ),
                )
            )


class DuplicateInBRule(ReconciliationRule):
    """A System A record that has more than one System B entry pointing at it."""

    def check(
        self,
        record: RecordA,
        matched_entries: list[EntryB],
        results: list[DisagreementResult],
    ) -> None:
        if len(matched_entries) > 1:
            from reconciliation.reconciler import DisagreementResult as DR

            entry_ids = ", ".join(e["entry_id"] for e in matched_entries)
            results.append(
                DR(
                    reason="DUPLICATE_IN_B",
                    record_id_a=record["record_id"],
                    entry_id_b=entry_ids,
                    record_ref_raw=matched_entries[0]["record_ref_raw"],
                    location_id=record["location_id"],
                    value_a=record["total_value"],
                    value_b=None,
                    value_b_raw="",
                    detail=(
                        f"{record['record_id']} has {len(matched_entries)} "
                        f"entries in System B: {entry_ids}"
                    ),
                )
            )


class ValueMismatchRule(ReconciliationRule):
    """
    System B value differs from System A total_value.
    Runs on every matched entry individually so duplicate records also get
    their individual values checked.
    """

    def check(
        self,
        record: RecordA,
        matched_entries: list[EntryB],
        results: list[DisagreementResult],
    ) -> None:
        from reconciliation.reconciler import DisagreementResult as DR

        for entry in matched_entries:
            if entry["value"] is None:
                continue  # handled by UnparseableValueRule
            if record["total_value"] is not None and entry["value"] != record["total_value"]:
                results.append(
                    DR(
                        reason="VALUE_MISMATCH",
                        record_id_a=record["record_id"],
                        entry_id_b=entry["entry_id"],
                        record_ref_raw=entry["record_ref_raw"],
                        location_id=record["location_id"],
                        value_a=record["total_value"],
                        value_b=entry["value"],
                        value_b_raw=entry["value_raw"],
                        detail=(
                            f"System A total_value={record['total_value']}, "
                            f"System B value={entry['value']}"
                        ),
                    )
                )


class UnparseableValueRule(ReconciliationRule):
    """A System B entry whose value field could not be parsed as a number."""

    def check(
        self,
        record: RecordA,
        matched_entries: list[EntryB],
        results: list[DisagreementResult],
    ) -> None:
        from reconciliation.reconciler import DisagreementResult as DR

        for entry in matched_entries:
            if entry["value"] is None:
                results.append(
                    DR(
                        reason="UNPARSEABLE_VALUE",
                        record_id_a=record["record_id"],
                        entry_id_b=entry["entry_id"],
                        record_ref_raw=entry["record_ref_raw"],
                        location_id=record["location_id"],
                        value_a=record["total_value"],
                        value_b=None,
                        value_b_raw=entry["value_raw"],
                        detail=(
                            f"System B entry {entry['entry_id']} has "
                            f"unparseable value '{entry['value_raw']}'"
                        ),
                    )
                )


# ── Engine ────────────────────────────────────────────────────────────────────


class RuleEngine:
    """
    Runs all registered rules against every System A record, then emits
    ORPHAN_IN_B for every System B entry that could not be resolved.

    Extend by appending a new ReconciliationRule to self.rules — nothing else
    needs to change.
    """

    def __init__(self) -> None:
        self.rules: list[ReconciliationRule] = [
            MissingInBRule(),
            DuplicateInBRule(),
            ValueMismatchRule(),
            UnparseableValueRule(),
        ]

    def run(
        self,
        records_a: list[RecordA],
        entries_b: list[EntryB],
    ) -> list[DisagreementResult]:
        from reconciliation.reconciler import DisagreementResult as DR

        results: list[DR] = []

        # Index B entries by resolved record_id; collect orphans separately
        b_by_record: dict[str, list[EntryB]] = {}
        orphans: list[EntryB] = []
        for entry in entries_b:
            resolved = entry["resolved_record_id"]
            if resolved is None:
                orphans.append(entry)
            else:
                b_by_record.setdefault(resolved, []).append(entry)

        # Run all record-level rules
        for record in records_a:
            matched = b_by_record.get(record["record_id"], [])
            for rule in self.rules:
                rule.check(record, matched, results)

        # Orphan B entries — one ORPHAN_IN_B per unresolved entry
        for entry in orphans:
            results.append(
                DR(
                    reason="ORPHAN_IN_B",
                    record_id_a="",
                    entry_id_b=entry["entry_id"],
                    record_ref_raw=entry["record_ref_raw"],
                    location_id=entry["location_id"],
                    value_a=None,
                    value_b=entry["value"],
                    value_b_raw=entry["value_raw"],
                    detail=(
                        f"System B entry {entry['entry_id']} references "
                        f"'{entry['record_ref_raw']}' which does not exist in System A"
                    ),
                )
            )

        return results
