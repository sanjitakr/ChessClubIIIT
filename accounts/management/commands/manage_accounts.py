from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from accounts.permissions import (
    RESULT_STAFF_GROUP,
    SUPERADMIN_GROUP,
    TOURNAMENT_MANAGER_GROUP,
    ensure_default_groups,
)


ROLE_GROUPS = {
    "result_staff": RESULT_STAFF_GROUP,
    "manager": TOURNAMENT_MANAGER_GROUP,
    "superadmin": SUPERADMIN_GROUP,
}


class Command(BaseCommand):
    help = "Create users and manage chess-club roles from the command line."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Username to create or update.")
        parser.add_argument("--password", help="Password for a new or existing user.")
        parser.add_argument("--email", default="", help="Email address.")
        parser.add_argument("--first-name", default="", help="First name.")
        parser.add_argument("--last-name", default="", help="Last name.")
        parser.add_argument("--create", action="store_true", help="Create the user if missing.")
        parser.add_argument(
            "--role",
            choices=["player", "result_staff", "manager", "admin", "superadmin"],
            help="Role to assign.",
        )
        parser.add_argument(
            "--remove-role",
            choices=["result_staff", "manager", "admin", "superadmin", "all_staff"],
            help="Role to remove.",
        )
        parser.add_argument("--activate", action="store_true", help="Activate the user.")
        parser.add_argument("--disable", action="store_true", help="Disable login for the user.")
        parser.add_argument("--list-staff", action="store_true", help="List users with staff/admin roles.")

    def handle(self, *args, **options):
        ensure_default_groups()

        if options["list_staff"]:
            self.list_staff()
            return

        username = (options["username"] or "").strip()
        if not username:
            raise CommandError("--username is required unless --list-staff is used.")

        User = get_user_model()
        user = User.objects.filter(username__iexact=username).first()
        if not user:
            if not options["create"]:
                raise CommandError(f"User '{username}' does not exist. Add --create to create it.")
            user = User(username=username)
            self.stdout.write(f"Creating user: {username}")

        changed_fields = []
        for option_name, field_name in (
            ("email", "email"),
            ("first_name", "first_name"),
            ("last_name", "last_name"),
        ):
            value = options.get(option_name)
            if value and getattr(user, field_name) != value:
                setattr(user, field_name, value)
                changed_fields.append(field_name)

        if options["password"]:
            user.set_password(options["password"])
            changed_fields.append("password")
        elif options["create"] and not user.pk:
            user.set_unusable_password()
            changed_fields.append("password")

        if options["activate"]:
            user.is_active = True
            changed_fields.append("is_active")
        if options["disable"]:
            user.is_active = False
            changed_fields.append("is_active")

        if not user.pk:
            user.save()
        elif changed_fields:
            user.save(update_fields=sorted(set(changed_fields)))

        role = options["role"]
        if role:
            self.assign_role(user, role)

        remove_role = options["remove_role"]
        if remove_role:
            self.remove_role(user, remove_role)

        user.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(self.describe_user(user)))

    def assign_role(self, user, role):
        if role == "player":
            self.stdout.write("Player role uses the normal active user account.")
            return

        if role == "admin":
            user.is_staff = True
            user.is_active = True
            user.save(update_fields=["is_staff", "is_active"])
            self.stdout.write("Granted Django admin access.")
            return

        group = Group.objects.get(name=ROLE_GROUPS[role])
        user.groups.add(group)
        user.is_active = True

        if role == "superadmin":
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_active", "is_staff", "is_superuser"])
        else:
            user.save(update_fields=["is_active"])

        self.stdout.write(f"Added role group: {group.name}")

    def remove_role(self, user, role):
        if role == "all_staff":
            groups = Group.objects.filter(name__in=ROLE_GROUPS.values())
            user.groups.remove(*groups)
            user.is_staff = False
            user.is_superuser = False
            user.save(update_fields=["is_staff", "is_superuser"])
            self.stdout.write("Removed all chess staff/admin access.")
            return

        if role == "admin":
            user.is_staff = user.is_superuser
            user.save(update_fields=["is_staff"])
            self.stdout.write("Removed Django admin access.")
            return

        group = Group.objects.get(name=ROLE_GROUPS[role])
        user.groups.remove(group)

        if role == "superadmin":
            user.is_superuser = False
            user.is_staff = False
            user.save(update_fields=["is_superuser", "is_staff"])

        self.stdout.write(f"Removed role group: {group.name}")

    def list_staff(self):
        User = get_user_model()
        users = (
            User.objects.filter(
                Q(groups__name__in=ROLE_GROUPS.values()) | Q(is_staff=True) | Q(is_superuser=True)
            )
            .distinct()
            .prefetch_related("groups")
            .order_by("username")
        )

        if not users:
            self.stdout.write("No staff/admin users found.")
            return

        for user in users:
            self.stdout.write(self.describe_user(user))

    def describe_user(self, user):
        groups = ", ".join(user.groups.values_list("name", flat=True)) or "none"
        flags = []
        if user.is_superuser:
            flags.append("superuser")
        if user.is_staff:
            flags.append("django-admin")
        if not user.is_active:
            flags.append("inactive")
        flag_text = ", ".join(flags) or "active"
        return f"{user.username} | groups: {groups} | flags: {flag_text}"
