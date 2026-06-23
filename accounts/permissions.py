"""Role helpers for tournament staff and result entry."""

RESULT_STAFF_GROUP = "Result Staff"
TOURNAMENT_MANAGER_GROUP = "Tournament Manager"


def is_result_staff(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name=RESULT_STAFF_GROUP).exists()


def is_tournament_manager(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.is_staff:
        return True
    return user.groups.filter(name=TOURNAMENT_MANAGER_GROUP).exists()


def can_record_results(user) -> bool:
    return is_result_staff(user)


def ensure_default_groups():
    from django.contrib.auth.models import Group

    Group.objects.get_or_create(name=RESULT_STAFF_GROUP)
    Group.objects.get_or_create(name=TOURNAMENT_MANAGER_GROUP)
