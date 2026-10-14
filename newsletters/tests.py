from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from accounts.permissions import RESULT_STAFF_GROUP, TOURNAMENT_MANAGER_GROUP, ensure_default_groups
from newsletters.models import Newsletter


class NewsletterRoleAccessTests(TestCase):
    def setUp(self):
        ensure_default_groups()
        User = get_user_model()
        self.manager = User.objects.create_user(username="manager", password="pass")
        self.staff = User.objects.create_user(username="staff", password="pass")
        self.player = User.objects.create_user(username="player", password="pass")
        self.manager.groups.add(Group.objects.get(name=TOURNAMENT_MANAGER_GROUP))
        self.staff.groups.add(Group.objects.get(name=RESULT_STAFF_GROUP))

    def test_manager_without_django_admin_can_publish_newsletter(self):
        self.assertFalse(self.manager.is_staff)
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("newsletter_admin"),
            {
                "action": "create",
                "title": "Round One Report",
                "content": "Tournament started cleanly.",
            },
        )

        self.assertRedirects(response, reverse("newsletter_admin"))
        self.assertTrue(Newsletter.objects.filter(title="Round One Report").exists())

    def test_result_staff_cannot_publish_newsletter(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("newsletter_admin"),
            {
                "action": "create",
                "title": "Blocked Report",
                "content": "Should not publish.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Newsletter.objects.filter(title="Blocked Report").exists())

    def test_player_cannot_publish_from_public_newsletter_page(self):
        self.client.force_login(self.player)

        response = self.client.post(
            reverse("newsletters"),
            {
                "title": "Player Draft",
                "content": "Should not publish.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Newsletter.objects.filter(title="Player Draft").exists())
