"""
Integration test: load real CSVs, reconcile, verify disagreement count and API shape.
"""

from pathlib import Path

import pytest
from django.core.management import call_command

from reconciliation.models import Disagreement, SystemARecord, SystemBEntry
from reconciliation.reconciler import reconcile_from_db
from reconciliation.serializers import DisagreementSerializer

DATASET_DIR = Path(__file__).resolve().parents[2] / "DealerOS_Assignment_Dataset"


@pytest.mark.django_db
class TestFullPipeline:
    def test_load_and_reconcile_finds_twelve_disagreements(self):
        call_command("load_data", dataset_dir=str(DATASET_DIR))

        assert SystemARecord.objects.count() == 120
        assert SystemBEntry.objects.count() == 121

        count = reconcile_from_db()
        assert count == 12

        by_reason = {}
        for d in Disagreement.objects.values("reason"):
            by_reason[d["reason"]] = by_reason.get(d["reason"], 0) + 1

        assert by_reason == {
            "VALUE_MISMATCH": 6,
            "MISSING_IN_B": 2,
            "DUPLICATE_IN_B": 2,
            "UNPARSEABLE_VALUE": 1,
            "ORPHAN_IN_B": 1,
        }

    def test_serializer_exposes_business_location_id(self):
        call_command("load_data", dataset_dir=str(DATASET_DIR))
        reconcile_from_db()

        disagreement = Disagreement.objects.select_related("location").first()
        assert disagreement is not None

        data = DisagreementSerializer(disagreement).data
        assert data["location_id"].startswith("LOC-")
        assert data["location_id"] == disagreement.location.location_id
