"""
API views.

Tenant isolation: every query is scoped to a single org_id supplied as a query
parameter. No org_id → 400. This is a stand-in for real authentication; in
production the org would come from the authenticated user's session, not a
query param.

Endpoints
─────────
GET /api/disagreements/?org=ORG-A
    Returns disagreements for the given org.
    Optional filters: ?reason=VALUE_MISMATCH
    Optional sort:    ?sort=value_a  or  ?sort=-value_a  (prefix - for desc)

GET /api/import-issues/
    Returns the log of import anomalies (not tenant-scoped — admin view).

GET /api/reasons/
    Returns the list of valid reason codes and their display labels.
"""

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Disagreement, ImportIssue
from .serializers import DisagreementSerializer, ImportIssueSerializer

VALID_SORT_FIELDS = {
    "value_a",
    "-value_a",
    "value_b",
    "-value_b",
    "record_id_a",
    "-record_id_a",
    "reason",
    "-reason",
}


@api_view(["GET"])
def disagreements(request):
    org_id = request.query_params.get("org", "").strip()
    if not org_id:
        return Response(
            {"error": "org query parameter is required (e.g. ?org=ORG-A)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Tenant isolation enforced here: filter by org through the Location FK
    qs = Disagreement.objects.select_related("location").filter(location__org_id=org_id)

    # Optional reason filter
    reason = request.query_params.get("reason", "").strip()
    if reason:
        qs = qs.filter(reason=reason)

    # Optional sort
    sort = request.query_params.get("sort", "reason").strip()
    if sort not in VALID_SORT_FIELDS:
        sort = "reason"
    qs = qs.order_by(sort, "record_id_a")

    serializer = DisagreementSerializer(qs, many=True)
    return Response(
        {
            "org_id": org_id,
            "count": qs.count(),
            "results": serializer.data,
        }
    )


@api_view(["GET"])
def import_issues(request):
    qs = ImportIssue.objects.all().order_by("source_file", "row_identifier")
    serializer = ImportIssueSerializer(qs, many=True)
    return Response({"count": qs.count(), "results": serializer.data})


@api_view(["GET"])
def reasons(request):
    return Response(
        [{"value": code, "label": label} for code, label in Disagreement.REASON_CHOICES]
    )


@api_view(["GET"])
def orgs(request):
    """Return the list of org IDs so the frontend can populate its selector."""
    from .models import Location

    org_ids = list(Location.objects.values_list("org_id", flat=True).distinct().order_by("org_id"))
    return Response(org_ids)


@api_view(["POST"])
def trigger_reconcile(request):
    """Run reconciliation comparison logic and return count of disagreements."""
    try:
        from .reconciler import reconcile_from_db

        count = reconcile_from_db()
        return Response({"success": True, "count": count})
    except Exception as e:
        return Response({"error": str(e)}, status=500)
