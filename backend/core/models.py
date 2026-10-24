from django.conf import settings
from django.db import models

class Organization(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    profit_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)

class Property(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="properties")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="unique_property_code")]

class UserProfile(models.Model):
    ROLES = [(r, r) for r in ("super_admin", "org_admin", "property_manager", "approver", "viewer")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name="users")
    role = models.CharField(max_length=30, choices=ROLES)
    properties = models.ManyToManyField(Property, blank=True, related_name="entitled_users")

class Budget(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="budgets")
    fiscal_period = models.CharField(max_length=20)
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["property", "fiscal_period"], name="unique_budget_period")]

class Project(models.Model):
    STATUSES = [(s, s) for s in ("draft", "submitted", "manager_review", "finance_review", "approved", "rejected")]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="projects")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    fiscal_period = models.CharField(max_length=20)
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2)
    actual_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=30, choices=STATUSES, default="draft")
    version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        indexes = [
            models.Index(fields=["organization", "property", "status"]),
            models.Index(fields=["organization", "fiscal_period", "category"]),
        ]

class ApprovalEvent(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="approval_events")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    property = models.ForeignKey(Property, on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    from_status = models.CharField(max_length=30)
    to_status = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

class AnalyticsRollup(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="rollups")
    property = models.ForeignKey(Property, on_delete=models.CASCADE, null=True, blank=True)
    payload = models.JSONField(default=dict)
    computed_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "property"], name="unique_rollup_scope")]
