from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile, Achievement


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'get_display_name', 'email', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    inlines = [UserProfileInline]
    list_filter = ('is_staff', 'is_superuser', 'groups')

    @admin.display(description="Display Name")
    def get_display_name(self, obj):
        return obj.display_name


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'rating', 'rank',)
    search_fields = ('user__username',)
    filter_horizontal = ('achievements',)


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon', 'created_at')
    search_fields = ('name',)
