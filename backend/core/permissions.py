from rest_framework.permissions import BasePermission
from .models import Project

def scoped_projects(user):
    profile = user.profile
    queryset = Project.objects.all() if profile.role == "super_admin" else Project.objects.filter(organization=profile.organization)
    if profile.role not in {"super_admin", "org_admin"}:
        queryset = queryset.filter(property_id__in=profile.properties.values("id"))
    return queryset

class CanWriteProjects(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.profile.role in {"super_admin", "org_admin", "property_manager"}

class CanApprove(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.profile.role in {"super_admin", "org_admin", "approver"}

class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.profile.role == "super_admin"
