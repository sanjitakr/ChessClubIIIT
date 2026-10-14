from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("match", "0008_match_query_indexes"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="match",
            name="analysis_json",
        ),
    ]
