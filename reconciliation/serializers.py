from rest_framework import serializers
from .models import Disagreement, ImportIssue


class DisagreementSerializer(serializers.ModelSerializer):
    org_id = serializers.CharField(source='location.org_id', read_only=True)
    location_name = serializers.CharField(source='location.location_name', read_only=True)
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)

    record_a_extra_data = serializers.JSONField(source='record_a.extra_data', read_only=True, default=dict)
    entry_b_extra_data = serializers.JSONField(source='entry_b.extra_data', read_only=True, default=dict)

    class Meta:
        model = Disagreement
        fields = [
            'id',
            'reason',
            'reason_display',
            'record_id_a',
            'entry_id_b',
            'record_ref_raw',
            'location_id',
            'org_id',
            'location_name',
            'value_a',
            'value_b',
            'value_b_raw',
            'detail',
            'created_at',
            'record_a_extra_data',
            'entry_b_extra_data',
        ]


class ImportIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportIssue
        fields = [
            'id',
            'source_file',
            'row_identifier',
            'field_name',
            'raw_value',
            'message',
            'severity',
            'created_at',
        ]
