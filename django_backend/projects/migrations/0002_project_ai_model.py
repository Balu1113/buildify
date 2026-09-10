from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="project",
            name="ai_model",
            field=models.CharField(
                choices=[
                    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
                    ("gemini-2.5-pro", "Gemini 2.5 Pro"),
                    ("gemini-2.0-flash", "Gemini 2.0 Flash"),
                    ("llama-3.3-70b-versatile", "Groq - Llama 3.3 70B"),
                    ("llama-4-scout-17b-16e-instruct", "Groq - Llama 4 Scout"),
                    ("qwen/qwen3-32b", "Groq - Qwen 3 32B"),
                    ("deepseek-ai/deepseek-v4-pro-0813", "DeepSeek V4 Pro"),
                ],
                default="deepseek-ai/deepseek-v4-pro-0813",
                max_length=100,
            ),
        ),
    ]