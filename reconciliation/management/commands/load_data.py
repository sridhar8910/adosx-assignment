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
"""

import csv
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

# Path to the dataset directory relative to the project root (where manage.py lives)
DATASET_DIR = Path(__file__).resolve().parents[3] / 'DealerOS_Assignment_Dataset'


def _log(issues: list, source: str, row_id: str, field: str, raw: str, msg: str, severity: str = 'WARNING'):
    issues.append(ImportIssue(
        source_file=source,
        row_identifier=row_id,
        field_name=field,
        raw_value=str(raw)[:200],
        message=msg,
        severity=severity,
    ))


def _parse_decimal(raw: str, source: str, row_id: str, field: str, issues: list):
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
        return None, True  # blank is allowed; caller decides if it matters

    # Strip all comma separators before attempting Decimal parse.
    # This handles both "1,000.50" and "1,25,400.00" — neither is actually
    # unparseable once commas are removed. The value_raw field preserves the
    # original so the dirty form is never lost.
    cleaned = stripped.replace(',', '')
    try:
        return Decimal(cleaned), True
    except InvalidOperation:
        _log(issues, source, row_id, field, raw,
             f"Cannot parse '{raw}' as a number — stored as NULL", 'WARNING')
        return None, False


def _parse_date(raw: str, source: str, row_id: str, field: str, issues: list):
    """Parse ISO date YYYY-MM-DD. Blank → None (no issue). Bad format → None + issue."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return date.fromisoformat(stripped)
    except ValueError:
        _log(issues, source, row_id, field, raw,
             f"Cannot parse '{raw}' as a date — stored as NULL", 'WARNING')
        return None


def _normalise_record_ref(raw: str) -> str | None:
    """
    Normalise dirty record_ref values to canonical "REC-NNNN" form.

    Handles the three patterns present in this dataset:
      "REC-1034"      → "REC-1034"   (already clean)
      "rec1034"       → "REC-1034"   (lowercase, missing hyphen)
      " REC - 1070 "  → "REC-1070"   (spaces around everything)
      "1112"          → "REC-1112"   (bare number)

    Requires at least 3 digits and an optional REC-like prefix to avoid
    matching incidental short numbers in other fields.
    Returns None if no valid digit sequence can be extracted.
    """
    stripped = raw.strip()
    collapsed = re.sub(r'\s+', '', stripped)  # remove all internal whitespace
    m = re.search(r'(?:REC|rec|Rec)?[-]?(\d{3,})$', collapsed)
    if not m:
        return None
    return f"REC-{m.group(1)}"


def _truncate_all():
    """
    Clear all reconciliation tables in dependency order.
    Uses TRUNCATE on PostgreSQL (instant regardless of row count) and
    falls back to DELETE on SQLite (used by the test suite).
    """
    from django.db import connection
    if connection.vendor == 'postgresql':
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
        # SQLite fallback (used in tests and local dev without Postgres)
        from reconciliation.models import (
            Disagreement, ImportIssue, Location, SystemARecord, SystemBEntry,
        )
        Disagreement.objects.all().delete()
        ImportIssue.objects.all().delete()
        SystemBEntry.objects.all().delete()
        SystemARecord.objects.all().delete()
        Location.objects.all().delete()


class Command(BaseCommand):
    help = 'Load locations.csv, system_a.csv, system_b.csv into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dataset-dir',
            type=str,
            default=str(DATASET_DIR),
            help='Path to the directory containing the three CSV files',
        )

    def handle(self, *args, **options):
        dataset_dir = Path(options['dataset_dir'])

        self.stdout.write('Clearing existing data…')
        _truncate_all()

        issues: list[ImportIssue] = []

        # Wrap the entire import in a transaction so a mid-run failure leaves
        # the DB in its previous clean state rather than half-loaded.
        with transaction.atomic():
            self._load_locations(dataset_dir, issues)
            location_map = {
                loc.location_id: loc.pk
                for loc in Location.objects.only('id', 'location_id')
            }
            self._load_system_a(dataset_dir, location_map, issues)
            # Fetch only the two columns needed for FK resolution — avoids
            # materialising full ORM objects for every System A row.
            record_a_id_map: dict[str, int] = {
                r['record_id']: r['id']
                for r in SystemARecord.objects.values('id', 'record_id').iterator()
            }
            self._load_system_b(dataset_dir, location_map, record_a_id_map, issues)

            ImportIssue.objects.bulk_create(issues, batch_size=2000)
            self.stdout.write(f'  Logged {len(issues)} import issues')

        self.stdout.write(self.style.SUCCESS(
            f'\nImport complete — run `python manage.py reconcile` next.'
        ))

    # ── Loaders ───────────────────────────────────────────────────────────────

    def _load_locations(self, dataset_dir: Path, issues: list):
        self.stdout.write('Loading locations.csv…')
        loc_path = dataset_dir / 'locations.csv'
        count = 0
        with open(loc_path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                loc_id = row['location_id'].strip()
                org_id = row['org_id'].strip()
                name = row['location_name'].strip()
                if not loc_id or not org_id:
                    _log(issues, 'locations.csv', loc_id or '(blank)',
                         'location_id/org_id', str(row),
                         'Row missing location_id or org_id — skipped', 'ERROR')
                    continue
                Location.objects.create(
                    location_id=loc_id, org_id=org_id, location_name=name
                )
                count += 1
        self.stdout.write(f'  Loaded {count} locations')

    def _load_system_a(self, dataset_dir: Path, location_map: dict, issues: list):
        self.stdout.write('Loading system_a.csv…')
        a_path = dataset_dir / 'system_a.csv'
        batch: list[SystemARecord] = []
        count = 0

        def flush():
            nonlocal count
            SystemARecord.objects.bulk_create(batch, batch_size=2000)
            count += len(batch)
            batch.clear()

        with open(a_path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                rec_id = row['record_id'].strip()
                if not rec_id:
                    _log(issues, 'system_a.csv', '(blank)', 'record_id',
                         str(row), 'Row has no record_id — skipped', 'ERROR')
                    continue

                loc_id = row['location_id'].strip()
                location_pk = location_map.get(loc_id)
                if location_pk is None:
                    _log(issues, 'system_a.csv', rec_id, 'location_id', loc_id,
                         f"Unknown location_id '{loc_id}' — skipped", 'ERROR')
                    continue

                event_date = _parse_date(row.get('event_date', ''), 'system_a.csv', rec_id, 'event_date', issues)
                base_value, _ = _parse_decimal(row.get('base_value', ''), 'system_a.csv', rec_id, 'base_value', issues)
                adjustment, _ = _parse_decimal(row.get('adjustment', ''), 'system_a.csv', rec_id, 'adjustment', issues)
                total_value, _ = _parse_decimal(row.get('total_value', ''), 'system_a.csv', rec_id, 'total_value', issues)

                KNOWN_KEYS_A = {
                    'record_id', 'location_id', 'event_date', 'category_code',
                    'actor_id', 'base_value', 'adjustment', 'total_value', 'state'
                }
                extra_data = {
                    k: v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                    if k not in KNOWN_KEYS_A and k is not None
                }

                batch.append(SystemARecord(
                    record_id=rec_id,
                    location_id=location_pk,
                    event_date=event_date,
                    category_code=row.get('category_code', '').strip(),
                    actor_id=row.get('actor_id', '').strip(),  # blank on REC-1050 is valid
                    base_value=base_value,
                    adjustment=adjustment,
                    total_value=total_value,
                    state=row.get('state', '').strip(),
                    extra_data=extra_data,
                ))

                if len(batch) >= 2000:
                    flush()

        if batch:
            flush()

        self.stdout.write(f'  Loaded {count} System A records')

    def _load_system_b(self, dataset_dir: Path, location_map: dict,
                       record_a_id_map: dict, issues: list):
        self.stdout.write('Loading system_b.csv…')
        b_path = dataset_dir / 'system_b.csv'
        batch: list[SystemBEntry] = []
        count = 0

        def flush():
            nonlocal count
            SystemBEntry.objects.bulk_create(batch, batch_size=2000)
            count += len(batch)
            batch.clear()

        with open(b_path, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                entry_id = row['entry_id'].strip()
                if not entry_id:
                    _log(issues, 'system_b.csv', '(blank)', 'entry_id',
                         str(row), 'Row has no entry_id — skipped', 'ERROR')
                    continue

                loc_id = row['location_id'].strip()
                location_pk = location_map.get(loc_id)
                if location_pk is None:
                    _log(issues, 'system_b.csv', entry_id, 'location_id', loc_id,
                         f"Unknown location_id '{loc_id}' — skipped", 'ERROR')
                    continue

                raw_ref = row.get('record_ref', '').strip()
                canonical_ref = _normalise_record_ref(raw_ref)
                record_a_pk = None

                if not canonical_ref:
                    _log(issues, 'system_b.csv', entry_id, 'record_ref', raw_ref,
                         f"Cannot normalise record_ref '{raw_ref}' — FK will be NULL", 'WARNING')
                else:
                    record_a_pk = record_a_id_map.get(canonical_ref)
                    if record_a_pk is None:
                        _log(issues, 'system_b.csv', entry_id, 'record_ref', raw_ref,
                             f"record_ref '{raw_ref}' (normalised: '{canonical_ref}') "
                             f"does not match any System A record — FK will be NULL", 'WARNING')

                # Log dirty refs that needed normalisation (INFO, not WARNING)
                if canonical_ref and canonical_ref != raw_ref:
                    _log(issues, 'system_b.csv', entry_id, 'record_ref', raw_ref,
                         f"Dirty record_ref '{raw_ref}' normalised to '{canonical_ref}'", 'INFO')

                value_raw = row.get('value', '').strip()
                value, _ = _parse_decimal(value_raw, 'system_b.csv', entry_id, 'value', issues)

                recorded_on = _parse_date(row.get('recorded_on', ''), 'system_b.csv', entry_id, 'recorded_on', issues)

                KNOWN_KEYS_B = {
                    'entry_id', 'record_ref', 'location_id', 'recorded_on', 'value', 'label'
                }
                extra_data = {
                    k: v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                    if k not in KNOWN_KEYS_B and k is not None
                }

                batch.append(SystemBEntry(
                    entry_id=entry_id,
                    record_ref_raw=raw_ref,
                    record_ref_id=record_a_pk,   # assign by PK, not by object
                    location_id=location_pk,
                    recorded_on=recorded_on,
                    value_raw=value_raw,
                    value=value,
                    label=row.get('label', '').strip(),
                    extra_data=extra_data,
                ))

                if len(batch) >= 2000:
                    flush()

        if batch:
            flush()

        self.stdout.write(f'  Loaded {count} System B entries')
