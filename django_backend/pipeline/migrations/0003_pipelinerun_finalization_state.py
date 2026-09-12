from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline", "0002_pipelinerun_stream_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinerun",
            name="finalization_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="finalization_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="pipelinerun",
            name="finalization_state",
            field=models.CharField(
                choices=[
                    ("pending", "Finalization pending"),
                    ("running", "Finalization running"),
                    ("failed", "Finalization failed"),
                    ("accepted", "Project accepted"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]