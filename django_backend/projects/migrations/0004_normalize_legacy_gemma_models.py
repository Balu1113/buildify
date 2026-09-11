from django.db import migrations


def normalize_legacy_models(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    Project.objects.filter(ai_model="gemma-4-26b").update(ai_model="gemma-4-26b-a4b-it")
    Project.objects.filter(ai_model="gemma-4-31b").update(ai_model="gemma-4-31b-it")


class Migration(migrations.Migration):
    dependencies = [("projects", "0003_expand_ai_models")]

    operations = [migrations.RunPython(normalize_legacy_models, migrations.RunPython.noop)]
