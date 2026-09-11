from rest_framework import serializers
from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    ai_model = serializers.CharField(required=False, default="nex-agi/nex-n2.5-pro:free")

    def validate_ai_model(self, value):
        normalized = Project.LEGACY_MODEL_ALIASES.get(value, value)
        valid_models = {model for model, _ in Project.AI_MODELS}
        if normalized not in valid_models:
            raise serializers.ValidationError(f'"{value}" is not a valid choice.')
        return normalized

    class Meta:
        model = Project
        fields = ["id", "name", "description", "ai_model", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
