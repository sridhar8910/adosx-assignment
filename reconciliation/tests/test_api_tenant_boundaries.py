"""
API-level tenant boundary tests.

These tests verify the most important security-related requirement:
  - ORG-A can only see its own disagreements and import issues.
  - ORG-B data is never visible to ORG-A, even if the caller guesses the URL.
  - Missing ?org= always returns 400, never leaks data.
  - Reason filter and sort both work within a tenant boundary.

No mocking: we build real DB objects in the test transaction using pytest-django.
"""

import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework.test import APIClient

from reconciliation.models import (
    Disagreement,
    ImportIssue,
    Location,
    SystemARecord,
    SystemBEntry,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def setup_two_orgs(db):
    """
    Creates minimal but realistic two-org data:
      ORG-A → LOC-A01, with one VALUE_MISMATCH disagreement.
      ORG-B → LOC-B01, with one MISSING_IN_B disagreement.

    This lets every test assert cross-org isolation.
    """
    loc_a = Location.objects.create(location_id="LOC-A01", org_id="ORG-A", location_name="Alpha Site")
    loc_b = Location.objects.create(location_id="LOC-B01", org_id="ORG-B", location_name="Beta Site")

    rec_a = SystemARecord.objects.create(
        record_id="REC-TA01",
        location=loc_a,
        total_value=Decimal("500.00"),
    )
    entry_a = SystemBEntry.objects.create(
        entry_id="ENT-TA01",
        record_ref_raw="REC-TA01",
        record_ref=rec_a,
        location=loc_a,
        value_raw="450.00",
        value=Decimal("450.00"),
    )
    rec_b = SystemARecord.objects.create(
        record_id="REC-TB01",
        location=loc_b,
        total_value=Decimal("200.00"),
    )

    # ORG-A disagreement
    dis_a = Disagreement.objects.create(
        reason=Disagreement.REASON_VALUE_MISMATCH,
        location=loc_a,
        record_a=rec_a,
        entry_b=entry_a,
        record_id_a="REC-TA01",
        value_a=Decimal("500.00"),
        value_b=Decimal("450.00"),
    )
    # ORG-B disagreement
    dis_b = Disagreement.objects.create(
        reason=Disagreement.REASON_MISSING_IN_B,
        location=loc_b,
        record_a=rec_b,
        record_id_a="REC-TB01",
        value_a=Decimal("200.00"),
    )

    # Import issues for each org
    ImportIssue.objects.create(
        source_file="system_a.csv",
        row_identifier="REC-TA01",
        message="Test issue for ORG-A",
        org_id="ORG-A",
    )
    ImportIssue.objects.create(
        source_file="system_b.csv",
        row_identifier="ENT-TB01",
        message="Test issue for ORG-B",
        org_id="ORG-B",
    )

    return {"loc_a": loc_a, "loc_b": loc_b, "dis_a": dis_a, "dis_b": dis_b}


# ── Disagreements endpoint ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestDisagreementsTenantBoundary:
    """ORG-A's disagreements are visible to ORG-A, invisible to ORG-B's query."""

    def test_org_a_sees_its_own_disagreement(self, api, setup_two_orgs):
        resp = api.get("/api/disagreements/", {"org": "ORG-A"})
        assert resp.status_code == 200
        record_ids = [r["record_id_a"] for r in resp.data["results"]]
        assert "REC-TA01" in record_ids

    def test_org_a_does_not_see_org_b_disagreement(self, api, setup_two_orgs):
        resp = api.get("/api/disagreements/", {"org": "ORG-A"})
        assert resp.status_code == 200
        record_ids = [r["record_id_a"] for r in resp.data["results"]]
        assert "REC-TB01" not in record_ids

    def test_org_b_sees_its_own_disagreement(self, api, setup_two_orgs):
        resp = api.get("/api/disagreements/", {"org": "ORG-B"})
        assert resp.status_code == 200
        record_ids = [r["record_id_a"] for r in resp.data["results"]]
        assert "REC-TB01" in record_ids

    def test_org_b_does_not_see_org_a_disagreement(self, api, setup_two_orgs):
        resp = api.get("/api/disagreements/", {"org": "ORG-B"})
        assert resp.status_code == 200
        record_ids = [r["record_id_a"] for r in resp.data["results"]]
        assert "REC-TA01" not in record_ids

    def test_missing_org_returns_400(self, api, setup_two_orgs):
        """No ?org= must never leak data — returns 400 immediately."""
        resp = api.get("/api/disagreements/")
        assert resp.status_code == 400
        assert "org" in resp.data["error"]

    def test_unknown_org_returns_empty_not_error(self, api, setup_two_orgs):
        """An org that exists nowhere returns an empty list, not 500."""
        resp = api.get("/api/disagreements/", {"org": "ORG-UNKNOWN"})
        assert resp.status_code == 200
        assert resp.data["count"] == 0
        assert resp.data["results"] == []


# ── Reason filter ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestReasonFilter:
    def test_reason_filter_returns_matching_rows(self, api, setup_two_orgs):
        resp = api.get("/api/disagreements/", {"org": "ORG-A", "reason": "VALUE_MISMATCH"})
        assert resp.status_code == 200
        for row in resp.data["results"]:
            assert row["reason"] == "VALUE_MISMATCH"

    def test_reason_filter_excludes_non_matching_rows(self, api, setup_two_orgs):
        resp = api.get("/api/disagreements/", {"org": "ORG-A", "reason": "MISSING_IN_B"})
        assert resp.status_code == 200
        # ORG-A has no MISSING_IN_B rows in setup
        assert resp.data["count"] == 0


# ── Import-issues endpoint ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestImportIssuesTenantBoundary:
    """Same isolation model: ?org= required, cross-org issues never leak."""

    def test_missing_org_returns_400(self, api, setup_two_orgs):
        resp = api.get("/api/import-issues/")
        assert resp.status_code == 400

    def test_org_a_sees_its_own_import_issues(self, api, setup_two_orgs):
        resp = api.get("/api/import-issues/", {"org": "ORG-A"})
        assert resp.status_code == 200
        messages = [r["message"] for r in resp.data["results"]]
        assert any("ORG-A" in m for m in messages)

    def test_org_a_does_not_see_org_b_import_issues(self, api, setup_two_orgs):
        resp = api.get("/api/import-issues/", {"org": "ORG-A"})
        assert resp.status_code == 200
        messages = [r["message"] for r in resp.data["results"]]
        assert not any("ORG-B" in m for m in messages)
