from django.db import models


class Project(models.Model):
    AI_MODELS = [
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
    ]

    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, null=True)
    ai_model = models.CharField(
        max_length=100,
        choices=AI_MODELS,
        default="deepseek-ai/deepseek-v4-pro-0813",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
