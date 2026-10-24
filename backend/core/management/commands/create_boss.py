from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from core.models import UserProfile

class Command(BaseCommand):
    help = "Create or update the platform-level Boss Account"
    def add_arguments(self, parser):
        parser.add_argument("--email", default="boss@blueocean.example.com")
        parser.add_argument("--password", default="Passw0rd!")
    def handle(self, *args, **options):
        user, _ = get_user_model().objects.get_or_create(username=options["email"], defaults={"email": options["email"]})
        user.email = options["email"]
        user.set_password(options["password"])
        user.is_staff = True
        user.is_superuser = True
        user.save()
        UserProfile.objects.update_or_create(user=user, defaults={"organization": None, "role": "super_admin"})
        self.stdout.write(self.style.SUCCESS(f"Boss Account ready: {options['email']}"))
