"""
Tests for importer utility functions (no database required).
"""

from decimal import Decimal

from reconciliation.management.commands.load_data import (
    _normalise_record_ref,
    _parse_decimal,
)


class TestNormaliseRecordRef:
    def test_already_clean(self):
        assert _normalise_record_ref("REC-1034") == "REC-1034"

    def test_lowercase_no_hyphen(self):
        # ENT/2026/4034 has "rec1034"
        assert _normalise_record_ref("rec1034") == "REC-1034"

    def test_spaces_everywhere(self):
        # ENT/2026/4070 has " REC - 1070 "
        assert _normalise_record_ref(" REC - 1070 ") == "REC-1070"

    def test_bare_number(self):
        # ENT/2026/4112 has "1112"
        assert _normalise_record_ref("1112") == "REC-1112"

    def test_no_digits_returns_none(self):
        assert _normalise_record_ref("GARBAGE") is None

    def test_empty_string_returns_none(self):
        assert _normalise_record_ref("") is None


class TestParseDecimal:
    def test_normal_float(self):
        val, ok = _parse_decimal("88969.92", "test", "ROW-1", "value", [])
        assert ok is True
        assert val == Decimal("88969.92")

    def test_indian_comma_grouping(self):
        # "1,25,400.00" — the value in ENT/2026/4064
        val, ok = _parse_decimal("1,25,400.00", "test", "ROW-1", "value", [])
        assert ok is True
        assert val == Decimal("125400.00")

    def test_standard_thousand_separator(self):
        val, ok = _parse_decimal("1,000.50", "test", "ROW-1", "value", [])
        assert ok is True
        assert val == Decimal("1000.50")

    def test_blank_returns_none_ok(self):
        val, ok = _parse_decimal("", "test", "ROW-1", "value", [])
        assert ok is True
        assert val is None

    def test_whitespace_returns_none_ok(self):
        val, ok = _parse_decimal("   ", "test", "ROW-1", "value", [])
        assert ok is True
        assert val is None

    def test_unparseable_logs_issue(self):
        issues = []
        val, ok = _parse_decimal("not-a-number", "test", "ROW-1", "value", issues)
        assert ok is False
        assert val is None
        assert len(issues) == 1
        assert "not-a-number" in issues[0].raw_value


class TestImportDynamicColumns:
    def test_dynamic_columns_stored_in_extra_data(self):
        from reconciliation.models import SystemARecord, SystemBEntry

        rec = SystemARecord(
            record_id="REC-9999", extra_data={"dynamic_col_1": "val1", "dynamic_col_2": "val2"}
        )
        assert rec.extra_data == {"dynamic_col_1": "val1", "dynamic_col_2": "val2"}

        entry = SystemBEntry(entry_id="ENT-9999", extra_data={"dynamic_col_x": "valx"})
        assert entry.extra_data == {"dynamic_col_x": "valx"}
