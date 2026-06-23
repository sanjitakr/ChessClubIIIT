from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, User
from accounts.permissions import RESULT_STAFF_GROUP, TOURNAMENT_MANAGER_GROUP, ensure_default_groups


class Command(BaseCommand):
    help = "Create Result Staff and Tournament Manager groups."

    def add_arguments(self, parser):
        parser.add_argument(
            "--assign-staff",
            type=str,
            help="Username to add to the Result Staff group (win/loss entry only).",
        )

    def handle(self, *args, **options):
        ensure_default_groups()
        self.stdout.write(self.style.SUCCESS(f"Groups ready: {RESULT_STAFF_GROUP}, {TOURNAMENT_MANAGER_GROUP}"))

        username = options.get("assign_staff")
        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                self.stderr.write(f"User '{username}' not found.")
                return
            group = Group.objects.get(name=RESULT_STAFF_GROUP)
            user.groups.add(group)
            self.stdout.write(self.style.SUCCESS(f"Added {username} to {RESULT_STAFF_GROUP}"))
