"""
Database schema for the reconciliation app.

Design decisions:
- Location is the tenant anchor. Every record links to a Location, and every
  Location belongs to exactly one Org. Org isolation is enforced by always
  filtering through location__org_id in queries, never trusting the caller to
  supply the right org.
- SystemARecord stores every field from system_a.csv. Numeric fields use
  DecimalField so we never lose precision silently. actor_id is nullable because
  REC-1050 has a blank one — that is valid data, not an error.
- SystemBEntry stores every field from system_b.csv. record_ref_raw preserves
  whatever string the CSV contained (including dirty forms like "rec1034" or
  "1112"). record_ref is the resolved FK — null when the ref could not be
  matched, which is itself a disagreement we surface.
- ImportIssue is an append-only log of every anomaly the importer encounters.
  Nothing is silently dropped; problems are recorded here instead.
- Disagreement is computed (not stored long-term) but we materialise it into
  this table on each reconciliation run so the API can query it without
  re-running the comparison on every request.
"""

from django.db import models


class Location(models.Model):
    location_id = models.CharField(max_length=20, unique=True)
    org_id = models.CharField(max_length=20, db_index=True)
    location_name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.location_id} ({self.org_id})"


class SystemARecord(models.Model):
    record_id = models.CharField(max_length=30, unique=True)
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="system_a_records"
    )
    event_date = models.DateField(null=True, blank=True)
    category_code = models.CharField(max_length=20, blank=True)
    actor_id = models.CharField(max_length=20, blank=True)  # blank is valid (REC-1050)
    base_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    adjustment = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    state = models.CharField(max_length=20, blank=True)
    extra_data = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.record_id


class SystemBEntry(models.Model):
    entry_id = models.CharField(max_length=30, unique=True)
    # Raw string from CSV — preserved exactly as imported so nothing is lost
    record_ref_raw = models.CharField(max_length=50)
    # Resolved FK — null means the ref did not match any SystemARecord
    record_ref = models.ForeignKey(
        SystemARecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_b_entries",
    )
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="system_b_entries"
    )
    recorded_on = models.DateField(null=True, blank=True)
    # value_raw: the original string before parsing (preserved even when parsed OK)
    value_raw = models.CharField(max_length=50, blank=True)
    value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    label = models.CharField(max_length=100, blank=True)
    extra_data = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.entry_id} -> {self.record_ref_raw}"


class ImportIssue(models.Model):
    """
    Every anomaly encountered during import is logged here.
    Nothing is silently dropped.
    """

    SEVERITY_INFO = "INFO"
    SEVERITY_WARNING = "WARNING"
    SEVERITY_ERROR = "ERROR"
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, "Info"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_ERROR, "Error"),
    ]

    source_file = models.CharField(max_length=50)
    row_identifier = models.CharField(max_length=50)
    field_name = models.CharField(max_length=50, blank=True)
    raw_value = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=SEVERITY_WARNING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.severity}] {self.source_file} / {self.row_identifier}: {self.message}"


class Disagreement(models.Model):
    """
    One row per disagreement found by the reconciliation engine.
    Re-created on each reconciliation run (truncate + insert).
    """

    REASON_MISSING_IN_B = "MISSING_IN_B"
    REASON_ORPHAN_IN_B = "ORPHAN_IN_B"
    REASON_DUPLICATE_IN_B = "DUPLICATE_IN_B"
    REASON_VALUE_MISMATCH = "VALUE_MISMATCH"
    REASON_UNPARSEABLE_VALUE = "UNPARSEABLE_VALUE"

    REASON_CHOICES = [
        (REASON_MISSING_IN_B, "Missing in System B"),
        (REASON_ORPHAN_IN_B, "Orphan in System B (no matching System A record)"),
        (REASON_DUPLICATE_IN_B, "Duplicate in System B"),
        (REASON_VALUE_MISMATCH, "Value mismatch between systems"),
        (REASON_UNPARSEABLE_VALUE, "System B value could not be parsed"),
    ]

    reason = models.CharField(max_length=30, choices=REASON_CHOICES, db_index=True)

    # The System A record involved (null for orphan-in-B cases)
    record_a = models.ForeignKey(
        SystemARecord, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    # The System B entry involved (null for missing-in-B cases)
    entry_b = models.ForeignKey(
        SystemBEntry, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )

    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="+")

    # Snapshot values at the time of reconciliation for display
    value_a = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    value_b = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    value_b_raw = models.CharField(max_length=50, blank=True)

    record_id_a = models.CharField(max_length=30, blank=True)
    # entry_id_b may hold a comma-joined list for DUPLICATE_IN_B rows
    entry_id_b = models.CharField(max_length=200, blank=True)
    record_ref_raw = models.CharField(max_length=50, blank=True)

    detail = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["reason", "record_id_a"]
        indexes = [
            # Primary query pattern: filter by org (via location) and reason
            models.Index(fields=["location", "reason"]),
            # Sort / lookup by record_id_a
            models.Index(fields=["record_id_a"]),
        ]

    def __str__(self):
        return f"{self.reason}: {self.record_id_a or self.entry_id_b}"
