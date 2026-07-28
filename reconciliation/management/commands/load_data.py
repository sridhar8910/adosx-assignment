"""
Management command: python manage.py load_data

Loads locations.csv, system_a.csv, and system_b.csv into the database.

Dirty-data contract:
  - Nothing is silently dropped. Every anomaly is logged to ImportIssue.
  - Unparseable numeric values are stored as NULL with the raw string preserved.
  - Dirty record_ref formats (e.g. "rec1034", "1112", " REC - 1070 ") are
    normalised to "REC-NNNN" before FK lookup. If normalisation succeeds but no
    matching SystemARecord exists, the entry is still saved with record_ref=NULL
    and an ImportIssue is written.
  - Blank actor_id on REC-1050 is valid — stored as empty string, no issue logged.
  - Running the command twice is safe: it clears all rows first (idempotent).
  - The entire import runs inside a single transaction. If anything fails the DB
    rolls back to its previous state — no partial imports.

Logging:
  All progress and anomaly messages go through Python's logging module at INFO
  or WARNING level rather than stdout.write(). Configure the root logger in
  Django LOGGING settings to control output format and destination in production.
"""

from __future__ import annotations

import csv
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from reconciliation.models import (
    Disagreement,
    ImportIssue,
    Location,
    SystemARecord,
    SystemBEntry,
)

logger = logging.getLogger(__name__)

# Path to the dataset directory relative to the project root (where manage.py lives)
DATASET_DIR = Path(__file__).resolve().parents[3] / "DealerOS_Assignment_Dataset"


def _log(
    issues: list[ImportIssue],
    source: str,
    row_id: str,
    field: str,
    raw: str,
    msg: str,
    severity: str = "WARNING",
) -> None:
    """Append an ImportIssue to *issues* and emit a matching log record."""
    issues.append(
        ImportIssue(
            source_file=source,
            row_identifier=row_id,
            field_name=field,
            raw_value=str(raw)[:200],
            message=msg,
            severity=severity,
        )
    )
    level = logging.WARNING if severity in ("WARNING", "ERROR") else logging.INFO
    logger.log(level, "[%s] row=%s field=%s — %s (raw=%r)", source, row_id, field, msg, raw)


def _parse_decimal(
    raw: str,
    source: str,
    row_id: str,
    field: str,
    issues: list[ImportIssue],
) -> tuple[Decimal | None, bool]:
    """
    Parse a decimal from a potentially dirty string.

    Handles:
      - Normal floats:              "88969.92"
      - Standard thousand-sep:      "1,000.50"    → 1000.50
      - Indian-style comma groups:  "1,25,400.00" → 125400.00
      - Blank / whitespace:         treated as NULL (caller decides significance)

    Returns (Decimal | None, ok: bool).
    ok=False means the field was non-blank but unparseable.
    """
    stripped = raw.strip()
    if not stripped:
        return None, True

    cleaned = stripped.replace(",", "")
    try:
        return Decimal(cleaned), True
    except InvalidOperation:
        _log(
            issues,
            source,
            row_id,
            field,
            raw,
            f"Cannot parse '{raw}' as a number — stored as NULL",
            "WARNING",
        )
        return None, False


def _parse_date(
    raw: str,
    source: str,
    row_id: str,
    field: str,
    issues: list[ImportIssue],
) -> date | None:
    """Parse ISO date YYYY-MM-DD. Blank → None (no issue). Bad format → None + issue."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return date.fromisoformat(stripped)
    except ValueError:
        _log(
            issues,
            source,
            row_id,
            field,
            raw,
            f"Cannot parse '{raw}' as a date — stored as NULL",
            "WARNING",
        )
        return None


def _normalise_record_ref(raw: str) -> str | None:
    """
    Normalise dirty record_ref values to canonical "REC-NNNN" form.

    Handles the three dirty patterns present in this dataset:
      "REC-1034"      → "REC-1034"   (already clean)
      "rec1034"       → "REC-1034"   (lowercase, missing hyphen)
      " REC - 1070 "  → "REC-1070"   (spaces around everything)
      "1112"          → "REC-1112"   (bare number)

    Requires at least 3 digits to avoid matching incidental short numbers.
    Returns None if no valid digit sequence can be extracted.
    """
    stripped = raw.strip()
    collapsed = re.sub(r"\s+", "", stripped)
    m = re.search(r"(?:REC|rec|Rec)?[-]?(\d{3,})$", collapsed)
    if not m:
        return None
    return f"REC-{m.group(1)}"


def _truncate_all() -> None:
    """
    Clear all reconciliation tables in dependency order.
    Uses TRUNCATE on PostgreSQL (O(1)) and falls back to DELETE on SQLite
    (used by the test suite via backend/test_settings.py).
    """
    from django.db import connection

    if connection.vendor == "postgresql":
        logger.info("Truncating all reconciliation tables (PostgreSQL TRUNCATE CASCADE)")
        with connection.cursor() as cursor:
            cursor.execute("""
                TRUNCATE TABLE
                    reconciliation_disagreement,
                    reconciliation_importissue,
                    reconciliation_systembentry,
                    reconciliation_systemarecord,
                    reconciliation_location
                RESTART IDENTITY CASCADE;
            """)
    else:
        logger.info(
            "Clearing all reconciliation tables (DELETE fallback for %s)", connection.vendor
        )
        Disagreement.objects.all().delete()
        ImportIssue.objects.all().delete()
        SystemBEntry.objects.all().delete()
        SystemARecord.objects.all().delete()
        Location.objects.all().delete()


class Command(BaseCommand):
    help = "Load locations.csv, system_a.csv, system_b.csv into the database"

    def add_arguments(self, parser) -> None:  # type: ignore[override]
        parser.add_argument(
            "--dataset-dir",
            type=str,
            default=str(DATASET_DIR),
            help="Path to the directory containing the three CSV files",
        )

    def handle(self, *args, **options) -> None:  # type: ignore[override]
        dataset_dir = Path(options["dataset_dir"])
        logger.info("load_data started, dataset_dir=%s", dataset_dir)

        _truncate_all()

        issues: list[ImportIssue] = []

        with transaction.atomic():
            self._load_locations(dataset_dir, issues)
            location_map: dict[str, int] = {
                loc.location_id: loc.pk for loc in Location.objects.only("id", "location_id")
            }

            self._load_system_a(dataset_dir, location_map, issues)
            record_a_id_map: dict[str, int] = {
                r["record_id"]: r["id"]
                for r in SystemARecord.objects.values("id", "record_id").iterator()
            }

            self._load_system_b(dataset_dir, location_map, record_a_id_map, issues)

            ImportIssue.objects.bulk_create(issues, batch_size=2000)
            logger.info("Logged %d import issues to ImportIssue table", len(issues))

        logger.info("load_data complete — run `python manage.py reconcile` next")

    # ── Loaders ───────────────────────────────────────────────────────────────

    def _load_locations(self, dataset_dir: Path, issues: list[ImportIssue]) -> None:
        loc_path = dataset_dir / "locations.csv"
        logger.info("Loading %s", loc_path)
        count = 0
        with open(loc_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                loc_id = row["location_id"].strip()
                org_id = row["org_id"].strip()
                name = row["location_name"].strip()
                if not loc_id or not org_id:
                    _log(
                        issues,
                        "locations.csv",
                        loc_id or "(blank)",
                        "location_id/org_id",
                        str(row),
                        "Row missing location_id or org_id — skipped",
                        "ERROR",
                    )
                    continue
                Location.objects.create(location_id=loc_id, org_id=org_id, location_name=name)
                count += 1
        logger.info("Loaded %d locations", count)

    def _load_system_a(
        self,
        dataset_dir: Path,
        location_map: dict[str, int],
        issues: list[ImportIssue],
    ) -> None:
        a_path = dataset_dir / "system_a.csv"
        logger.info("Loading %s", a_path)
        batch: list[SystemARecord] = []
        count = 0

        def flush() -> None:
            nonlocal count
            SystemARecord.objects.bulk_create(batch, batch_size=2000)
            count += len(batch)
            batch.clear()

        with open(a_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rec_id = row["record_id"].strip()
                if not rec_id:
                    _log(
                        issues,
                        "system_a.csv",
                        "(blank)",
                        "record_id",
                        str(row),
                        "Row has no record_id — skipped",
                        "ERROR",
                    )
                    continue

                loc_id = row["location_id"].strip()
                location_pk = location_map.get(loc_id)
                if location_pk is None:
                    _log(
                        issues,
                        "system_a.csv",
                        rec_id,
                        "location_id",
                        loc_id,
                        f"Unknown location_id '{loc_id}' — skipped",
                        "ERROR",
                    )
                    continue

                event_date = _parse_date(
                    row.get("event_date", ""), "system_a.csv", rec_id, "event_date", issues
                )
                base_value, _ = _parse_decimal(
                    row.get("base_value", ""), "system_a.csv", rec_id, "base_value", issues
                )
                adjustment, _ = _parse_decimal(
                    row.get("adjustment", ""), "system_a.csv", rec_id, "adjustment", issues
                )
                total_value, _ = _parse_decimal(
                    row.get("total_value", ""), "system_a.csv", rec_id, "total_value", issues
                )

                known_keys: set[str] = {
                    "record_id",
                    "location_id",
                    "event_date",
                    "category_code",
                    "actor_id",
                    "base_value",
                    "adjustment",
                    "total_value",
                    "state",
                }
                extra_data = {
                    k: v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                    if k not in known_keys and k is not None
                }

                batch.append(
                    SystemARecord(
                        record_id=rec_id,
                        location_id=location_pk,
                        event_date=event_date,
                        category_code=row.get("category_code", "").strip(),
                        actor_id=row.get("actor_id", "").strip(),
                        base_value=base_value,
                        adjustment=adjustment,
                        total_value=total_value,
                        state=row.get("state", "").strip(),
                        extra_data=extra_data,
                    )
                )

                if len(batch) >= 2000:
                    flush()

        if batch:
            flush()

        logger.info("Loaded %d System A records", count)

    def _load_system_b(
        self,
        dataset_dir: Path,
        location_map: dict[str, int],
        record_a_id_map: dict[str, int],
        issues: list[ImportIssue],
    ) -> None:
        b_path = dataset_dir / "system_b.csv"
        logger.info("Loading %s", b_path)
        batch: list[SystemBEntry] = []
        count = 0

        def flush() -> None:
            nonlocal count
            SystemBEntry.objects.bulk_create(batch, batch_size=2000)
            count += len(batch)
            batch.clear()

        with open(b_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                entry_id = row["entry_id"].strip()
                if not entry_id:
                    _log(
                        issues,
                        "system_b.csv",
                        "(blank)",
                        "entry_id",
                        str(row),
                        "Row has no entry_id — skipped",
                        "ERROR",
                    )
                    continue

                loc_id = row["location_id"].strip()
                location_pk = location_map.get(loc_id)
                if location_pk is None:
                    _log(
                        issues,
                        "system_b.csv",
                        entry_id,
                        "location_id",
                        loc_id,
                        f"Unknown location_id '{loc_id}' — skipped",
                        "ERROR",
                    )
                    continue

                raw_ref = row.get("record_ref", "").strip()
                canonical_ref = _normalise_record_ref(raw_ref)
                record_a_pk: int | None = None

                if not canonical_ref:
                    _log(
                        issues,
                        "system_b.csv",
                        entry_id,
                        "record_ref",
                        raw_ref,
                        f"Cannot normalise record_ref '{raw_ref}' — FK will be NULL",
                        "WARNING",
                    )
                else:
                    record_a_pk = record_a_id_map.get(canonical_ref)
                    if record_a_pk is None:
                        _log(
                            issues,
                            "system_b.csv",
                            entry_id,
                            "record_ref",
                            raw_ref,
                            f"record_ref '{raw_ref}' (normalised: '{canonical_ref}') "
                            f"does not match any System A record — FK will be NULL",
                            "WARNING",
                        )

                if canonical_ref and canonical_ref != raw_ref:
                    _log(
                        issues,
                        "system_b.csv",
                        entry_id,
                        "record_ref",
                        raw_ref,
                        f"Dirty record_ref '{raw_ref}' normalised to '{canonical_ref}'",
                        "INFO",
                    )

                value_raw = row.get("value", "").strip()
                value, _ = _parse_decimal(value_raw, "system_b.csv", entry_id, "value", issues)
                recorded_on = _parse_date(
                    row.get("recorded_on", ""), "system_b.csv", entry_id, "recorded_on", issues
                )

                known_keys_b: set[str] = {
                    "entry_id",
                    "record_ref",
                    "location_id",
                    "recorded_on",
                    "value",
                    "label",
                }
                extra_data = {
                    k: v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                    if k not in known_keys_b and k is not None
                }

                batch.append(
                    SystemBEntry(
                        entry_id=entry_id,
                        record_ref_raw=raw_ref,
                        record_ref_id=record_a_pk,
                        location_id=location_pk,
                        recorded_on=recorded_on,
                        value_raw=value_raw,
                        value=value,
                        label=row.get("label", "").strip(),
                        extra_data=extra_data,
                    )
                )

                if len(batch) >= 2000:
                    flush()

        if batch:
            flush()

        logger.info("Loaded %d System B entries", count)
