from rest_framework import serializers
from .models import Project, AnalyticsRollup

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("id", "organization", "property", "title", "category", "fiscal_period",
                  "budget_amount", "actual_cost", "status", "version", "created_at", "updated_at")
        read_only_fields = ("organization", "status", "version", "created_at", "updated_at")

class RollupSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticsRollup
        fields = ("property", "payload", "computed_at")

