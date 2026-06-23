from django import template

register = template.Library()


@register.filter
def display_name(user):
    if user is None:
        return ""
    if hasattr(user, "display_name"):
        return user.display_name
    full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    return full or getattr(user, "username", "")
