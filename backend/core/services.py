from collections import defaultdict
from django.db import transaction
from django.db.models import Count, Max, Min, Sum
from django.utils import timezone
from .models import ApprovalEvent, AnalyticsRollup, Project

FLOW = ("submitted", "manager_review", "finance_review", "approved")

def aggregate_for_scope(organization=None, property_ids=None):
    projects = Project.objects.all() if organization is None else Project.objects.filter(organization=organization)
    if property_ids is not None:
        projects = projects.filter(property_id__in=property_ids)
    rows = projects.values("category").annotate(
        budget=Sum("budget_amount"), actual=Sum("actual_cost"), count=Count("id")
    )
    by_category = [{
        "category": row["category"], "budget": float(row["budget"] or 0),
        "actual": float(row["actual"] or 0), "count": row["count"],
    } for row in rows]
    totals = projects.aggregate(budget=Sum("budget_amount"), actual=Sum("actual_cost"))
    pending = projects.filter(status__in=("submitted", "manager_review", "finance_review")).count()
    cycle = ApprovalEvent.objects.filter(project__in=projects).values("project_id").annotate(
        first=Min("created_at"), last=Max("created_at")
    )
    cycles = [(item["last"] - item["first"]).total_seconds() / 86400 for item in cycle if item["first"] and item["last"]]
    budget, actual = float(totals["budget"] or 0), float(totals["actual"] or 0)
    return {"budget": budget, "actual": actual, "variance": actual - budget,
            "variance_percent": ((actual - budget) / budget * 100) if budget else 0,
            "pending_approval": pending, "avg_approval_cycle_days": sum(cycles) / len(cycles) if cycles else 0,
            "by_category": by_category, "computed_at": timezone.now().isoformat()}

@transaction.atomic
def transition_project(project_id, actor, action, expected_version=None):
    project = Project.objects.select_for_update().select_related("organization", "property").get(id=project_id)
    if expected_version is not None and project.version != expected_version:
        raise ValueError("Project was changed by another approver")
    if action == "submit":
        if project.status != "draft":
            raise ValueError("Only draft projects can be submitted")
        next_status = "submitted"
    elif action == "reject":
        if project.status not in FLOW[:-1]:
            raise ValueError("Project is not awaiting approval")
        next_status = "rejected"
    elif action == "approve":
        if project.status not in FLOW[:-1]:
            raise ValueError("Project is not awaiting approval")
        next_status = FLOW[FLOW.index(project.status) + 1]
    else:
        raise ValueError("Unknown approval action")
    old_status = project.status
    project.status, project.version = next_status, project.version + 1
    project.save(update_fields=["status", "version", "updated_at"])
    ApprovalEvent.objects.create(project=project, organization=project.organization, property=project.property,
                                 actor=actor, from_status=old_status, to_status=next_status)
    return project
