from celery import shared_task
from django.db.models import Q
from .models import AnalyticsRollup, Organization, Property
from .services import aggregate_for_scope

@shared_task
def refresh_analytics(organization_id):
    organization = Organization.objects.get(id=organization_id)
    AnalyticsRollup.objects.update_or_create(
        organization=organization, property=None,
        defaults={"payload": {**aggregate_for_scope(organization), "property_ids": []}},
    )
    for prop in Property.objects.filter(organization=organization):
        AnalyticsRollup.objects.update_or_create(
            organization=organization, property=prop,
            defaults={"payload": aggregate_for_scope(organization, [prop.id])},
        )
