"""
API views.

Authentication is intentionally omitted per the assignment brief. The `org`
query parameter therefore represents the **authenticated tenant context** for
this exercise only. In production, the org would be derived from the
authenticated principal (e.g. a JWT claim or session-bound org attribute) and
never accepted from the client. The current design is application-level
filtering, not authorization — a distinction that matters in production.

Endpoints
─────────
GET /api/disagreements/?org=ORG-A
    Returns disagreements for the given org.
    Requires ?org=. Returns 400 if absent.
    Optional filters: ?reason=VALUE_MISMATCH
    Optional sort:    ?sort=value_a  or  ?sort=-value_a  (prefix - for desc)

GET /api/import-issues/?org=ORG-A
    Returns import anomalies scoped to the requesting org.
    Requires ?org=. Returns 400 if absent. Same tenant model as /disagreements/.

GET /api/reasons/
    Returns the list of valid reason codes and their display labels.

GET /api/orgs/
    Returns the list of valid org IDs for the UI org selector.

POST /api/reconcile/
    Triggers a fresh reconciliation run and returns the disagreement count.
"""

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Disagreement, ImportIssue, Location
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

    # Tenant isolation enforced here: filter by org through the Location FK.
    # NOTE: In production the org_id would be derived from the authenticated
    # principal, not supplied by the caller. This is the critical difference
    # between application-level filtering and actual authorization.
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
    """
    Returns import anomalies scoped to the requesting org.

    Requires ?org= — same tenant model as /disagreements/. In production this
    endpoint would be restricted to privileged/admin roles rather than any
    authenticated tenant user, since import issues cross location boundaries
    (e.g. an unknown location_id cannot be attributed to any org).

    Issues with org_id="" (unknown-location rows) are excluded from tenant
    responses and would only appear in a privileged admin view.
    """
    org_id = request.query_params.get("org", "").strip()
    if not org_id:
        return Response(
            {"error": "org query parameter is required (e.g. ?org=ORG-A)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = ImportIssue.objects.filter(org_id=org_id).order_by("source_file", "row_identifier")
    serializer = ImportIssueSerializer(qs, many=True)
    return Response({"org_id": org_id, "count": qs.count(), "results": serializer.data})


@api_view(["GET"])
def reasons(request):
    return Response(
        [{"value": code, "label": label} for code, label in Disagreement.REASON_CHOICES]
    )


@api_view(["GET"])
def orgs(request):
    """Return the list of org IDs so the frontend can populate its selector."""
    org_ids = list(
        Location.objects.values_list("org_id", flat=True).distinct().order_by("org_id")
    )
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
