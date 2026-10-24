from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import OrganizationViewSet, ProjectViewSet, analytics, login, platform_user_detail, platform_users

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("organizations", OrganizationViewSet, basename="organization")
urlpatterns = [
    path("auth/login/", login),
    path("analytics/", analytics),
    path("platform/users/", platform_users),
    path("platform/users/<int:user_id>/", platform_user_detail),
    path("", include(router.urls)),
]
