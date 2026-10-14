from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from accounts.permissions import (
    RESULT_STAFF_GROUP,
    SUPERADMIN_GROUP,
    TOURNAMENT_MANAGER_GROUP,
    ensure_default_groups,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Create chess-club role groups and optionally assign portal/admin roles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--assign-staff",
            type=str,
            help="Username to add to the Result Staff group (win/loss entry only).",
        )
        parser.add_argument(
            "--assign-manager",
            type=str,
            help="Username to add to the Tournament Manager group. Does not grant Django admin access.",
        )
        parser.add_argument(
            "--assign-superadmin",
            type=str,
            help="Username to promote to Superadmin and Django superuser.",
        )

    def handle(self, *args, **options):
        ensure_default_groups()
        self.stdout.write(
            self.style.SUCCESS(
                f"Groups ready: {RESULT_STAFF_GROUP}, {TOURNAMENT_MANAGER_GROUP}, {SUPERADMIN_GROUP}"
            )
        )

        staff_username = options.get("assign_staff")
        if staff_username:
            user = User.objects.filter(username=staff_username).first()
            if not user:
                self.stderr.write(f"User '{staff_username}' not found.")
                return
            group = Group.objects.get(name=RESULT_STAFF_GROUP)
            user.groups.add(group)
            self.stdout.write(self.style.SUCCESS(f"Added {staff_username} to {RESULT_STAFF_GROUP}"))

        manager_username = options.get("assign_manager")
        if manager_username:
            user = User.objects.filter(username=manager_username).first()
            if not user:
                self.stderr.write(f"User '{manager_username}' not found.")
                return
            group = Group.objects.get(name=TOURNAMENT_MANAGER_GROUP)
            user.groups.add(group)
            self.stdout.write(self.style.SUCCESS(f"Added {manager_username} to {TOURNAMENT_MANAGER_GROUP}"))

        superadmin_username = options.get("assign_superadmin")
        if superadmin_username:
            user = User.objects.filter(username=superadmin_username).first()
            if not user:
                self.stderr.write(f"User '{superadmin_username}' not found.")
                return
            group = Group.objects.get(name=SUPERADMIN_GROUP)
            user.groups.add(group)
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])
            self.stdout.write(self.style.SUCCESS(f"Promoted {superadmin_username} to {SUPERADMIN_GROUP}"))
