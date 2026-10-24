from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Organization, Property, Project, UserProfile
from .services import transition_project

class PlatformTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.org_a = Organization.objects.create(name="A", slug="a")
        self.org_b = Organization.objects.create(name="B", slug="b")
        self.property_a = Property.objects.create(organization=self.org_a, name="A1", code="A1")
        self.property_b = Property.objects.create(organization=self.org_b, name="B1", code="B1")
        user = User.objects.create_user(username="a@example.com", password="pw")
        profile = UserProfile.objects.create(user=user, organization=self.org_a, role="viewer")
        profile.properties.add(self.property_a)
        self.client = APIClient()
        self.client.force_authenticate(user)
        self.project_b = Project.objects.create(organization=self.org_b, property=self.property_b, title="secret", category="IT", fiscal_period="FY2026", budget_amount=10)

    def test_cross_tenant_detail_is_not_found(self):
        response = self.client.get(f"/api/projects/{self.project_b.id}/")
        self.assertEqual(response.status_code, 404)

    def test_approval_requires_valid_state_and_is_atomic(self):
        user = self.project_b.organization.users.first().user if self.project_b.organization.users.exists() else get_user_model().objects.create_user(username="approver", password="pw")
        if not hasattr(user, "profile"):
            profile = UserProfile.objects.create(user=user, organization=self.org_b, role="approver")
            profile.properties.add(self.property_b)
        project = Project.objects.create(organization=self.org_b, property=self.property_b, title="valid", category="IT", fiscal_period="FY2026", budget_amount=10, status="submitted")
        transitioned = transition_project(project.id, user, "approve", 0)
        self.assertEqual(transitioned.status, "manager_review")
        with self.assertRaises(ValueError):
            transition_project(project.id, user, "approve", 0)

