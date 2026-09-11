from django.db import models


class Project(models.Model):
    LEGACY_MODEL_ALIASES = {
        "gemma-4-26b": "gemma-4-26b-a4b-it",
        "gemma-4-31b": "gemma-4-31b-it",
    }

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
        ("gemma-4-26b-a4b-it", "Gemma 4 26B A4B IT"),
        ("gemma-4-31b-it", "Gemma 4 31B IT"),
        ("openai/gpt-oss-120b", "Groq - GPT OSS 120B"),
        ("openai/gpt-oss-20b", "Groq - GPT OSS 20B (Fast)"),
        ("deepseek/deepseek-chat-v3.1", "DeepSeek Chat V3.1"),
        ("nex-agi/nex-n2.5-pro:free", "Nex AGI N2.5 Pro (Free)"),
        ("google/gemini-2.5-flash", "Google Gemini 2.5 Flash"),
        ("openai/gpt-4.1-mini", "OpenAI GPT-4.1 Mini"),
        ("meta-llama/llama-3.3-70b-instruct", "Meta Llama 3.3 70B Instruct"),
        ("mistralai/mistral-small-3.1-24b-instruct", "Mistral Small 3.1 24B Instruct"),
        ("poolside/poolside-laguna-s-2.1", "Poolside Laguna S 2.1"),
        ("poolside/poolside-laguna-xs-2.1", "Poolside Laguna XS 2.1"),
        ("cohere/north-mini-code", "Cohere North Mini Code"),
        ("dots3/dots3-note", "Dots3-Note"),
        ("thinking-machines/inkling", "Thinking Machines Inkling"),
    ]

    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, null=True)
    ai_model = models.CharField(
        max_length=100,
        choices=AI_MODELS,
        default="nex-agi/nex-n2.5-pro:free",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
