from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tournaments", "0010_alter_tournamentregistration_unique_together_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.PositiveSmallIntegerField(choices=[(1, "Role Added"), (2, "Role Removed"), (3, "Staff Disabled"), (4, "Tournament Ended"), (5, "Result Recorded"), (6, "Result Corrected"), (7, "Time Control Changed")])),
                ("meta", models.CharField(blank=True, default="", max_length=96)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_actions", to=settings.AUTH_USER_MODEL)),
                ("match", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="audit_logs", to="tournaments.tournamentmatch")),
                ("target_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_targets", to=settings.AUTH_USER_MODEL)),
                ("tournament", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="audit_logs", to="tournaments.tournament")),
            ],
            options={
                "ordering": ["-id"],
                "indexes": [
                    models.Index(fields=["-id"], name="auditlog_id_desc_idx"),
                    models.Index(fields=["tournament", "-id"], name="auditlog_tourn_id_idx"),
                ],
            },
        ),
    ]
