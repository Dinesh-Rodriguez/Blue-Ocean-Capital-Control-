import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import authenticate
from kombu.exceptions import OperationalError
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .models import AnalyticsRollup, Organization, Project, Property, UserProfile
from .permissions import CanApprove, CanWriteProjects, IsSuperAdmin, scoped_projects
from .serializers import ProjectSerializer, RollupSerializer
from .services import aggregate_for_scope, transition_project

logger = logging.getLogger(__name__)

@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    user = authenticate(username=request.data.get("email"), password=request.data.get("password"))
    if user is None or not hasattr(user, "profile"):
        return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
    refresh = RefreshToken.for_user(user)
    refresh["organization_id"] = user.profile.organization_id
    refresh["role"] = user.profile.role
    return Response({"access": str(refresh.access_token), "refresh": str(refresh),
                     "user": {"id": user.id, "email": user.email, "role": user.profile.role,
                              "organization_id": user.profile.organization_id}})

class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return scoped_projects(self.request.user).select_related("property").order_by("-updated_at", "-id")

    def list(self, request, *args, **kwargs):
        if request.query_params.get("recent_mix") == "true":
            statuses = ["draft", "submitted", "manager_review", "finance_review", "approved", "rejected"]
            recent_by_status = [
                list(self.get_queryset().filter(status=status)[:2])
                for status in statuses
            ]
            projects = [
                project
                for index in range(2)
                for projects_for_status in recent_by_status
                for project in projects_for_status[index:index + 1]
            ]
            return Response({
                "count": len(projects),
                "next": None,
                "previous": None,
                "results": ProjectSerializer(projects, many=True).data,
            })
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        profile = self.request.user.profile
        if profile.role not in {"super_admin", "org_admin", "property_manager"}:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only project managers can create projects")
        prop = serializer.validated_data["property"]
        if profile.role != "super_admin" and (prop.organization_id != profile.organization_id or (
            profile.role != "org_admin" and not profile.properties.filter(id=prop.id).exists()
        )):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Property is outside your scope")
        serializer.save(organization=prop.organization if profile.role == "super_admin" else profile.organization)

    def get_permissions(self):
        if self.action == "approve":
            return [CanApprove()]
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [CanWriteProjects()]
        return [IsAuthenticated()]

    @action(detail=True, methods=["post"], permission_classes=[CanApprove])
    def approve(self, request, pk=None):
        if not self.get_queryset().filter(pk=pk).exists():
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            project = transition_project(pk, request.user, request.data.get("action", "approve"),
                                         request.data.get("version"))
        except (Project.DoesNotExist, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"tenant-{project.organization_id}", {"type": "approval.update",
            "project_id": project.id, "status": project.status, "version": project.version})
        from .tasks import refresh_analytics
        try:
            refresh_analytics.delay(project.organization_id)
        except OperationalError:
            logger.warning("Analytics refresh could not be queued for organization %s", project.organization_id)
        return Response(ProjectSerializer(project).data)

    @action(detail=True, methods=["post"], permission_classes=[CanWriteProjects])
    def submit(self, request, pk=None):
        if not self.get_queryset().filter(pk=pk).exists():
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            project = transition_project(pk, request.user, "submit", request.data.get("version"))
        except (Project.DoesNotExist, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"tenant-{project.organization_id}", {"type": "approval.update",
            "project_id": project.id, "status": project.status, "version": project.version})
        return Response(ProjectSerializer(project).data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def analytics(request):
    profile = request.user.profile
    if profile.role == "super_admin":
        payload = aggregate_for_scope()
        payload["total_profit"] = sum(
            float(value) for value in Organization.objects.values_list("profit_amount", flat=True)
        )
        return Response(payload)
    property_ids = None if profile.role == "org_admin" else list(profile.properties.values_list("id", flat=True))
    rollup = AnalyticsRollup.objects.filter(organization=profile.organization, property__isnull=True).first()
    if rollup and set(rollup.payload.get("property_ids", [])) == set(property_ids or []):
        return Response(rollup.payload)
    payload = {**aggregate_for_scope(profile.organization, property_ids), "property_ids": property_ids or []}
    AnalyticsRollup.objects.update_or_create(
        organization=profile.organization, property=None, defaults={"payload": payload}
    )
    return Response(payload)

class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    permission_classes = [IsSuperAdmin]
    serializer_class = None

    def list(self, request, *args, **kwargs):
        return Response(list(self.get_queryset().values("id", "name", "slug", "profit_amount")))

    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_queryset().values("id", "name", "slug", "profit_amount").get(id=kwargs["pk"]))

    def create(self, request, *args, **kwargs):
        organization = Organization.objects.create(
            name=request.data["name"], slug=request.data["slug"],
            profit_amount=request.data.get("profit_amount", 0),
        )
        return Response({"id": organization.id, "name": organization.name, "slug": organization.slug,
                         "profit_amount": organization.profit_amount}, status=201)

    def update(self, request, *args, **kwargs):
        organization = self.get_object()
        organization.name = request.data.get("name", organization.name)
        organization.slug = request.data.get("slug", organization.slug)
        organization.profit_amount = request.data.get("profit_amount", organization.profit_amount)
        organization.save()
        return Response({"id": organization.id, "name": organization.name, "slug": organization.slug,
                         "profit_amount": organization.profit_amount})

    def destroy(self, request, *args, **kwargs):
        self.get_object().delete()
        return Response(status=204)

@api_view(["GET", "POST"])
@permission_classes([IsSuperAdmin])
def platform_users(request):
    User = get_user_model()
    if request.method == "GET":
        users = UserProfile.objects.select_related("user", "organization").prefetch_related("properties")
        return Response([{
            "id": profile.user_id, "email": profile.user.email, "role": profile.role,
            "organization_id": profile.organization_id,
            "property_ids": list(profile.properties.values_list("id", flat=True)),
        } for profile in users])
    data = request.data
    organization = Organization.objects.get(id=data["organization_id"]) if data.get("organization_id") else None
    user = User.objects.create_user(username=data["email"], email=data["email"], password=data.get("password", "Passw0rd!"))
    profile = UserProfile.objects.create(user=user, organization=organization, role=data["role"])
    profile.properties.set(Property.objects.filter(id__in=data.get("property_ids", [])))
    return Response({"id": user.id, "email": user.email, "role": profile.role}, status=201)

@api_view(["PATCH", "DELETE"])
@permission_classes([IsSuperAdmin])
def platform_user_detail(request, user_id):
    User = get_user_model()
    user = User.objects.get(id=user_id)
    profile = user.profile
    if request.method == "DELETE":
        user.delete()
        return Response(status=204)
    data = request.data
    profile.role = data.get("role", profile.role)
    if "organization_id" in data:
        profile.organization_id = data["organization_id"] or None
    profile.save()
    if "property_ids" in data:
        profile.properties.set(Property.objects.filter(id__in=data["property_ids"]))
    if data.get("password"):
        user.set_password(data["password"])
        user.save(update_fields=["password"])
    return Response({"id": user.id, "email": user.email, "role": profile.role, "organization_id": profile.organization_id})
