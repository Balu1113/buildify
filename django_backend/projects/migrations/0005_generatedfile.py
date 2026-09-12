from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("projects", "0004_normalize_legacy_gemma_models")]

    operations = [
        migrations.CreateModel(
            name="GeneratedFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(max_length=1024)),
                ("content", models.TextField()),
                ("content_hash", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="generated_files", to="projects.project")),
            ],
            options={"ordering": ["path"]},
        ),
        migrations.AddConstraint(
            model_name="generatedfile",
            constraint=models.UniqueConstraint(fields=("project", "path"), name="unique_generated_file_per_project"),
        ),
    ]
