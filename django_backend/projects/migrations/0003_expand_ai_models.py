from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0002_project_ai_model")]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="ai_model",
            field=models.CharField(
                choices=[
                    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
                    ("gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite"),
                    ("gemini-2.5-pro", "Gemini 2.5 Pro"),
                    ("gemini-2.0-flash", "Gemini 2.0 Flash"),
                    ("gemini-3-flash", "Gemini 3 Flash"),
                    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
                    ("gemini-3.5-flash", "Gemini 3.5 Flash"),
                    ("gemini-3.6-flash", "Gemini 3.6 Flash"),
                    ("gemini-3.7-flash", "Gemini 3.7 Flash"),
                    ("gemini-3.8-flash", "Gemini 3.8 Flash"),
                    ("gemma-4-26b", "Gemma 4 26B"),
                    ("gemma-4-31b", "Gemma 4 31B"),
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